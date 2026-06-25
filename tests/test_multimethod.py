from pathlib import Path
import unittest

from benchcore.auditor import audit_items
from benchcore.checkers import DEFAULT_CHECKERS
from benchcore.loader import build_items, load_mapping, load_rows
from benchcore.methods import DEFAULT_DATASET_CHECKERS, DEFAULT_METHOD_CHECKERS


class MultiMethodAuditTest(unittest.TestCase):
    def test_multimethod_findings(self) -> None:
        path = Path("examples/sample_multimethod_benchmark.jsonl")
        rows = load_rows(path)
        mapping = load_mapping(None, rows)
        items = build_items(rows, mapping)
        violations = audit_items(
            items,
            root=path.parent,
            checkers=[*DEFAULT_CHECKERS, *DEFAULT_METHOD_CHECKERS],
            dataset_checkers=DEFAULT_DATASET_CHECKERS,
        )
        defect_types = {v.defect_type for v in violations}
        self.assertIn("conflicting_duplicate_oracle", defect_types)
        self.assertIn("output_evaluator_contract_mismatch", defect_types)
        self.assertIn("overstrict_evaluator", defect_types)
        self.assertIn("metamorphic_inconsistency", defect_types)


if __name__ == "__main__":
    unittest.main()
