from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from scripts import preflight_platinum_holdout_availability as preflight


def test_aggregate_counts_statuses_without_emitting_ids(tmp_path: Path) -> None:
    path = tmp_path / "test.parquet"
    pq.write_table(pa.Table.from_pylist([
        {"cleaning_status": "consensus", "id": "a", "question": "secret-a"},
        {"cleaning_status": "verified", "id": "b", "question": "secret-b"},
        {"cleaning_status": "revised", "id": "c", "question": "secret-c"},
        {"cleaning_status": "rejected", "id": "d", "question": "secret-d"},
    ]), path)
    result = preflight.aggregate_table("fixture", path)
    assert result["positive_rows"] == 2
    assert result["negative_rows"] == 2
    assert result["identity_duplicate_rows"] == 0
    serialized = json.dumps(result)
    assert "secret-" not in serialized
    assert '"a"' not in serialized


def test_duplicate_identity_fails_detection_gate() -> None:
    rows = [{
        "positive_rows": 100, "negative_rows": 300, "unknown_status_rows": 0,
        "identity_duplicate_rows": 1, "identity_missing_rows": 0,
    }] * 3
    assert preflight.decide_detection(rows) == "NOT_IDENTIFIABLE_ITEM_IDENTITY"


def test_detection_gate_requires_live_positives_and_negatives() -> None:
    passing = [{
        "positive_rows": 40, "negative_rows": 120, "unknown_status_rows": 0,
        "identity_duplicate_rows": 0, "identity_missing_rows": 0,
    }] * 3
    assert preflight.decide_detection(passing) == "PASS_DETECTION_HOLDOUT_SOURCE_AVAILABLE"
    no_positives = [{**row, "positive_rows": 0} for row in passing]
    assert preflight.decide_detection(no_positives) == "INSUFFICIENT_POSITIVE_PREVALENCE"


def test_unknown_label_fails_closed() -> None:
    rows = [{
        "positive_rows": 100, "negative_rows": 300, "unknown_status_rows": 1,
        "identity_duplicate_rows": 0, "identity_missing_rows": 0,
    }]
    assert preflight.decide_detection(rows) == "NOT_IDENTIFIABLE_DEFECT_LABELS"


def test_prompt_only_cache_does_not_claim_exact_item_join() -> None:
    caches = [{
        "safe_pickle": {"dangerous_opcode_counts": {}},
        "inspection": {"explicit_item_identity_present": False},
    }]
    assert preflight.decide_cache(caches, 100) == "NOT_IDENTIFIABLE_MODEL_OUTPUT_LINKAGE"


def test_dangerous_pickle_is_rejected_before_container_parse(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.pkl"
    path.write_bytes(b"cos\nsystem\n.")
    result = preflight.safe_pickle_opcodes(path)
    assert result["dangerous_opcode_counts"] == {"GLOBAL": 1}
