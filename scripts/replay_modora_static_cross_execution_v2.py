#!/usr/bin/env python3
"""Replay MoDora library-level complementarity after production checker fixes.

This is deliberately not a ``benchcore audit`` entry point.  The product
rejects the source result exports; this research replay constructs canonical
items with a frozen adapter and invokes a frozen checker subset directly.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchcore.auditor import audit_items_with_ledger
from benchcore.checkers import DEFAULT_CHECKERS
from benchcore.input_domain import UnsupportedAuditInput, enforce_audit_input_domain
from benchcore.loader import load_rows
from benchcore.methods import DEFAULT_DATASET_CHECKERS, DEFAULT_METHOD_CHECKERS


PRODUCTION_COMMIT = "092a2585c37fd40c77838f535e6d29f70e8fecbf"
FROZEN_CODE_SHA256 = {
    "benchcore/checkers.py": "4c2641c7b4fba452ecd0163c8e6ec911f1dbbf62d57c2f55f66687bb95e38000",
    "benchcore/methods.py": "e35f668fbc0391d52032cdedc6aa8dae7a59a0330607d685aee5e38367441071",
    "benchcore/auditor.py": "424bd594619dcadff2d69f31f1e1df2d5c46fc380f19db6229cf5c89a5aae2d9",
    "benchcore/schema.py": "1015e091e3fbbe10cc26d165dbdc4fec4e3f3966463013e3403bba7883249870",
    "benchcore/promotion.py": "312b0c60637e025058a0603a5dc59a16d96df6b13ba76ad4350f821048be2e53",
    "benchcore/oracle_text.py": "89a70fdce316690ba232ca71fb356ad264d8e73b5dac77addca8d8d921823d97",
    "benchcore/decision_policy.py": "9fc10ba62a250b741c3c812ed9fa41539fd5a4999434e84e029f8ac2cd9cff15",
    "benchcore/input_domain.py": "56cd6080d29f1415d95cd5133fec9f7f6f37fe14288275e703fd8678bf7b0e8a",
    "scripts/mine_modora_defects.py": "3bf48bd13504b502407d0f16a48ceb266994ba7e96b23b3b3fe5dd19ed0772fb",
    "scripts/analyze_modora_static_cross_execution.py": "30c8add3943a6d882e91bf966c148ece1908f8970915c11f2cc2c8be95c8ab85",
}
FROZEN_MINING_RECEIPT_SHA256 = (
    "d91f471330eecf1849dff6b88b43e3092360196dd21040600cafd443cdfcaad2"
)
FROZEN_V1_RECEIPT_SHA256 = (
    "fb9c1d996653a9a009c4f41f73e8a517ad4a5d8747eefbe34e0a5074c25747dc"
)
COMPATIBLE_ITEM_CHECKERS = {
    "task_specification",
    "context_attachment",
    "oracle_ground_truth",
    "task_integrity",
}
COMPATIBLE_DATASET_CHECKERS = {"duplicate_conflict", "schema_drift"}
AVAILABILITY_DEFECT_TYPES = {
    "missing_context",
    "context_version_mismatch_risk",
    "source_reference_missing",
    "inaccessible_attachment",
}
CONTINGENCY_SPECS = (
    ("static_intrinsic_x_cross_execution", "static_intrinsic", "cross_execution_hit"),
    ("static_any_x_cross_execution", "static_any_compatible", "cross_execution_hit"),
    ("static_intrinsic_x_mining_layer", "static_intrinsic", "mining_layer_hit"),
    ("static_any_x_mining_layer", "static_any_compatible", "mining_layer_hit"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).casefold()
    if text == "true":
        return True
    if text == "false":
        return False
    raise ValueError(f"not a frozen boolean: {value!r}")


def verify_frozen_code(repo_root: Path) -> dict[str, str]:
    actual = {}
    for relative, expected in FROZEN_CODE_SHA256.items():
        digest = sha256_file(repo_root / relative)
        if digest != expected:
            raise RuntimeError(
                f"frozen code hash mismatch for {relative}: {digest} != {expected}"
            )
        actual[relative] = digest
    return actual


def verify_receipt(path: Path, expected_sha256: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required receipt missing: {path}")
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise RuntimeError(f"receipt hash mismatch for {path}: {actual} != {expected_sha256}")
    return json.loads(path.read_text(encoding="utf-8"))


def verify_v1_outputs(v1_receipt_path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    receipt = verify_receipt(v1_receipt_path, FROZEN_V1_RECEIPT_SHA256)
    if receipt.get("schema_version") != "modora-static-cross-execution-complementarity-v1":
        raise RuntimeError("unexpected V1 complementarity receipt schema")
    output_dir = v1_receipt_path.parent
    verified = {}
    for filename, expected in sorted(receipt.get("output_sha256", {}).items()):
        path = output_dir / filename
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"V1 output hash mismatch for {filename}: {actual} != {expected}")
        verified[filename] = actual
    required = {"item_channels.csv", "static_findings.csv", "contingency_cells.csv"}
    if not required <= set(verified):
        raise RuntimeError(f"V1 receipt does not bind required outputs: {sorted(required - set(verified))}")
    return receipt, verified


def verify_product_refusal(
    miner: ModuleType,
    input_dir: Path,
) -> list[dict[str, Any]]:
    results = []
    for method, filename in miner.METHOD_FILES.items():
        path = input_dir / filename
        rows = load_rows(path)
        try:
            enforce_audit_input_domain(rows)
        except UnsupportedAuditInput as exc:
            results.append(
                {
                    "method": method,
                    "filename": filename,
                    "rows": len(rows),
                    "refused": True,
                    "schema_version": exc.refusal.schema_version,
                }
            )
        else:
            raise RuntimeError(f"product input-domain guard did not refuse {filename}")
    return results


def run_static_v2(old: ModuleType, items: list[Any]) -> dict[str, Any]:
    all_item_checkers = list(DEFAULT_CHECKERS) + list(DEFAULT_METHOD_CHECKERS)
    compatible = old.select_named(all_item_checkers, COMPATIBLE_ITEM_CHECKERS)
    compatible_dataset = old.select_named(
        DEFAULT_DATASET_CHECKERS, COMPATIBLE_DATASET_CHECKERS
    )
    result = audit_items_with_ledger(
        items,
        checkers=compatible,
        dataset_checkers=compatible_dataset,
        fail_fast=True,
    )
    failed = [entry for entry in result.ledger if entry.status == "operational_failed"]
    if failed:
        raise RuntimeError(f"V2 static library replay had operational failures: {failed[:3]}")

    finding_rows = []
    any_ids: set[int] = set()
    intrinsic_ids: set[int] = set()
    availability_ids: set[int] = set()
    for finding in result.violations:
        channel = (
            "availability_metadata"
            if finding.defect_type in AVAILABILITY_DEFECT_TYPES
            else "intrinsic"
        )
        for question_id in old.target_ids(finding):
            any_ids.add(question_id)
            if channel == "intrinsic":
                intrinsic_ids.add(question_id)
            else:
                availability_ids.add(question_id)
            finding_rows.append(
                {
                    "questionId": question_id,
                    "channel": channel,
                    "checker": finding.detection_method,
                    "defect_type": finding.defect_type,
                    "severity": finding.severity,
                    "review_only": finding.review_only,
                    "evidence_tier": finding.evidence_tier,
                    "message": finding.message,
                    "source_finding_item_id": finding.item_id,
                }
            )
    finding_rows.sort(
        key=lambda row: (
            row["questionId"],
            row["channel"],
            row["defect_type"],
            str(row["source_finding_item_id"]),
        )
    )
    return {
        "finding_rows": finding_rows,
        "any_ids": any_ids,
        "intrinsic_ids": intrinsic_ids,
        "availability_ids": availability_ids,
        "summary": {
            "findings_before_target_expansion": len(result.violations),
            "expanded_rows": len(finding_rows),
            "hit_items": len(any_ids),
            "intrinsic_hit_items": len(intrinsic_ids),
            "availability_hit_items": len(availability_ids),
            "finding_types": dict(
                sorted(Counter(v.defect_type for v in result.violations).items())
            ),
            "ledger_status": dict(
                sorted(Counter(entry.status for entry in result.ledger).items())
            ),
        },
    }


def cell_for(row: Mapping[str, Any], static_field: str, external_field: str) -> str:
    static = parse_bool(row[static_field])
    external = parse_bool(row[external_field])
    return "A" if static and external else "B" if external else "C" if static else "D"


def build_coverage_migrations(
    old_rows: Sequence[Mapping[str, Any]],
    new_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    old_by_id = {int(row["questionId"]): row for row in old_rows}
    new_by_id = {int(row["questionId"]): row for row in new_rows}
    if set(old_by_id) != set(new_by_id) or set(new_by_id) != set(range(1, 1066)):
        raise RuntimeError("V1/V2 item-channel identity mismatch")
    migrations = []
    for name, static_field, external_field in CONTINGENCY_SPECS:
        for question_id in sorted(new_by_id):
            v1_cell = cell_for(old_by_id[question_id], static_field, external_field)
            v2_cell = cell_for(new_by_id[question_id], static_field, external_field)
            migrations.append(
                {
                    "comparison": name,
                    "questionId": question_id,
                    "v1_cell": v1_cell,
                    "v2_cell": v2_cell,
                    "transition": f"{v1_cell}->{v2_cell}",
                    "changed": v1_cell != v2_cell,
                }
            )
    return migrations


def finding_key(row: Mapping[str, Any]) -> tuple[int, str, str]:
    return (
        int(row["questionId"]),
        str(row["defect_type"]),
        str(row["source_finding_item_id"]),
    )


def build_evidence_migrations(
    old_rows: Sequence[Mapping[str, Any]],
    new_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    old_by_key = {finding_key(row): row for row in old_rows}
    new_by_key = {finding_key(row): row for row in new_rows}
    if len(old_by_key) != len(old_rows) or len(new_by_key) != len(new_rows):
        raise RuntimeError("duplicate expanded static-finding migration key")
    output = []
    for key in sorted(set(old_by_key) | set(new_by_key)):
        old = old_by_key.get(key)
        new = new_by_key.get(key)
        v1_tier = "" if old is None else str(old["evidence_tier"])
        v2_tier = "" if new is None else str(new["evidence_tier"])
        v1_review = "" if old is None else str(old["review_only"])
        v2_review = "" if new is None else str(new["review_only"])
        v1_severity = "" if old is None else str(old["severity"])
        v2_severity = "" if new is None else str(new["severity"])
        changed = (
            old is None
            or new is None
            or (v1_tier, v1_review, v1_severity)
            != (v2_tier, v2_review, v2_severity)
        )
        output.append(
            {
                "questionId": key[0],
                "defect_type": key[1],
                "source_finding_item_id": key[2],
                "v1_present": old is not None,
                "v2_present": new is not None,
                "v1_evidence_tier": v1_tier,
                "v2_evidence_tier": v2_tier,
                "v1_review_only": v1_review,
                "v2_review_only": v2_review,
                "v1_severity": v1_severity,
                "v2_severity": v2_severity,
                "changed": changed,
            }
        )
    return output


def contingency_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        name: {
            row["cell"]: int(row["count"])
            for row in rows
            if row["comparison"] == name
        }
        for name, _, _ in CONTINGENCY_SPECS
    }


def transition_counts_by_comparison(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    return {
        name: dict(
            sorted(
                Counter(
                    row["transition"]
                    for row in rows
                    if row["comparison"] == name
                ).items()
            )
        )
        for name, _, _ in CONTINGENCY_SPECS
    }


def validate_anchors(
    product_refusals: Sequence[Mapping[str, Any]],
    static: Mapping[str, Any],
    item_rows: Sequence[Mapping[str, Any]],
    contingency: Sequence[Mapping[str, Any]],
    coverage_migrations: Sequence[Mapping[str, Any]],
    evidence_migrations: Sequence[Mapping[str, Any]],
) -> dict[str, bool]:
    items = {int(row["questionId"]): row for row in item_rows}
    grids = contingency_counts(contingency)
    mining = grids["static_intrinsic_x_mining_layer"]
    cross = grids["static_intrinsic_x_cross_execution"]
    b_to_a = {
        int(row["questionId"])
        for row in coverage_migrations
        if row["comparison"] == "static_intrinsic_x_mining_layer"
        and row["transition"] == "B->A"
    }
    q895_q896 = [
        row
        for row in evidence_migrations
        if int(row["questionId"]) in {895, 896}
        and row["defect_type"] == "conflicting_duplicate_oracle"
    ]
    return {
        "nine_method_files_refused_by_product_boundary": len(product_refusals) == 9
        and all(row["refused"] for row in product_refusals),
        "canonical_items_1065": len(item_rows) == 1065
        and set(items) == set(range(1, 1066)),
        "all_four_v2_contingencies_partition_1065": len(contingency) == 16
        and all(sum(grid.values()) == 1065 for grid in grids.values()),
        "mining_layer_grid_3_15_14_1033": mining
        == {"A": 3, "B": 15, "C": 14, "D": 1033},
        "strict_cross_execution_does_not_claim_invisible_overlap": cross
        == {"A": 0, "B": 15, "C": 17, "D": 1033},
        "invisible_gold_three_are_static_confirmed": all(
            items[qid]["static_intrinsic"]
            and items[qid]["artifact_sidecar_invisible_gold"]
            and not items[qid]["cross_execution_hit"]
            for qid in (853, 854, 1048)
        ),
        "coverage_b_to_a_exactly_three_invisible_items": b_to_a == {853, 854, 1048},
        "q895_q896_evidence_confirmed_to_review": len(q895_q896) == 2
        and all(
            row["v1_evidence_tier"] == "confirmed"
            and row["v2_evidence_tier"] == "review"
            and row["v1_review_only"] == "False"
            and row["v2_review_only"] == "True"
            for row in q895_q896
        ),
        "static_intrinsic_items_17": static["summary"]["intrinsic_hit_items"] == 17,
    }


def render_findings(
    v1_contingency: Sequence[Mapping[str, Any]],
    v2_contingency: Sequence[Mapping[str, Any]],
    coverage_migrations: Sequence[Mapping[str, Any]],
    evidence_migrations: Sequence[Mapping[str, Any]],
) -> str:
    v1 = contingency_counts(v1_contingency)
    v2 = contingency_counts(v2_contingency)
    changed_coverage = [row for row in coverage_migrations if row["changed"]]
    changed_evidence = [row for row in evidence_migrations if row["changed"]]
    mining_name = "static_intrinsic_x_mining_layer"
    cross_name = "static_intrinsic_x_cross_execution"
    return "\n".join(
        [
            "# MoDora 静态与跨执行审计互补性 V2 重放",
            "",
            "> 结果知情、零 API、无 PDF 的修复后确定性重放。命中不自动等于真缺陷。",
            "",
            "## 1. 这不是 audit 产品对 result export 的审计",
            "",
            "九份 MoDora 文件均被 `result-export-refusal-v1` 显式拒绝。本轮没有调用 `benchcore audit`；研究脚本使用冻结 adapter 构造 canonical item，并直接调用 schema-compatible checker 库。输入域防线未被绕过、放宽或增加例外。",
            "",
            "## 2. 覆盖迁移：mining layer",
            "",
            f"V1 static-intrinsic × mining-layer：`{json.dumps(v1[mining_name], sort_keys=True)}`。",
            f"V2 static-intrinsic × mining-layer：`{json.dumps(v2[mining_name], sort_keys=True)}`。",
            "",
            "`q853/q854/q1048` 从 B→A：外部 artifact-sidecar 暴露的 U+200B 类别已被固化为确定性静态 checker，三条均为 static confirmed。它们不是多模型共识信号。",
            "",
            "## 3. strict cross-execution 归因不变",
            "",
            f"V1 static-intrinsic × strict-cross-execution：`{json.dumps(v1[cross_name], sort_keys=True)}`。",
            f"V2 static-intrinsic × strict-cross-execution：`{json.dumps(v2[cross_name], sort_keys=True)}`。",
            "",
            "strict cross-execution 的 A 仍为 0；新增的三个静态命中只使 C 增加，不能被重写成多模型增量。",
            "",
            "## 4. 证据层迁移",
            "",
            "`q895/q896` 的 `conflicting_duplicate_oracle` 仍是静态命中，但从 V1 `confirmed` 降为 V2 `review`。四格布尔命中不变，证据声称已经收紧；这是外部数据纠正 production 假阳的独立迁移类型。",
            "",
            f"覆盖迁移展开行中 changed={len(changed_coverage)}；静态 finding union 中 evidence/presence changed={len(changed_evidence)}。完整明细见 CSV，不把新增 finding 与层级变化混为一类。",
            "",
            "## 5. 边界",
            "",
            "- 五条 fact-convergence 仍为 hypothesis；本机无原始 PDF，本轮不继续搜索。",
            "- 产品不支持 result export audit；本轮只证明冻结研究 adapter 下的库级互补性。",
            "- 本轮是人工设计后的 deterministic rule promotion，不是自动训练或学习。",
            "- API attempts=0；PDF reads=0；production checkers added=0。",
            "",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--input-dir", type=Path, default=Path("data/MoDora"))
    parser.add_argument(
        "--mining-receipt",
        type=Path,
        default=Path("reports/modora_defect_mining_20260810/receipt.json"),
    )
    parser.add_argument(
        "--v1-receipt",
        type=Path,
        default=Path(
            "reports/modora_static_cross_execution_complementarity_20260810/receipt.json"
        ),
    )
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(
            "docs/research/MoDora_静态与跨执行审计互补性_V2_REPLAY_PROTOCOL_20260811.md"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "reports/modora_static_cross_execution_complementarity_v2_20260811"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    code_hashes = verify_frozen_code(repo_root)
    mining_receipt = verify_receipt(
        args.mining_receipt, FROZEN_MINING_RECEIPT_SHA256
    )
    if mining_receipt.get("schema_version") != "modora-defect-mining-receipt-v2":
        raise RuntimeError("unexpected mining receipt schema")
    v1_receipt, v1_outputs = verify_v1_outputs(args.v1_receipt)

    miner = load_module(
        repo_root / "scripts/mine_modora_defects.py", "v2_frozen_mine_modora"
    )
    old = load_module(
        repo_root / "scripts/analyze_modora_static_cross_execution.py",
        "v1_frozen_modora_complementarity",
    )
    product_refusals = verify_product_refusal(miner, args.input_dir)
    loaded = miner.load_data(args.input_dir)
    mining_result = miner.analyze(loaded)
    mining_anchors = miner.validate_anchors(mining_result)
    if not all(mining_anchors.values()):
        raise RuntimeError(
            f"upstream mining anchors failed: {[key for key, value in mining_anchors.items() if not value]}"
        )

    items = old.build_items(miner, loaded)
    static = run_static_v2(old, items)
    item_rows = old.build_item_channels(mining_result, static)
    contingency = old.contingency_rows(item_rows)

    v1_dir = args.v1_receipt.parent
    old_item_rows = read_csv(v1_dir / "item_channels.csv")
    old_static_rows = read_csv(v1_dir / "static_findings.csv")
    old_contingency = read_csv(v1_dir / "contingency_cells.csv")
    coverage_migrations = build_coverage_migrations(old_item_rows, item_rows)
    evidence_migrations = build_evidence_migrations(
        old_static_rows, static["finding_rows"]
    )
    anchors = validate_anchors(
        product_refusals,
        static,
        item_rows,
        contingency,
        coverage_migrations,
        evidence_migrations,
    )
    if not all(anchors.values()):
        raise RuntimeError(
            f"V2 replay anchors failed: {[key for key, value in anchors.items() if not value]}"
        )

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    output_specs = {
        "item_channels_v2.csv": item_rows,
        "contingency_cells_v2.csv": contingency,
        "static_findings_v2.csv": static["finding_rows"],
        "coverage_migrations.csv": coverage_migrations,
        "evidence_tier_migrations.csv": evidence_migrations,
    }
    expected_names = set(output_specs) | {"FINDINGS.md", "receipt.json"}
    unexpected = {path.name for path in output.iterdir() if path.is_file()} - expected_names
    if unexpected:
        raise RuntimeError(f"unexpected pre-existing V2 output files: {sorted(unexpected)}")
    for filename, rows in output_specs.items():
        write_csv(output / filename, rows)
    findings = render_findings(
        old_contingency, contingency, coverage_migrations, evidence_migrations
    )
    (output / "FINDINGS.md").write_text(findings, encoding="utf-8")

    generated = sorted(
        path for path in output.iterdir() if path.is_file() and path.name != "receipt.json"
    )
    receipt = {
        "schema_version": "modora-static-cross-execution-complementarity-v2",
        "script": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "protocol": {"path": str(args.protocol), "sha256": sha256_file(args.protocol)},
        "production_commit": PRODUCTION_COMMIT,
        "boundary": {
            "audit_product_used_for_static_analysis": False,
            "canonical_items_constructed_by_research_adapter": True,
            "result_export_refusal_verified_for_all_method_files": True,
            "product_refusals": product_refusals,
        },
        "inputs": {
            "input_dir": str(args.input_dir.resolve()),
            "modora_sha256": loaded.input_hashes,
            "frozen_code_sha256": code_hashes,
            "mining_receipt": {
                "path": str(args.mining_receipt),
                "sha256": FROZEN_MINING_RECEIPT_SHA256,
            },
            "v1_receipt": {
                "path": str(args.v1_receipt),
                "sha256": FROZEN_V1_RECEIPT_SHA256,
                "verified_output_sha256": v1_outputs,
            },
        },
        "static_summary_v2": static["summary"],
        "contingency_v1": v1_receipt["contingency"],
        "contingency_v2": contingency,
        "coverage_transition_counts_by_comparison": transition_counts_by_comparison(
            coverage_migrations
        ),
        "coverage_transition_counts": dict(
            sorted(Counter(row["transition"] for row in coverage_migrations).items())
        ),
        "evidence_migration_changed_rows": sum(
            bool(row["changed"]) for row in evidence_migrations
        ),
        "anchors": anchors,
        "upstream_mining_anchors": mining_anchors,
        "output_sha256": {path.name: sha256_file(path) for path in generated},
        "api_attempts": 0,
        "pdf_reads": 0,
        "production_checkers_added": 0,
        "inputs_modified": False,
        "v1_outputs_modified": False,
    }
    (output / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"anchors": anchors, "static_summary": static["summary"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
