#!/usr/bin/env python3
"""Compare frozen production-static and MoDora cross-execution signals offline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
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
from benchcore.methods import DEFAULT_DATASET_CHECKERS, DEFAULT_METHOD_CHECKERS
from benchcore.schema import BenchmarkItem, Violation


FROZEN_CODE_SHA256 = {
    "benchcore/checkers.py": "fcf792c2b4ecdc5e859b9f5b9264d119db069db3ae21b1104c70061305d2bb5e",
    "benchcore/methods.py": "d4f907ebee9f11d5878adefec080079e73d99d09f14a8a9682293b25be46ed0a",
    "benchcore/auditor.py": "424bd594619dcadff2d69f31f1e1df2d5c46fc380f19db6229cf5c89a5aae2d9",
    "benchcore/schema.py": "1015e091e3fbbe10cc26d165dbdc4fec4e3f3966463013e3403bba7883249870",
    "scripts/mine_modora_defects.py": "3bf48bd13504b502407d0f16a48ceb266994ba7e96b23b3b3fe5dd19ed0772fb",
}
FROZEN_MINING_RECEIPT_SHA256 = (
    "d91f471330eecf1849dff6b88b43e3092360196dd21040600cafd443cdfcaad2"
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


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify_frozen_inputs(repo_root: Path, mining_receipt: Path) -> dict[str, str]:
    actual = {}
    for relative, expected in FROZEN_CODE_SHA256.items():
        path = repo_root / relative
        digest = sha256_file(path)
        if digest != expected:
            raise RuntimeError(
                f"frozen code hash mismatch for {relative}: {digest} != {expected}"
            )
        actual[relative] = digest
    if not mining_receipt.is_file():
        raise RuntimeError(f"mining receipt missing: {mining_receipt}")
    receipt_hash = sha256_file(mining_receipt)
    if receipt_hash != FROZEN_MINING_RECEIPT_SHA256:
        raise RuntimeError(
            f"mining receipt hash mismatch: {receipt_hash} != "
            f"{FROZEN_MINING_RECEIPT_SHA256}"
        )
    receipt = json.loads(mining_receipt.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != "modora-defect-mining-receipt-v2":
        raise RuntimeError("unexpected mining receipt schema")
    if not receipt.get("anchors") or not all(
        value is True for value in receipt["anchors"].values()
    ):
        raise RuntimeError("mining receipt anchors are not all true")
    actual["reports/modora_defect_mining_20260810/receipt.json"] = receipt_hash
    return actual


def build_items(miner: ModuleType, loaded: Any) -> list[BenchmarkItem]:
    canonical, conflicts = miner.canonical_metadata(loaded)
    unresolved = {
        row["questionId"]
        for row in conflicts
        if row.get("semantic_conflict") is True
    }
    items = []
    for question_id in loaded.ids:
        row = canonical[question_id]
        items.append(
            BenchmarkItem(
                item_id=str(question_id),
                row_uid=f"modora:{question_id}",
                raw=dict(row),
                task=row["question"],
                gold=row["answer"],
                context={
                    "source_document_identity": {
                        "pdf_id": row["pdf_id"],
                        "content_available": False,
                    }
                },
                metadata={
                    "pdf_id": row["pdf_id"],
                    "tag": row["tag"],
                    "context_content_available": False,
                    "canonical_metadata_unresolved": question_id in unresolved,
                },
            )
        )
    return items


def select_named(values: Iterable[Any], names: set[str]) -> list[Any]:
    selected = [value for value in values if value.name in names]
    found = Counter(value.name for value in selected)
    if found != Counter({name: 1 for name in names}):
        raise RuntimeError(
            f"frozen checker set unavailable: expected {sorted(names)}, got {dict(found)}"
        )
    return selected


def target_ids(finding: Violation) -> list[int]:
    raw_targets = finding.evidence.get("target_row_uids")
    if not raw_targets:
        return [int(finding.item_id)]
    targets = []
    for raw in raw_targets:
        text = str(raw)
        if not text.startswith("modora:"):
            raise RuntimeError(f"unexpected target row uid: {text}")
        targets.append(int(text.split(":", 1)[1]))
    return sorted(set(targets))


def run_static(items: list[BenchmarkItem]) -> dict[str, Any]:
    complete_checkers = list(DEFAULT_CHECKERS) + list(DEFAULT_METHOD_CHECKERS)
    complete = audit_items_with_ledger(
        items,
        checkers=complete_checkers,
        dataset_checkers=list(DEFAULT_DATASET_CHECKERS),
        fail_fast=True,
    )
    compatible_checkers = select_named(complete_checkers, COMPATIBLE_ITEM_CHECKERS)
    compatible_dataset = select_named(
        DEFAULT_DATASET_CHECKERS, COMPATIBLE_DATASET_CHECKERS
    )
    compatible = audit_items_with_ledger(
        items,
        checkers=compatible_checkers,
        dataset_checkers=compatible_dataset,
        fail_fast=True,
    )
    for label, result in (("complete", complete), ("compatible", compatible)):
        failed = [entry for entry in result.ledger if entry.status == "operational_failed"]
        if failed:
            raise RuntimeError(f"{label} static run had operational failures: {failed[:3]}")

    finding_rows = []
    any_ids: set[int] = set()
    intrinsic_ids: set[int] = set()
    availability_ids: set[int] = set()
    for finding in compatible.violations:
        channel = (
            "availability_metadata"
            if finding.defect_type in AVAILABILITY_DEFECT_TYPES
            else "intrinsic"
        )
        for question_id in target_ids(finding):
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
        key=lambda row: (row["questionId"], row["channel"], row["defect_type"])
    )
    complete_hit_ids = {
        question_id
        for finding in complete.violations
        for question_id in target_ids(finding)
    }
    return {
        "finding_rows": finding_rows,
        "any_ids": any_ids,
        "intrinsic_ids": intrinsic_ids,
        "availability_ids": availability_ids,
        "summary": {
            "complete_findings": len(complete.violations),
            "complete_hit_items": len(complete_hit_ids),
            "complete_finding_types": dict(
                sorted(Counter(v.defect_type for v in complete.violations).items())
            ),
            "complete_ledger_status": dict(
                sorted(Counter(entry.status for entry in complete.ledger).items())
            ),
            "compatible_findings_before_target_expansion": len(
                compatible.violations
            ),
            "compatible_expanded_rows": len(finding_rows),
            "compatible_hit_items": len(any_ids),
            "intrinsic_hit_items": len(intrinsic_ids),
            "availability_hit_items": len(availability_ids),
            "compatible_finding_types": dict(
                sorted(Counter(v.defect_type for v in compatible.violations).items())
            ),
            "compatible_ledger_status": dict(
                sorted(Counter(entry.status for entry in compatible.ledger).items())
            ),
        },
    }


def phi(left: Sequence[int], right: Sequence[int]) -> float | None:
    if len(left) != len(right) or not left:
        raise ValueError("binary vectors must have equal non-zero length")
    if any(value not in {0, 1} for value in (*left, *right)):
        raise ValueError("phi requires binary vectors")
    n11 = sum(a == 1 and b == 1 for a, b in zip(left, right))
    n10 = sum(a == 1 and b == 0 for a, b in zip(left, right))
    n01 = sum(a == 0 and b == 1 for a, b in zip(left, right))
    n00 = len(left) - n11 - n10 - n01
    denominator = math.sqrt((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00))
    return (n11 * n00 - n10 * n01) / denominator if denominator else None


def method_correlations(miner: ModuleType, loaded: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    methods = list(miner.METHOD_FILES)
    vectors = {
        method: [
            1 if loaded.by_method[method][question_id]["judge"] == "T" else 0
            for question_id in loaded.ids
        ]
        for method in methods
    }
    pairs = []
    for left_index, left in enumerate(methods):
        for right in methods[left_index + 1 :]:
            lv, rv = vectors[left], vectors[right]
            value = phi(lv, rv)
            pairs.append(
                {
                    "method_a": left,
                    "method_b": right,
                    "n11": sum(a == 1 and b == 1 for a, b in zip(lv, rv)),
                    "n10": sum(a == 1 and b == 0 for a, b in zip(lv, rv)),
                    "n01": sum(a == 0 and b == 1 for a, b in zip(lv, rv)),
                    "n00": sum(a == 0 and b == 0 for a, b in zip(lv, rv)),
                    "phi": "" if value is None else f"{value:.12f}",
                }
            )
    matrix = []
    for left in methods:
        row: dict[str, Any] = {"method": left}
        for right in methods:
            value = 1.0 if left == right else phi(vectors[left], vectors[right])
            row[right] = "" if value is None else f"{value:.12f}"
        matrix.append(row)
    return pairs, matrix


def contingency_rows(
    item_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output = []
    for name, static_field, external_field in CONTINGENCY_SPECS:
        cells = {"A": [], "B": [], "C": [], "D": []}
        for row in item_rows:
            static = bool(row[static_field])
            external = bool(row[external_field])
            cell = "A" if static and external else "B" if external else "C" if static else "D"
            cells[cell].append(int(row["questionId"]))
        if sum(len(ids) for ids in cells.values()) != len(item_rows):
            raise RuntimeError(f"contingency partition failed: {name}")
        for cell in "ABCD":
            output.append(
                {
                    "comparison": name,
                    "static_field": static_field,
                    "external_field": external_field,
                    "cell": cell,
                    "count": len(cells[cell]),
                    "question_ids_json": json.dumps(cells[cell], separators=(",", ":")),
                }
            )
    return output


def build_item_channels(
    mining_result: Mapping[str, Any], static: Mapping[str, Any]
) -> list[dict[str, Any]]:
    triage = {row["questionId"]: row for row in mining_result["triage_rows"]}
    rows = []
    for question_id in sorted(triage):
        source = triage[question_id]
        h1 = bool(source["sig_h1_record_inconsistency"])
        fact = bool(source["sig_r1_fact_convergence"])
        inversion = bool(source["sig_r2_difficulty_inversion"])
        invisible = bool(source["sig_h2_invisible_gold"])
        cross = h1 or fact or inversion
        rows.append(
            {
                "questionId": question_id,
                "static_intrinsic": question_id in static["intrinsic_ids"],
                "static_availability_metadata": question_id
                in static["availability_ids"],
                "static_any_compatible": question_id in static["any_ids"],
                "cross_execution_hard_h1": h1,
                "cross_execution_review_fact": fact,
                "cross_execution_review_inversion": inversion,
                "cross_execution_hit": cross,
                "artifact_sidecar_invisible_gold": invisible,
                "mining_layer_hit": cross or invisible,
                "all_wrong_divergent_no_selected_anomaly": (
                    source["n_correct"] == 0
                    and source["max_e1_prediction_convergence"] == 1
                ),
                "primary_verdict": source["primary_verdict"],
            }
        )
    if len(rows) != 1065 or {row["questionId"] for row in rows} != set(range(1, 1066)):
        raise RuntimeError("item channel alignment is not exactly 1..1065")
    return rows


def row_by_id(item_rows: Sequence[Mapping[str, Any]], question_id: int) -> Mapping[str, Any]:
    return next(row for row in item_rows if row["questionId"] == question_id)


def validate_anchors(
    static: Mapping[str, Any],
    item_rows: Sequence[Mapping[str, Any]],
    contingency: Sequence[Mapping[str, Any]],
    phi_pairs: Sequence[Mapping[str, Any]],
) -> dict[str, bool]:
    controls = {question_id: row_by_id(item_rows, question_id) for question_id in (853, 854, 895, 896, 994, 1048, 1060)}
    return {
        "items_1065": len(item_rows) == 1065,
        "complete_static_degenerate_1065": static["summary"]["complete_hit_items"] == 1065,
        "compatible_43_findings_47_expanded_target_items": (
            static["summary"]["compatible_findings_before_target_expansion"] == 43
            and static["summary"]["compatible_hit_items"] == 47
        ),
        "four_contingencies_partition_1065": len(contingency) == 16
        and all(
            sum(
                row["count"]
                for row in contingency
                if row["comparison"] == name
            )
            == 1065
            for name, _, _ in CONTINGENCY_SPECS
        ),
        "phi_pairs_36": len(phi_pairs) == 36,
        "q994_true_negative_not_selected": not controls[994]["static_intrinsic"]
        and not controls[994]["mining_layer_hit"],
        "q895_q896_known_static_false_positive_control": all(
            controls[qid]["static_intrinsic"]
            and not controls[qid]["mining_layer_hit"]
            for qid in (895, 896)
        ),
        "q1060_cross_execution_hard_static_miss": controls[1060][
            "cross_execution_hard_h1"
        ]
        and not controls[1060]["static_intrinsic"],
        "invisible_gold_sidecar_not_cross_execution": all(
            controls[qid]["artifact_sidecar_invisible_gold"]
            and not controls[qid]["cross_execution_hit"]
            for qid in (853, 854, 1048)
        ),
        "divergent_all_wrong_89_no_semantic_claim": sum(
            row["all_wrong_divergent_no_selected_anomaly"] for row in item_rows
        )
        == 89,
    }


def render_findings(
    static: Mapping[str, Any],
    item_rows: Sequence[Mapping[str, Any]],
    contingency: Sequence[Mapping[str, Any]],
    phi_pairs: Sequence[Mapping[str, Any]],
) -> str:
    grids = {
        name: {
            row["cell"]: row["count"]
            for row in contingency
            if row["comparison"] == name
        }
        for name, _, _ in CONTINGENCY_SPECS
    }
    phi_defined = [row for row in phi_pairs if row["phi"] != ""]
    highest = max(phi_defined, key=lambda row: float(row["phi"]))
    lowest = min(phi_defined, key=lambda row: float(row["phi"]))
    cross_hard = sum(row["cross_execution_hard_h1"] for row in item_rows)
    cross_fact = sum(row["cross_execution_review_fact"] for row in item_rows)
    cross_inversion = sum(row["cross_execution_review_inversion"] for row in item_rows)
    cross_any = sum(row["cross_execution_hit"] for row in item_rows)
    invisible = sum(row["artifact_sidecar_invisible_gold"] for row in item_rows)
    intrinsic = grids["static_intrinsic_x_cross_execution"]
    mining = grids["static_intrinsic_x_mining_layer"]
    intrinsic_type_counts = dict(
        sorted(
            Counter(
                row["defect_type"]
                for row in static["finding_rows"]
                if row["channel"] == "intrinsic"
            ).items()
        )
    )
    return "\n".join(
        [
            "# MoDora 静态与跨执行审计互补性结果",
            "",
            "> 零 API 的事后确定性二次分析。命中不自动等于真缺陷；预飞已知性见冻结协议。",
            "",
            "## 1. 主四格：production static intrinsic × cross-execution",
            "",
            f"A（两层都报）={intrinsic['A']}；B（跨执行独有）={intrinsic['B']}；C（静态独有）={intrinsic['C']}；D（两层都未报）={intrinsic['D']}。合计 1,065。",
            "",
            f"cross-execution 分层为：hard local T/F inconsistency={cross_hard}，fact-convergence review={cross_fact}，difficulty-inversion review={cross_inversion}，并集={cross_any}。review 层不得写成 confirmed defect。",
            "",
            "## 2. artifact-sidecar 的独立增量",
            "",
            f"U+200B/invisible-gold sidecar 命中={invisible}。把它加入整个 mining layer 后，与 static intrinsic 的四格为 A={mining['A']}、B={mining['B']}、C={mining['C']}、D={mining['D']}。这个增量来自 artifact 扫描，不来自多模型共识。",
            "",
            "## 3. production static 的适用性与对照",
            "",
            f"完整 production checker 集合在 {static['summary']['complete_hit_items']}/1065 item 上都会命中，主要因为本地 MoDora 记录没有 evaluator/output contract；该结果是适用性诊断，不是性能结论。",
            "",
            f"schema-compatible 子集产生 {static['summary']['compatible_findings_before_target_expansion']} 条 finding，覆盖 {static['summary']['compatible_hit_items']} item；其中 intrinsic 覆盖 {static['summary']['intrinsic_hit_items']} item，availability/metadata 覆盖 {static['summary']['availability_hit_items']} item。",
            "",
            f"intrinsic 的 {static['summary']['intrinsic_hit_items']} 个 item 由以下类型构成：`{json.dumps(intrinsic_type_counts, ensure_ascii=False, sort_keys=True)}`。因此 A={intrinsic['A']} 说明当前可适用的 production 静态规则与冻结 cross-execution 信号没有重叠，不表示所有可能静态规则都与它正交。",
            "",
            "`q994` 在两层都未命中，保住了英寸/毫米真阴性。`q895/q896` 被 production duplicate checker 报为 `conflicting_duplicate_oracle` 并升到 `confirmed`，但已知只差句末标点；它们是静态层的已验证假阳性对照，所以 C 不能直接解读为“静态不可替代”。",
            "",
            "`q1060` 是 cross-execution hard/static-miss；`q853/q854/q1048` 是 invisible-gold sidecar/static-miss。后三条证明现有 production static 没有不可见字符检查，但不能归因给多模型一致性。",
            "",
            "## 4. 方法依赖性",
            "",
            f"36 对 phi 中，最高为 {highest['method_a']}–{highest['method_b']}={float(highest['phi']):.3f}，最低为 {lowest['method_a']}–{lowest['method_b']}={float(lowest['phi']):.3f}。这说明依赖性应由实测矩阵描述，不应从“RAG”等名称手工分族。本轮不事后改写既有信号规则。",
            "",
            "## 5. 边界",
            "",
            "- 89 条全错且预测发散 item 只是 `no_selected_anomaly`，不是“真难题”或“无缺陷”证据。",
            "- cross-execution 层要求公开的多方法逐题结果，覆盖窄；production static 不需要响应面板，覆盖广。",
            "- 四格表明信号互补，不提供 B/C 全部为真缺陷的 precision 保证。",
            "- API attempts=0，PDF reads=0，production checkers added=0。",
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
        "--protocol",
        type=Path,
        default=Path(
            "docs/research/MoDora_静态与跨执行审计互补性_PROTOCOL_20260810.md"
        ),
    )
    parser.add_argument(
        "--protocol-correction",
        type=Path,
        default=Path(
            "docs/research/MoDora_静态与跨执行审计互补性_目标行展开口径更正_20260810.md"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "reports/modora_static_cross_execution_complementarity_20260810"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    frozen_hashes = verify_frozen_inputs(repo_root, args.mining_receipt)
    miner = load_module(
        repo_root / "scripts/mine_modora_defects.py", "frozen_mine_modora_defects"
    )
    loaded = miner.load_data(args.input_dir)
    mining_result = miner.analyze(loaded)
    mining_anchors = miner.validate_anchors(mining_result)
    if not all(mining_anchors.values()):
        raise RuntimeError(
            f"upstream mining anchors failed: {[k for k, v in mining_anchors.items() if not v]}"
        )
    items = build_items(miner, loaded)
    static = run_static(items)
    item_rows = build_item_channels(mining_result, static)
    contingency = contingency_rows(item_rows)
    phi_pairs, phi_matrix = method_correlations(miner, loaded)
    anchors = validate_anchors(static, item_rows, contingency, phi_pairs)
    if not all(anchors.values()):
        raise RuntimeError(
            f"analysis anchors failed: {[k for k, v in anchors.items() if not v]}"
        )

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    output_specs = {
        "item_channels.csv": item_rows,
        "contingency_cells.csv": contingency,
        "static_findings.csv": static["finding_rows"],
        "method_phi_pairs.csv": phi_pairs,
        "method_phi_matrix.csv": phi_matrix,
    }
    expected_output_names = set(output_specs) | {"FINDINGS.md", "receipt.json"}
    unexpected_existing = {
        path.name for path in output.iterdir() if path.is_file()
    } - expected_output_names
    if unexpected_existing:
        raise RuntimeError(
            f"unexpected pre-existing output files: {sorted(unexpected_existing)}"
        )
    for filename, rows in output_specs.items():
        write_csv(output / filename, rows)
    findings = render_findings(static, item_rows, contingency, phi_pairs)
    (output / "FINDINGS.md").write_text(findings, encoding="utf-8")
    generated = sorted(
        path
        for path in output.iterdir()
        if path.is_file() and path.name != "receipt.json"
    )
    receipt = {
        "schema_version": "modora-static-cross-execution-complementarity-v1",
        "script": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "protocol": {
            "path": str(args.protocol),
            "sha256": sha256_file(args.protocol),
        },
        "protocol_correction": {
            "path": str(args.protocol_correction),
            "sha256": sha256_file(args.protocol_correction),
        },
        "inputs": {
            "input_dir": str(args.input_dir.resolve()),
            "modora_sha256": loaded.input_hashes,
            "frozen_code_and_upstream_sha256": frozen_hashes,
            "mining_receipt_path": str(args.mining_receipt),
        },
        "static_summary": static["summary"],
        "channel_summary": {
            "cross_execution_hard_h1": sum(
                row["cross_execution_hard_h1"] for row in item_rows
            ),
            "cross_execution_review_fact": sum(
                row["cross_execution_review_fact"] for row in item_rows
            ),
            "cross_execution_review_inversion": sum(
                row["cross_execution_review_inversion"] for row in item_rows
            ),
            "cross_execution_union": sum(
                row["cross_execution_hit"] for row in item_rows
            ),
            "artifact_sidecar_invisible_gold": sum(
                row["artifact_sidecar_invisible_gold"] for row in item_rows
            ),
            "mining_layer_union": sum(row["mining_layer_hit"] for row in item_rows),
            "all_wrong_divergent_no_selected_anomaly": sum(
                row["all_wrong_divergent_no_selected_anomaly"] for row in item_rows
            ),
        },
        "contingency": contingency,
        "anchors": anchors,
        "upstream_mining_anchors": mining_anchors,
        "output_sha256": {path.name: sha256_file(path) for path in generated},
        "api_attempts": 0,
        "pdf_reads": 0,
        "production_checkers_added": 0,
        "inputs_modified": False,
    }
    (output / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt["channel_summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
