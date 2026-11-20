import tempfile
import unittest
from pathlib import Path
from statistics import fmean

from transit_fold import load_csv, search, simulate, trial


class FoldTests(unittest.TestCase):
    def test_recovers_injected_period_despite_gap_and_noise(self):
        trials, best = search(simulate())
        self.assertEqual(251, len(trials))
        self.assertAlmostEqual(2.7, best.period, delta=.02)
        self.assertAlmostEqual(.016, best.depth, delta=.004)

    def test_flat_control_has_zero_gain(self):
        _, best = search([(i / 10, 1.) for i in range(100)], steps=11)
        self.assertEqual((best.score, best.depth), (0., 0.))

    def test_injection_strength_exceeds_same_noise_control(self):
        _, control = search(simulate(depth=0), steps=51)
        _, injected = search(simulate(), steps=51)
        self.assertGreater(injected.score, 10 * control.score)

    def test_phase_wrap_dip(self):
        times = [i / 80 for i in range(800)]
        flux = [0.98 if i % 80 in {78, 79, 0, 1} else 1. for i in range(800)]
        fit = trial(times, [f - fmean(flux) for f in flux], 1.)
        self.assertGreater(fit.depth, .014)
        self.assertLess(min(fit.center, 1-fit.center), .04)

    def test_short_baseline_rejected(self):
        with self.assertRaisesRegex(ValueError, "span"):
            search([(i / 100, 1.) for i in range(30)])

    def test_csv_sorted_and_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "curve.csv"
            path.write_text("time_days,flux\n2,0.9\n1,1.0\n")
            self.assertEqual(load_csv(path), [(1., 1.), (2., .9)])
            path.write_text("time_days,flux\n2,nan\n")
            with self.assertRaisesRegex(ValueError, "line 2"):
                load_csv(path)


if __name__ == "__main__":
    unittest.main()
