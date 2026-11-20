"""Find inconsistent outcomes across retries of the same CI job."""

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path


def suite_cases(element, lineage=()):
    tag = element.tag.rsplit("}", 1)[-1]
    if tag == "testsuite":
        lineage = lineage + (element.get("name", ""),)
    if tag == "testcase":
        yield lineage, element
    else:
        for child in element:
            yield from suite_cases(child, lineage)


def read_report(path):
    root = ET.parse(path).getroot()
    if root.tag.rsplit("}", 1)[-1] not in {"testsuite", "testsuites"}:
        raise ValueError(f"{path.name}: expected a JUnit testsuite or testsuites root")
    seen = set()
    for lineage, case in suite_cases(root):
        if not case.get("name"):
            raise ValueError(f"{path.name}: unnamed testcase")
        identity = (lineage, case.get("classname", ""), case.get("name"))
        if identity in seen:
            raise ValueError(f"{path.name}: duplicate testcase {identity}; split jobs into separate reports")
        seen.add(identity)
        tags = {c.tag.rsplit("}", 1)[-1] for c in case}
        if tags & {"flakyFailure", "rerunFailure", "flakyError", "rerunError"}:
            raise ValueError("inline retries unsupported; export one report per attempt")
        status = "fail" if tags & {"failure", "error"} else "skip" if "skipped" in tags else "pass"
        duration = Decimal(case.get("time", "0"))
        if not duration.is_finite() or duration < 0 or not math.isfinite(float(duration)):
            raise ValueError(f"{path.name}: invalid testcase duration")
        yield identity, status, duration


def analyze(manifest):
    manifest = Path(manifest)
    records = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError("manifest must be a non-empty list")
    histories = defaultdict(list)
    attempts = set()
    for entry in records:
        if not isinstance(entry, dict):
            raise ValueError("report entry must be an object")
        keys = ("commit", "run", "job", "environment", "file")
        if any(not isinstance(entry.get(k), str) or not entry[k].strip() for k in keys):
            raise ValueError(f"each record needs non-empty strings for {', '.join(keys)}")
        attempt = entry.get("attempt")
        if type(attempt) is not int or attempt < 1:
            raise ValueError("attempt must be a positive integer")
        group = tuple(entry[k] for k in keys[:-1])
        if (group, attempt) in attempts:
            raise ValueError(f"duplicate attempt {attempt} for {group}")
        attempts.add((group, attempt))
        for identity, status, duration in read_report(manifest.parent / entry["file"]):
            histories[group, identity].append((attempt, status, duration))

    candidates = []
    consistent = 0
    for (group, identity), observations in sorted(histories.items()):
        executed = sorted(obs for obs in observations if obs[1] != "skip")
        if len(executed) < 2:
            continue
        if len({obs[1] for obs in executed}) == 1:
            consistent += 1
            continue
        lineage, classname, case = identity
        candidates.append({
            "commit": group[0], "run": group[1], "job": group[2], "environment": group[3],
            "suite": list(lineage), "classname": classname, "test": case,
            "history": [{"attempt": a, "outcome": s} for a, s, _ in sorted(observations)],
            "repeat_case_seconds": float(sum(t for _, _, t in executed[1:])),
        })
    return {"reports": len(records), "retested_consistently": consistent, "candidates": candidates}


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-candidate", action="store_true", help="exit 1 on inconsistent outcomes")
    args = parser.parse_args(args)
    try:
        result = analyze(args.manifest)
    except (OSError, ValueError, TypeError, ET.ParseError, InvalidOperation, OverflowError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['reports']} reports | {len(result['candidates'])} inconsistent | "
              f"{result['retested_consistently']} consistent retests")
        for case in result["candidates"]:
            history = " -> ".join(f"{s['attempt']}:{s['outcome']}" for s in case["history"])
            print(f"{case['classname']}::{case['test']}  ({case['commit']} / {case['run']} / "
                  f"{case['job']} / {case['environment']})\n"
                  f"  {history}  |  repeat case time {case['repeat_case_seconds']:g}s")
    return 1 if args.fail_on_candidate and result["candidates"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
