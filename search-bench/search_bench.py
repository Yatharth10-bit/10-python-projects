"""Compare title-weighted BM25 against a baseline on a small judged corpus."""

import argparse
import csv
import json
import math
import re
import sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent


def read_rows(path, headers):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(headers).issubset(reader.fieldnames or []):
            raise ValueError(f"{path.name} needs columns {', '.join(headers)}")
        for row in reader:
            if any(not (row.get(key) or "").strip() for key in headers):
                raise ValueError(f"{path.name} row {reader.line_num} has a blank field")
            yield tuple(row[key].strip() for key in headers)


def index_documents(db, path):
    db.execute("CREATE VIRTUAL TABLE docs USING fts5(id UNINDEXED, title, body)")
    seen = set()
    for doc_id, title, body in read_rows(path, ("id", "title", "body")):
        if doc_id in seen:
            raise ValueError(f"Duplicate document ID: {doc_id}")
        db.execute("INSERT INTO docs VALUES (?, ?, ?)", (doc_id, title, body))
        seen.add(doc_id)
    if not seen:
        raise ValueError("The document collection is empty")
    return seen


def search(db, query, title_weight=1.0, k=3):
    if not 1 <= k <= 50 or not math.isfinite(title_weight) or title_weight <= 0:
        raise ValueError("Use k from 1 to 50 and a finite, positive title weight")
    if len(query) > 300:
        raise ValueError("Queries can contain up to 300 characters")
    terms = dict.fromkeys(re.findall(r"[^\W_]+", query.casefold()))
    if not terms:
        return []
    expression = " OR ".join(f'"{term}"' for term in terms)
    rows = db.execute(
        "SELECT id, title, snippet(docs, 2, '[', ']', ' ... ', 16) FROM docs "
        "WHERE docs MATCH ? ORDER BY bm25(docs, 0, ?, 1), id LIMIT ?",
        (expression, title_weight, k),
    )
    return [dict(id=i, title=t, excerpt=e) for i, t, e in rows]


def evaluate(db, path, known_ids, weight, k):
    judgments = {}
    for query, doc_id in read_rows(path, ("query", "relevant_id")):
        if doc_id not in known_ids:
            raise ValueError(f"Unknown judged document: {doc_id}")
        judgments.setdefault(query, set()).add(doc_id)
    if not judgments:
        raise ValueError("At least one judged query is required")
    scores = [0.0, 0.0]
    for query, relevant in judgments.items():
        first = []
        for i, boost in enumerate((1.0, weight)):
            ranks = search(db, query, boost, k)
            rank = next((n for n, hit in enumerate(ranks, 1) if hit["id"] in relevant), 0)
            first.append(rank)
            scores[i] += 1 / rank if rank else 0
        print(f"{query:26} {first[0] or 'miss':>6} {first[1] or 'miss':>8}")
    return tuple(total / len(judgments) for total in scores)


def make_handler(db, weight, k):
    class SearchAPI(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlsplit(self.path)
            code = 200
            if url.path != "/search":
                code, result = 404, {"error": "Use /search?q=your+terms"}
            else:
                query = parse_qs(url.query).get("q", [""])[0].strip()
                try:
                    if not query:
                        raise ValueError("Provide a nonempty q parameter")
                    result = {"query": query, "hits": search(db, query, weight, k)}
                except ValueError as exc:
                    code, result = 400, {"error": str(exc)}
            body = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return SearchAPI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs", type=Path, default=HERE / "documents.csv")
    parser.add_argument("--weight", type=float, default=5.0, help="Weight assigned to title hits")
    parser.add_argument("-k", type=int, default=3)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("query").add_argument("terms")
    commands.add_parser("eval").add_argument("--labels", type=Path, default=HERE / "judgments.csv")
    commands.add_parser("serve").add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.k <= 50 or not math.isfinite(args.weight) or args.weight <= 0:
        parser.error("Use k from 1 to 50 and a finite, positive weight")
    with closing(sqlite3.connect(":memory:")) as db:
        try:
            ids = index_documents(db, args.docs)
            if args.command == "eval":
                print("Query                        Base  Boosted  (first relevant rank)")
                base, boosted = evaluate(db, args.labels, ids, args.weight, args.k)
                print(f"MRR@{args.k}: {base:.3f} baseline / {boosted:.3f} title-weighted")
            elif args.command == "query":
                print(json.dumps(search(db, args.terms, args.weight, args.k), indent=2, ensure_ascii=False))
            else:
                with HTTPServer(("127.0.0.1", args.port), make_handler(db, args.weight, args.k)) as api:
                    print(f"Search API at http://127.0.0.1:{api.server_port}/search?q=graphics+lab", flush=True)
                    try:
                        api.serve_forever()
                    except KeyboardInterrupt:
                        pass
        except (ValueError, OSError, sqlite3.Error, csv.Error) as exc:
            parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
