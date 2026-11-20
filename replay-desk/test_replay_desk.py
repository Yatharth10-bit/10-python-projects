import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

from replay_desk import inbox, process, receive, report


class ReplayTests(unittest.TestCase):
    def test_retry_after_partial_failure_and_duplicate_delivery(self):
        with inbox(":memory:") as db:
            event = {"id": "101", "shipment": "x"}
            receive(db, [event, event])
            self.assertEqual(process(db, "101", True), "simulated-failure")
            self.assertEqual(report(db)["shipment_scans"], [])
            self.assertEqual(process(db, "101"), "applied")
            self.assertEqual(process(db, "101"), "skipped-already-applied")
            receive(db, [{"id": "102", "shipment": "x"}])
            process(db, "102")
            result = report(db)
            self.assertEqual(result["inbox"][0]["deliveries"], 2)
            self.assertEqual(result["shipment_scans"][0]["scans"], 2)
            self.assertEqual(len(result["attempts"]), 4)

    def test_conflict_rejects_whole_batch(self):
        with inbox(":memory:") as db:
            with self.assertRaises(ValueError):
                receive(db, [{"id": "abc", "shipment": "x"}, {"id": "abc", "shipment": "y"}])
            self.assertEqual(report(db)["inbox"], [])

    def test_worker_race(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "db.sqlite3"
            with inbox(path) as db:
                receive(db, [{"id": "one", "shipment": "s"}])
            barrier = Barrier(4)
            def run(_):
                with inbox(path) as db:
                    barrier.wait(timeout=10)
                    return process(db, "one")
            with ThreadPoolExecutor(max_workers=4) as pool:
                outcomes = list(pool.map(run, range(4)))
            self.assertEqual(outcomes.count("applied"), 1)
            self.assertEqual(outcomes.count("skipped-already-applied"), 3)
