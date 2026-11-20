"""Reconcile two single-currency CSV ledgers by invoice ID."""
import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

EXAMPLES = Path(__file__).with_name("examples")


def paise(text):
    value = text.strip()
    if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]{1,2})?", value):
        raise ValueError("amount must be a decimal with at most two places")
    whole, _, fraction = value.lstrip("-").partition(".")
    amount = int(whole) * 100 + int(fraction.ljust(2, "0"))
    return -amount if value.startswith("-") else amount


def read_ledger(path):
    records = defaultdict(list)
    rejects = []
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, strict=True)
        header = next(reader, [])
        if sorted(header) != ["amount", "invoice_id"]:
            raise ValueError(f"{path}: expected exactly the columns invoice_id and amount")
        for row in reader:
            line = reader.line_num
            invoice = ""
            if header.index("invoice_id") < len(row):
                invoice = row[header.index("invoice_id")].strip()
            amount = None
            try:
                if len(row) != 2:
                    raise ValueError("expected two fields")
                if not invoice:
                    raise ValueError("missing invoice ID")
                amount = paise(row[header.index("amount")])
            except ValueError as error:
                rejects.append({"line": line, "invoice_id": invoice, "reason": str(error)})
            if invoice:
                records[invoice].append({"line": line, "paise": amount})
    return records, rejects


def reconcile(expected_path, received_path):
    left, left_errors = read_ledger(expected_path)
    right, right_errors = read_ledger(received_path)
    details = []
    counts = defaultdict(int)
    for invoice in sorted(left.keys() | right.keys()):
        expected, received = left.get(invoice, []), right.get(invoice, [])
        if len(expected) > 1 or len(received) > 1:
            state = "duplicate"
        elif any(row["paise"] is None for row in expected + received):
            state = "invalid"
        elif not expected:
            state = "unexpected"
        elif not received:
            state = "missing"
        elif expected[0]["paise"] != received[0]["paise"]:
            state = "mismatch"
        else:
            state = "matched"
        counts[state] += 1
        details.append({"invoice_id": invoice, "state": state, "expected": expected, "received": received})
    def valid_total(groups):
        return sum(row["paise"] for rows in groups.values() for row in rows if row["paise"] is not None)
    expected_total = valid_total(left)
    received_total = valid_total(right)
    return {
        "clean": not (left_errors or right_errors or any(k != "matched" for k in counts)),
        "invoice_counts": dict(sorted(counts.items())),
        "parseable_amounts_with_id_paise": {"expected": expected_total, "received": received_total,
                                             "received_minus_expected": received_total - expected_total},
        "rejected_rows": {"expected": left_errors, "received": right_errors},
        "invoices": details
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    cmd = p.add_subparsers(dest="command", required=True)
    cmd.add_parser("demo")
    compare = cmd.add_parser("compare")
    compare.add_argument("expected")
    compare.add_argument("received")
    compare.add_argument("--check", action="store_true", help="exit 1 for reconciliation exceptions")
    args = p.parse_args()
    try:
        if args.command == "demo":
            report = reconcile(EXAMPLES / "expected.csv", EXAMPLES / "received.csv")
        else:
            report = reconcile(args.expected, args.received)
        print(json.dumps(report, indent=2))
        if getattr(args, "check", False) and not report["clean"]:
            return 1
        return 0
    except (OSError, ValueError, csv.Error) as exc:
        p.exit(2, f"batch-proof: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
