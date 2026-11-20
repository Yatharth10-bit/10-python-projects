"""Scan unevenly sampled brightness measurements for repeating dips."""

import argparse
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
from statistics import fmean


PHASE_BINS = 80
WIDTHS = (2, 4, 6, 8)


@dataclass(frozen=True)
class Trial:
    period: float
    score: float
    depth: float
    center: float


def simulate(seed=17, depth=0.016, period=2.7):
    """Generate 18 days of noisy relative flux, including an observing gap."""
    rng = random.Random(seed)
    result = []
    for i in range(900):
        time = i / 50 + rng.uniform(0, 0.005)
        if 7 < time < 8.2:
            continue
        distance = abs(((time / period - 0.37 + 0.5) % 1) - 0.5)
        flux = 1 - depth * (distance < 0.035) + rng.gauss(0, 0.002)
        result.append((time, flux))
    return result


def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"time_days", "flux"}.issubset(reader.fieldnames or []):
            raise ValueError("Include the column headers time_days and flux.")
        rows = []
        for row in reader:
            try:
                pair = float(row["time_days"]), float(row["flux"])
                if not all(map(math.isfinite, pair)):
                    raise ValueError()
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid measurement on CSV line {reader.line_num}.") from exc
            rows.append(pair)
    return sorted(rows)


def trial(times, deviations, period):
    counts, sums = [0] * PHASE_BINS, [0.] * PHASE_BINS
    for time, value in zip(times, deviations):
        index = int((time % period) / period * PHASE_BINS) % PHASE_BINS
        counts[index] += 1
        sums[index] += value
    # Doubled bins make a dip crossing phase zero an ordinary contiguous window.
    total = len(times)
    total_flux = sum(sums)
    counts += counts
    sums += sums
    best = Trial(period, 0., 0., 0.)
    for width in WIDTHS:
        inside = sum(counts[:width])
        inside_flux = sum(sums[:width])
        for start in range(PHASE_BINS):
            outside = total - inside
            if inside >= 3 and outside >= 3:
                depth = (total_flux - inside_flux) / outside - inside_flux / inside
                gain = max(0., depth) ** 2 * inside * outside / total
                if gain > best.score:
                    center = ((start + width / 2) / PHASE_BINS) % 1
                    best = Trial(period, gain, depth, center)
            inside += counts[start + width] - counts[start]
            inside_flux += sums[start + width] - sums[start]
    return best


def search(rows, low=1.5, high=4., steps=251):
    if not 0 < low < high or not math.isfinite(high) or not 2 <= steps <= 5000:
        raise ValueError("Choose finite positive ordered periods and 2–5000 grid points.")
    if len(rows) < 20:
        raise ValueError("Provide at least 20 measurements.")
    times, flux = zip(*rows)
    origin = min(times)
    if max(times) - origin < 2 * high:
        raise ValueError("Observation span must cover twice the maximum trial period.")
    times = [t - origin for t in times]
    center = fmean(flux)
    deviations = [v - center for v in flux]
    trials = [trial(times, deviations, low + (high-low)*i/(steps-1)) for i in range(steps)]
    return trials, max(trials, key=lambda item: item.score)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, help="UTF-8 CSV with time_days and flux headers")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--min-period", type=float, default=1.5)
    parser.add_argument("--max-period", type=float, default=4.)
    parser.add_argument("--steps", type=int, default=251)
    parser.add_argument("--output", type=Path, default=Path("transit-report.html"))
    args = parser.parse_args()
    try:
        rows = load_csv(args.csv) if args.csv else simulate(args.seed)
        trials, best = search(rows, args.min_period, args.max_period, args.steps)
        description = ("Imported CSV" if args.csv else
                       f"Synthetic injection · 2.700 days · seed {args.seed}")
        data = {"label": description, "rows": rows, "best": trials.index(best),
                "trials": [[t.period, t.score, t.depth, t.center] for t in trials]}
        page = Path(__file__).with_name("viewer.html").read_text(encoding="utf-8")
        args.output.write_text(page.replace("/*DATA*/null", json.dumps(data)), encoding="utf-8")
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(2, f"{exc}\n")
    if best.score:
        print(f"Best grid period {best.period:.3f} days | depth {best.depth:.5f} flux units")
    else:
        print("No measurable dip on the trial grid.")
    print(f"{len(rows)} samples | {len(trials)} periods | {args.output}")


if __name__ == "__main__":
    main()
