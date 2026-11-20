"""Find sustained slow frames in an ordered game-performance capture."""

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path


@dataclass(frozen=True)
class Frame:
    number: int
    ms: float
    phase: str


def read_frames(path):
    frames = []
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"frame", "ms", "phase"}
        if not required <= set(reader.fieldnames or ()):
            raise ValueError("expected CSV columns: frame,ms,phase")
        for row in reader:
            try:
                frame = Frame(int(row["frame"]), float(row["ms"]), row["phase"].strip())
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"line {reader.line_num}: invalid frame, ms or phase") from exc
            if frame.number < 0 or not frame.phase or not math.isfinite(frame.ms) or frame.ms <= 0:
                raise ValueError(f"line {reader.line_num}: invalid frame, ms or phase")
            if frames and frame.number != frames[-1].number + 1:
                raise ValueError(f"line {reader.line_num}: frame numbers must be consecutive")
            frames.append(frame)
    if not frames:
        raise ValueError("capture contains no frames")
    return frames


def metrics(values, budget):
    ordered = sorted(values)
    count = len(ordered)
    result = {"frames": count, "over_budget": sum(v > budget for v in values),
              "achieved_fps": 1000 / (math.fsum(values) / count)}
    for p in (50, 95, 99):
        result[f"p{p}_ms"] = ordered[(p * count + 99) // 100 - 1]
    return result


def analyze(frames, fps):
    if not math.isfinite(fps) or fps <= 0 or not math.isfinite(1000 / fps):
        raise ValueError("target FPS must give a positive finite frame budget")
    budget = 1000 / fps
    phases = defaultdict(list)
    best_start, best_size, size = 0, 0, 0
    for index, frame in enumerate(frames):
        phases[frame.phase].append(frame.ms)
        size = size + 1 if frame.ms > budget else 0
        if size > best_size:
            best_start, best_size = index - size + 1, size
    longest = None
    if best_size:
        run = frames[best_start:best_start + best_size]
        longest = {"start": run[0].number, "end": run[-1].number, "frames": best_size,
                   "elapsed_ms": math.fsum(f.ms for f in run)}
    return {"target_fps": fps, "budget_ms": budget,
            **metrics([f.ms for f in frames], budget), "longest_run": longest,
            "phases": {name: metrics(times, budget) for name, times in phases.items()}}


def timeline(frames, budget):
    # Keep isolated hitches visible even when the capture exceeds the chart width.
    width, height, pad = 920, 215, 48
    plot_width = width - 2 * pad
    count = min(len(frames), 300)
    ceiling = max(budget, max(f.ms for f in frames)) * 1.10

    def y(value):
        return height - 25 - (value / ceiling) * (height - 45)

    marks = []
    for i in range(count):
        chunk = frames[i * len(frames) // count:(i + 1) * len(frames) // count]
        peak = max(chunk, key=lambda frame: frame.ms)
        color = "#e38436" if peak.ms > budget else "#227a76"
        bar_top = y(peak.ms)
        label = escape(f"Frames {chunk[0].number}–{chunk[-1].number}: "
                       f"peak {peak.ms:g} ms at {peak.number} ({peak.phase})")
        marks.append(f'<rect x="{pad+i*plot_width/count:.2f}" y="{bar_top:.2f}" '
                     f'width="{plot_width/count*0.88:.2f}" height="{height-25-bar_top:.2f}" '
                     f'fill="{color}"><title>{label}</title></rect>')
    line = y(budget)
    return (f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Peak frame times in '
            f'capture order; dashed line marks the frame budget">{"".join(marks)}'
            f'<path d="M {pad} {line:.2f} H {width-pad}" fill="none" stroke="#253243" stroke-dasharray="5 4"/>'
            f'<text x="2" y="{line+4:.2f}">{budget:.1f}</text>'
            f'<text x="{pad}" y="{height-3}">Frame {frames[0].number}</text>'
            f'<text x="{width-pad}" y="{height-3}" text-anchor="end">{frames[-1].number}</text></svg>')


def render(frames, report, title):
    row_html = []
    for phase, m in report["phases"].items():
        row_html.append(f'<tr><td>{escape(phase)}</td><td>{m["frames"]}</td><td>{m["over_budget"]}</td>'
                        f'<td>{m["p50_ms"]:.2f}</td><td>{m["p95_ms"]:.2f}</td><td>{m["p99_ms"]:.2f}</td></tr>')
    run = report["longest_run"]
    longest = (f'{run["frames"]} consecutive frames ({run["start"]}–{run["end"]}) '
               f'spanning {run["elapsed_ms"]:.1f} ms' if run else "All frames met the target")
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} | FrameBudget</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f5f5ed;color:#14292c;font:16px/1.5 system-ui,sans-serif}}
main{{max-width:980px;margin:auto;padding:5vw 4vw}}h1{{font-size:clamp(2rem,6vw,4.2rem);line-height:1.05;margin:0 0 24px}}
h2{{font-size:1.18rem;margin-top:1.9rem}}figure{{margin:0;background:white;padding:14px;border:1px solid #acbbb7}}
svg{{width:100%;height:auto}}svg text{{font:12px system-ui;fill:#253243}}figcaption{{font-size:.86rem}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th,td{{text-align:right;padding:8px;border-bottom:1px solid #c4cdca}}
th:first-child,td:first-child{{text-align:left}}.scroll{{overflow-x:auto}}.stats{{color:#12655f;font-weight:650}}
</style><main><h1>{escape(title)}</h1><p class="stats">{report["frames"]} frames · {report["achieved_fps"]:.1f} achieved FPS ·
 {report["over_budget"]} over budget at {report["target_fps"]:g} FPS</p>
<h2>Frame times in capture order</h2><figure>{timeline(frames, report["budget_ms"])}
<figcaption>Height gives peak frame time in milliseconds. Orange exceeds the dashed budget of {report["budget_ms"]:.2f} ms.
Each bar represents one frame or, on longer captures, a consecutive group. Hover to read its peak.</figcaption></figure>
<h2>Longest over-budget run</h2><p>{longest}.</p><h2>Phase comparison</h2><div class="scroll"><table>
<thead><tr><th>Phase</th><th>Frames</th><th>Over budget</th><th>p50 ms</th><th>p95 ms</th><th>p99 ms</th></tr></thead>
<tbody>{''.join(row_html)}</tbody></table></div></main></html>"""


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture")
    parser.add_argument("--fps", type=float, default=60)
    parser.add_argument("--html", type=Path, help="write a standalone HTML timeline")
    parser.add_argument("--title", help="title of HTML report; defaults to capture filename")
    opts = parser.parse_args(args)
    try:
        frames = read_frames(opts.capture)
        report = analyze(frames, opts.fps)
        if opts.html:
            if opts.html.resolve() == Path(opts.capture).resolve():
                raise ValueError("HTML output must differ from the capture")
            opts.html.write_text(render(frames, report, opts.title or Path(opts.capture).stem),
                                 encoding="utf-8")
    except (ValueError, OSError, OverflowError, csv.Error) as exc:
        print(f"Input/output error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
