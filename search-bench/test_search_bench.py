import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from http.client import HTTPResponse
from pathlib import Path
from unittest.mock import Mock

from search_bench import HERE, evaluate, index_documents, make_handler, search


class SearchBenchTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.ids = index_documents(self.db, HERE / "documents.csv")

    def test_ranking_changes(self):
        self.assertEqual(search(self.db, "graphics lab", 1)[0]["id"], "d02")
        self.assertEqual(search(self.db, "graphics lab", 5)[0]["id"], "d01")

    def test_query_punctuation_is_literal(self):
        self.assertEqual(search(self.db, '"graphICs" (lab)*'), search(self.db, "graphics lab"))
        self.assertEqual(search(self.db, '""'), [])

    def test_metrics_include_misses(self):
        with redirect_stdout(io.StringIO()):
            base, weighted = evaluate(self.db, HERE / "judgments.csv", self.ids, 5, 3)
        self.assertAlmostEqual(base, 6.5 / 9)
        self.assertAlmostEqual(weighted, 8 / 9)

    def test_unknown_label_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            labels = Path(tmp) / "labels.csv"
            labels.write_text("query,relevant_id\nlab,d88\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unknown judged"):
                evaluate(self.db, labels, self.ids, 5, 3)

    def test_api_contract(self):
        handler = make_handler(self.db, 5, 3)
        for url, code in [("/search?q=graphics+lab", 200), ("/search", 400), ("/", 404)]:
            with self.subTest(url=url):
                # Exercise HTTP parsing and serialization with a memory transport.
                transport = Mock()
                transport.makefile.return_value = io.BytesIO(f"GET {url} HTTP/1.0\r\n\r\n".encode())
                wire = io.BytesIO()
                transport.sendall.side_effect = wire.write
                handler(transport, ("127.0.0.1", 12345), None)
                wire.seek(0)
                transport.makefile.return_value = wire
                response = HTTPResponse(transport)
                response.begin()
                self.assertEqual(response.status, code)
                result = json.loads(response.read())
                if code == 200:
                    self.assertEqual(result["hits"][0]["id"], "d01")
