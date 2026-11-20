"""Inspect and safely retry a local shipment webhook inbox."""
import argparse
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SAMPLE = Path(__file__).with_name("sample-deliveries.json")


@contextmanager
def inbox(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, shipment TEXT NOT NULL,
                processed INTEGER NOT NULL DEFAULT 0, deliveries INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS ledger (
                event_id TEXT PRIMARY KEY REFERENCES events(id), shipment TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attempts (
                seq INTEGER PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(id), outcome TEXT NOT NULL
            );
        """)
        yield db
    finally:
        db.close()


def fields(event):
    if not isinstance(event, dict) or set(event) != {"id", "shipment"}:
        raise ValueError("each event must contain exactly id and shipment")
    for key in ("id", "shipment"):
        if not isinstance(event[key], str) or not event[key].strip():
            raise ValueError(f"{key} must be a nonempty string")
    return event["id"], event["shipment"]


def receive(db, events):
    if not isinstance(events, list):
        raise ValueError("deliveries must be a JSON array")
    with db:
        db.execute("BEGIN IMMEDIATE")
        for event in events:
            event_id, shipment = fields(event)
            old = db.execute("SELECT shipment FROM events WHERE id=?", (event_id,)).fetchone()
            if old is None:
                db.execute("INSERT INTO events(id,shipment) VALUES (?,?)", (event_id, shipment))
            elif old[0] != shipment:
                raise ValueError(f"{event_id} was already used for a different shipment")
            else:
                db.execute("UPDATE events SET deliveries=deliveries+1 WHERE id=?", (event_id,))


def process(db, event_id, simulate_failure=False):
    with db:
        db.execute("BEGIN IMMEDIATE")
        event = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if event is None:
            raise ValueError(f"unknown event: {event_id}")
        if event["processed"]:
            outcome = "skipped-already-applied"
        else:
            db.execute("SAVEPOINT apply_effect")
            db.execute("INSERT INTO ledger(event_id,shipment) VALUES (?,?)", (event_id, event["shipment"]))
            if simulate_failure:
                db.execute("ROLLBACK TO apply_effect")
                outcome = "simulated-failure"
            else:
                db.execute("UPDATE events SET processed=1 WHERE id=?", (event_id,))
                outcome = "applied"
            db.execute("RELEASE apply_effect")
        db.execute("INSERT INTO attempts(event_id,outcome) VALUES (?,?)", (event_id, outcome))
        return outcome


def report(db):
    with db:
        db.execute("BEGIN")
        return {
            "inbox": [dict(row) for row in db.execute("SELECT * FROM events ORDER BY id")],
            "attempts": [dict(row) for row in db.execute("SELECT * FROM attempts ORDER BY seq")],
            "shipment_scans": [dict(row) for row in db.execute(
                "SELECT shipment,COUNT(*) AS scans FROM ledger GROUP BY shipment ORDER BY shipment")]
        }


def read_batch(path):
    with Path(path).open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default="replay-desk.sqlite3")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    sub.add_parser("status")
    sub.add_parser("receive").add_argument("json_file")
    run = sub.add_parser("process")
    run.add_argument("id")
    run.add_argument("--fail", action="store_true", help="roll back the ledger write inside a savepoint")
    args = p.parse_args()
    try:
        with inbox(":memory:" if args.cmd == "demo" else args.db) as db:
            if args.cmd == "demo":
                receive(db, read_batch(SAMPLE))
                process(db, "evt-201", True)
                process(db, "evt-201")
                process(db, "evt-201")
                process(db, "evt-202")
                result = report(db)
            elif args.cmd == "receive":
                batch = read_batch(args.json_file)
                receive(db, batch)
                result = {"received": len(batch)}
            elif args.cmd == "process":
                result = {"outcome": process(db, args.id, args.fail)}
            else:
                result = report(db)
            print(json.dumps(result, indent=2))
    except (ValueError, sqlite3.Error, OSError) as exc:
        p.exit(2, f"replay-desk: {exc}\n")


if __name__ == "__main__":
    main()
