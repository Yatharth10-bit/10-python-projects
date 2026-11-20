"""Estimate a T20 chase probability at an over break, then audit it on later matches."""

import argparse
import csv
import json
import math
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from html import escape

from demo.synthetic import matches


@dataclass(frozen=True)
class State:
    match: str
    day: str
    target: int
    runs: int
    outs: int
    balls_left: int
    win: bool

    @property
    def pressure(self):
        return 6 * (self.target - self.runs) / self.balls_left


def snapshot(key, data, over):
    info = data["info"]
    if info.get("match_type") != "T20" or info.get("overs") != 20 or info.get("balls_per_over", 6) != 6:
        return None, "outside standard 20-over format"
    outcome = info["outcome"]
    innings = data["innings"]
    if len(innings) != 2 or "winner" not in outcome or outcome.get("method") or outcome.get("result"):
        return None, "unresolved, adjusted or extra innings"
    first, second = innings
    if (second.get("target", {}).get("overs", 20) != 20 or first.get("forfeited")
            or second.get("forfeited") or outcome["winner"] not in (first["team"], second["team"])):
        return None, "nonstandard chase"
    target = second.get("target", {}).get("runs")
    if target is None:
        extra = first.get("penalty_runs", {})
        target = 1 + extra.get("pre", 0) + extra.get("post", 0) + sum(
            d["runs"]["total"] for o in first["overs"] for d in o["deliveries"]
        )
    total = second.get("penalty_runs", {}).get("pre", 0)
    outs = 0
    blocks = second["overs"]
    # Use the recorded over boundaries. This also respects umpire miscounted overs.
    if len(blocks) <= over or [o["over"] for o in blocks[:over + 1]] != list(range(over + 1)):
        return None, "no live chase at this over"
    for block in blocks[:over]:
        for delivery in block["deliveries"]:
            total += delivery["runs"]["total"]
            outs += sum(w["kind"] not in ("retired hurt", "retired not out")
                        for w in delivery.get("wickets", []))
    if total >= target or outs >= 10:
        return None, "no live chase at this over"
    day = date.fromisoformat(info["dates"][0]).isoformat()
    return State(key, day, target, total, outs, 6 * (20 - over), outcome["winner"] == second["team"]), None


def records(path):
    if path is None:
        yield from matches()
    elif path.is_dir():
        for p in sorted(path.glob("*.json")):
            yield p.stem, json.loads(p.read_text(encoding="utf-8-sig"))
    elif path.suffix.lower() == ".json":
        yield path.stem, json.loads(path.read_text(encoding="utf-8-sig"))
    else:
        with zipfile.ZipFile(path) as archive:
            for key in sorted(archive.namelist()):
                if key.lower().endswith(".json"):
                    with archive.open(key) as stream:
                        yield key, json.load(stream)


def split_by_date(states):
    days = sorted({s.day for s in states})
    if len(days) < 2:
        raise ValueError("need eligible chases on at least two distinct dates")
    boundary = days[max(1, min(len(days) - 1, int(len(days) * 0.75)))]
    return [s for s in states if s.day < boundary], [s for s in states if s.day >= boundary]


def predict(train, state, k):
    # Units are explicit: one wicket of distance equals two required runs per over.
    near = sorted(train, key=lambda s: (
        math.hypot((s.pressure - state.pressure) / 2, s.outs - state.outs), s.match
    ))[:k]
    return (sum(s.win for s in near) + 1) / (len(near) + 2)


def evaluate(train, test, k):
    baseline = sum(s.win for s in train) / len(train)
    details = [(s, predict(train, s, k)) for s in test]
    model_error = sum((p - s.win) ** 2 for s, p in details) / len(test)
    base_error = sum((baseline - s.win) ** 2 for s in test) / len(test)
    return details, model_error, base_error


def draw(details, model, baseline, over, label):
    examples = details[:8]
    height = 188 + len(examples) * 42
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 {height}" role="img">',
        '<title>Held-out cricket forecasts and actual chase results</title>',
        f'<rect width="820" height="{height}" rx="18" fill="#131d33"/>',
        '<g font-family="system-ui, sans-serif" fill="#e6f0fa">',
        '<text x="32" y="46" font-size="30" font-weight="bold">Chase Replay</text>',
        f'<text x="32" y="77" font-size="16">{escape(label)} · At the end of over {over} · '
        f'{len(details)} held-out matches</text>',
        '<g font-size="13" fill="#afc2da"><text x="32" y="122">Match date</text>'
        '<text x="165" y="122">Score</text><text x="270" y="122">Estimated chase win probability</text>'
        '<text x="681" y="122">Outcome</text></g>',
    ]
    for i, (state, chance) in enumerate(examples):
        y = 150 + 42 * i
        color = "#7bddba" if state.win else "#f9bba1"
        svg.extend([
            f'<text x="32" y="{y+5}" font-size="15">{escape(state.day)}</text>',
            f'<text x="165" y="{y+5}" font-size="15">{state.runs}/{state.outs}</text>',
            f'<rect x="270" y="{y-7}" width="300" height="14" rx="7" fill="#2d3d5a"/>',
            f'<rect x="270" y="{y-7}" width="{300*chance:.1f}" height="14" rx="7" fill="#8ecfee"/>',
            f'<text x="590" y="{y+5}" font-size="15">{chance:.0%}</text>',
            f'<text x="681" y="{y+5}" font-size="15" fill="{color}">{"Won" if state.win else "Lost"}</text>',
        ])
    svg.append(f'<text x="32" y="{height-21}" font-size="15">Brier score on all held-out matches '
               f'(lower is better): model {model:.4f}, baseline {baseline:.4f}</text></g></svg>')
    return "\n".join(svg)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="Cricsheet JSON directory, ZIP, or match JSON")
    parser.add_argument("--over", type=int, default=10, help="completed overs, 1 through 19")
    parser.add_argument("--neighbors", type=int, default=7)
    parser.add_argument("--csv", type=Path, help="write all held-out match predictions")
    parser.add_argument("--svg", type=Path, help="write a preview of held-out predictions and outcomes")
    args = parser.parse_args()
    if not 1 <= args.over <= 19 or args.neighbors < 1:
        parser.error("--over must be 1–19 and --neighbors must be positive")
    states, skips = [], Counter()
    try:
        for key, data in records(args.data):
            state, reason = snapshot(key, data, args.over)
            if state is None:
                skips[reason] += 1
            else:
                states.append(state)
        train, test = split_by_date(states)
        details, model, baseline = evaluate(train, test, args.neighbors)
        if args.svg:
            label = "Imported match data" if args.data else "Synthetic demo"
            args.svg.write_text(draw(details, model, baseline, args.over, label), encoding="utf-8")
        if args.csv:
            with args.csv.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["match", "date", "runs", "wickets", "target", "forecast", "chase_won"])
                writer.writerows((s.match, s.day, s.runs, s.outs, s.target, round(p, 6), int(s.win))
                                 for s, p in details)
    except (KeyError, IndexError, TypeError, ValueError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"Chase Replay: {exc}\n")
    label = args.data or "fictional generated fixtures"
    print(f"Chase Replay | {label} | after over {args.over}")
    print(f"{len(train)} training matches through {max(s.day for s in train)}; "
          f"{len(test)} held-out matches from {min(s.day for s in test)}.")
    print(f"Brier score (lower is better): model {model:.4f}, training win-rate baseline {baseline:.4f}")
    print("Excluded:", dict(skips) or "none")
    print("\nHeld-out examples (first five)")
    for s, p in details[:5]:
        print(f"  {s.day} {s.match}: {s.runs}/{s.outs}, target {s.target} | "
              f"{p:.0%} forecast | chase {'won' if s.win else 'lost'}")


if __name__ == "__main__":
    main()
