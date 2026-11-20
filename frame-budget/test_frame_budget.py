import tempfile
import unittest
from pathlib import Path

from frame_budget import Frame, analyze, read_frames, render


class FrameBudgetTests(unittest.TestCase):
    def analyze_values(self, ms):
        return analyze([Frame(i, value, "field") for i, value in enumerate(ms)], 100)

    def test_budget_equality_and_first_tied_run(self):
        r = self.analyze_values([11, 12, 10, 13, 14])
        self.assertEqual(r["over_budget"], 4)
        self.assertEqual(r["longest_run"], {"start": 0, "end": 1, "frames": 2, "elapsed_ms": 23})

    def test_single_and_nearest_rank(self):
        self.assertIsNone(self.analyze_values([10])["longest_run"])
        r = self.analyze_values(list(range(1, 101)))
        self.assertEqual([r["p50_ms"], r["p95_ms"], r["p99_ms"]], [50, 95, 99])

    def test_read_rejects_gaps_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.csv"
            for rows in ("1,12,A\n3,11,A", "1,nan,A", "1,0,A"):
                path.write_text("frame,ms,phase\n" + rows)
                with self.assertRaises(ValueError):
                    read_frames(path)

    def test_report_escapes_user_text(self):
        frames = [Frame(1, 20, "<test>")]
        html = render(frames, analyze(frames, 60), "<title>")
        self.assertNotIn("(<test>)", html)
        self.assertIn("&lt;title&gt;", html)
        self.assertIn("&lt;test&gt;", html)

    def test_synthetic_capture(self):
        frames = read_frames(Path(__file__).parent / "examples/synthetic-orbit-run.csv")
        r = analyze(frames, 60)
        self.assertEqual(r["frames"], 96)
        self.assertEqual(r["longest_run"]["start"], 43)
        self.assertEqual(r["longest_run"]["end"], 50)
        self.assertEqual(r["over_budget"], 12)

    def test_bucket_count_is_bounded(self):
        frames = [Frame(i, 1 if i != 333 else 80, "test") for i in range(1000)]
        html = render(frames, analyze(frames, 60), "Long capture")
        self.assertEqual(html.count("<rect"), 300)
        self.assertIn("peak 80 ms at 333", html)


if __name__ == "__main__":
    unittest.main()
