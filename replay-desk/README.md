# ReplayDesk

A courier sends the same scan twice. A worker fails halfway through processing it. ReplayDesk stores each delivery count and attempt, then shows whether the shipment ledger actually changed. All effects in this demo stay inside SQLite.

## Try the failure

From this folder, using Python 3.10+:

```sh
python replay_desk.py demo
python -m unittest discover -v
```

The demo ingests three deliveries for two distinct scans on the same shipment. Event `evt-201` fails, succeeds on retry, then skips a repeat. The final shipment total is two. Try the same commands separately and inspect the ledger between attempts:

```sh
python replay_desk.py receive sample-deliveries.json
python replay_desk.py process evt-201 --fail
python replay_desk.py status
python replay_desk.py process evt-201
python replay_desk.py process evt-201
python replay_desk.py status
```

The regular commands persist to a local file. Set `--db another.sqlite3` before the command to start a separate inbox. To experiment, change the IDs and shipments in a copy of the sample JSON. Reusing an ID with a changed shipment rejects the entire incoming batch.

## Explain it in an interview

The event ID identifies a scan. The shipment identifies what was scanned. Deduplicating by shipment would silently lose legitimate scans. The worker opens a write transaction, checks the event, and records the effect and completion together. The failure switch rolls back just the effect using a savepoint, leaving an auditable attempt. Another worker can then retry.

**Scope.** This CLI models webhook ingestion from a file. The transaction protects local database changes. A remote carrier call or email would require a separate delivery strategy.

[Real-world motivation: Stripe webhook delivery and retries](https://docs.stripe.com/webhooks)
