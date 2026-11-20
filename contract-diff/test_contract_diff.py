import copy
import unittest
from pathlib import Path

from contract_diff import changes, read_spec


class ContractTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).parent / "examples"
        self.old = read_spec(base / "v1.json")
        self.new = read_spec(base / "v2.json")

    def test_fixture(self):
        rows = changes(self.old, self.new)
        self.assertEqual({r["reason"] for r in rows}, {"New required input", "Possible output enum widened"})

    def test_reverse_is_compatible(self):
        self.assertEqual(changes(self.new, self.old), [])

    def test_operation_removal(self):
        spec = copy.deepcopy(self.old)
        spec["paths"].clear()
        self.assertEqual(changes(self.old, spec)[0]["reason"], "Endpoint removed")

    def test_unchanged_recursive_schema(self):
        schema = self.old["components"]["schemas"]["Ticket"]
        schema["properties"]["parent"] = {"$ref": "#/components/schemas/Ticket"}
        self.assertEqual(changes(self.old, copy.deepcopy(self.old)), [])

    def test_constraint_needs_manual_review(self):
        self.new = copy.deepcopy(self.old)
        self.new["components"]["schemas"]["Ticket"]["properties"]["name"]["minLength"] = 5
        self.assertEqual(changes(self.old, self.new)[0]["level"], "review")


if __name__ == "__main__":
    unittest.main()
