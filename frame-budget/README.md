# FrameBudget

**Where did the game stutter?** Inspect ordered frame durations from your game or renderer. A 60 FPS target gives each frame about 16.67 ms. FrameBudget finds isolated spikes, sustained slow sequences and the game phases in which they happen. It produces a standalone HTML timeline and JSON metrics.

## Run

Python 3.9+, standard library. From this folder:

```sh
python frame_budget.py examples/synthetic-orbit-run.csv --fps 60 --html report.html --title "Orbit run (synthetic capture)"
python -m unittest discover -v
```

Open `report.html` locally. The included **original synthetic fixture** represents a fictional game passing through a hangar, debris field and warp gate. Of 96 frames, 12 exceed the 60 FPS budget. Frame 15 is a 62 ms hitch. The longest over-budget sequence lasts eight frames, from 43 through 50, in the debris field. This example makes no claims about a real game's performance.

## Bring a capture

Export consecutive per-frame samples as CSV. `frame` is a nonnegative integer that increases by one, `ms` is the positive finite elapsed frame duration in milliseconds, and `phase` is your scene or activity label. Extra columns are ignored. Supply comparable, consistently measured timings. CPU or GPU work counters may differ from elapsed presentation time. Unity users can consult the [frame timing API counter reference](https://docs.unity3d.com/6000.0/Documentation/Manual/frame-timing-manager-counter-reference.html) to choose their measurement.

| Metric | Calculation |
|---|---|
| Achieved FPS | 1,000 divided by mean elapsed frame duration |
| p50 / p95 / p99 | Nearest-rank percentile of frame times in milliseconds |
| Over budget | Frame time strictly greater than 1,000 / target FPS |
| Longest run | Consecutive over-budget frame count. The earliest run wins ties, and the run can cross phases. |
| Elapsed run time | Sum of all frame durations in that run |

The timeline compresses long captures into at most 300 consecutive groups and plots the maximum in each, preserving isolated hitches. The phase table uses every original frame. Percentiles are descriptive and sensitive to sample size. FrameBudget locates a slowdown; identifying its cause requires profiler data. Invalid input or an unwritable report path exits with code 2.
