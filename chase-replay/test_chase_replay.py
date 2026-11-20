import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from chase_replay import evaluate, predict, records, snapshot, split_by_date


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.matches = list(records(None))
        self.states = [s for k, m in self.matches if (s := snapshot(k, m, 10)[0])]

    def test_chronological_split_and_brier(self):
        train, test = split_by_date(self.states)
        self.assertLess(max(s.day for s in train), min(s.day for s in test))
        self.assertTrue({s.match for s in train}.isdisjoint(s.match for s in test))
        details, model, base = evaluate(train, test, 7)
        self.assertEqual(len(details), len(test))
        self.assertTrue(0 <= model <= 1 and 0 <= base <= 1)
        self.assertTrue(all(0 < p < 1 for _, p in details))

    def test_future_deliveries_do_not_affect_features(self):
        key, data = self.matches[0]
        original, _ = snapshot(key, data, 10)
        changed = copy.deepcopy(data)
        changed["innings"][1]["overs"][10]["deliveries"][0]["runs"]["total"] += 30
        self.assertEqual(snapshot(key, changed, 10)[0], original)

    def test_wide_and_retired_hurt(self):
        key, data = self.matches[0]
        original, _ = snapshot(key, data, 10)
        data["innings"][1]["overs"][0]["deliveries"].append({
            "runs": {"total": 1}, "extras": {"wides": 1}, "wickets": [{"kind": "retired hurt"}]
        })
        updated, _ = snapshot(key, data, 10)
        self.assertEqual((updated.runs, updated.outs, updated.balls_left),
                         (original.runs + 1, original.outs, original.balls_left))

    def test_rain_rule_exclusion_and_zip(self):
        key, data = self.matches[0]
        data["info"]["outcome"]["method"] = "D/L"
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "matches.zip"
            with zipfile.ZipFile(p, "w") as archive:
                archive.writestr(key + ".json", json.dumps(data))
                archive.writestr("README.txt", "sample")
            [(name, loaded)] = list(records(p))
            self.assertIsNone(snapshot(name, loaded, 10)[0])

    def test_single_neighbor_smoothing(self):
        s = self.states[0]
        self.assertAlmostEqual(predict([s], s, 1), (s.win + 1) / 3)


if __name__ == "__main__":
    unittest.main()
