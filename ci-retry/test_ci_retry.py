import json
import tempfile
import unittest
from pathlib import Path

from ci_retry import analyze, read_report


class RetryTests(unittest.TestCase):
    def setUp(self):
        self.demo = Path(__file__).parent / "examples" / "runs.json"

    def test_fixture_ignores_change_of_commit_and_skips(self):
        result = analyze(self.demo)
        self.assertEqual(result["retested_consistently"], 1)
        self.assertEqual([r["test"] for r in result["candidates"]], ["test_reservation"])
        self.assertEqual(result["candidates"][0]["repeat_case_seconds"], 2)

    def modified(self, transform):
        records = json.loads(self.demo.read_text())
        for item in records:
            item["file"] = str(self.demo.parent / item["file"])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.json"
            path.write_text(json.dumps(transform(records)), encoding="utf-8")
            return analyze(path)

    def test_environment_separates_results(self):
        def alter(rows):
            rows[1]["environment"] = "windows"
            return rows
        self.assertEqual(self.modified(alter)["candidates"], [])

    def test_order_independent(self):
        self.assertEqual(self.modified(lambda rows: rows[::-1]), analyze(self.demo))

    def test_duplicate_attempt_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate attempt"):
            self.modified(lambda rows: rows + [rows[0]])

    def test_duplicates_within_suite_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "r.xml"
            path.write_text('<testsuite><testcase name="x"/><testcase name="x"/></testsuite>')
            with self.assertRaisesRegex(ValueError, "duplicate testcase"):
                list(read_report(path))


if __name__ == "__main__":
    unittest.main()
