import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from batch_proof import EXAMPLES, paise, reconcile


class ReconciliationTests(unittest.TestCase):
    def test_equal_totals_hide_two_errors(self):
        result = reconcile(EXAMPLES / "expected.csv", EXAMPLES / "received.csv")
        self.assertEqual(result["parseable_amounts_with_id_paise"]["received_minus_expected"], 0)
        self.assertEqual(result["invoice_counts"], {"matched": 1, "mismatch": 2})
        self.assertFalse(result["clean"])

    def test_classification_and_quarantine(self):
        with TemporaryDirectory() as folder:
            left, right = Path(folder) / "a", Path(folder) / "b"
            left.write_text("invoice_id,amount\nA,1\nA,1\nB,2\nC,x\nD,-0.05\n,3\n", encoding="utf-8")
            right.write_text("amount,invoice_id\n-0.05,D\n2,Z\n3,C\n", encoding="utf-8")
            result = reconcile(left, right)
            self.assertEqual(result["invoice_counts"],
                             {"duplicate": 1, "missing": 1, "invalid": 1, "matched": 1, "unexpected": 1})
            self.assertEqual(len(result["rejected_rows"]["expected"]), 2)
            right.write_text("amount,wrong\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                reconcile(left, right)

    def test_exact_money_and_input_precision(self):
        self.assertEqual(paise("120000000000000.01"), 12000000000000001)
        self.assertEqual(paise("-0.5"), -50)
        for value in ["1.111", "NaN", "1e6", "", "1,000"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                paise(value)

    def test_clean_and_row_order_independent(self):
        with TemporaryDirectory() as folder:
            other = Path(folder) / "received.csv"
            other.write_text("invoice_id,amount\nLAB-42,250\nLAB-43,450\nLAB-41,100\n", encoding="utf-8")
            self.assertTrue(reconcile(EXAMPLES / "expected.csv", other)["clean"])
