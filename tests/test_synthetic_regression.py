import json
from dataclasses import asdict
from pathlib import Path

from benchcore.auditor import audit_items
from benchcore.checkers import DEFAULT_CHECKERS
from benchcore.defect_injection import inject_defects, score_injected_report
from benchcore.loader import build_items
from benchcore.schema import FieldMapping


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_audit_seed.jsonl"
MAPPING = FieldMapping(
    item_id="id",
    task="task",
    context=["context"],
    choices="choices",
    gold="gold",
    output_contract="output_contract",
    evaluator="evaluator",
)


def test_structural_mutation_recall_gate_is_perfect():
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
    mutations = inject_defects(
        rows,
        MAPPING,
        seed=20260713,
        mutations_per_item=10,
    )
    items = build_items([result.row for result in mutations], MAPPING)
    violations = audit_items(items, checkers=list(DEFAULT_CHECKERS), dataset_checkers=[])
    manifest = {"mutations": [asdict(result.provenance) for result in mutations]}
    report = {"violations": [asdict(violation) for violation in violations]}

    score = score_injected_report(manifest, report)

    structural = score["per_evidence_grade"]["structural"]
    assert structural["expected"] >= 7
    assert structural["recall"] == 1.0, score["misses"]
