#!/usr/bin/env python3
"""Materialize AgentSuite's ACEBench-102 human-alignment set without labels.

The public AgentSuite snapshot stores benchmark artifacts and human labels in
the same repository.  This script joins them only to establish stable IDs, then
writes the audit input and truth to separate, hash-bound files.  Neither the
human label nor AgentSuite's issue explanation is copied into the audit input.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


EXPECTED_LABEL_SHA256 = "2aab0afdf7fd6cc2760a78e3c6f67cc6459f9783eafcd3dfcf4dde651435faf1"
EXPECTED_LABEL_COUNTS = Counter({"1": 51, "0": 51})
EXPECTED_ITEM_COUNT = 1023


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def nested_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(nested_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(nested_keys(child))
    return keys


def normalized_id(task_name: str, raw_id: Any) -> str:
    value = str(raw_id).strip()
    return re.sub(rf"^{re.escape(task_name)}[_-]", "", value)


def load_task_rows(data_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(data_dir.glob("data_*.json")):
        task_name = path.stem.removeprefix("data_")
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            key = (task_name, normalized_id(task_name, row.get("id")))
            if key in rows:
                raise SystemExit(f"duplicate task key {key!r} at {path}:{line_number}")
            rows[key] = row
    return rows


def load_answer_rows(answer_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(answer_dir.glob("data_*.json")):
        task_name = path.stem.removeprefix("data_")
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            key = (task_name, normalized_id(task_name, row.get("id")))
            if key in rows:
                raise SystemExit(f"duplicate answer key {key!r} at {path}:{line_number}")
            rows[key] = row
    return rows


def stable_item_id(task_name: str, task_id: str) -> str:
    return f"agentsuite-ace::{task_name}::{task_id}"


def parse_inline_structure(value: Any) -> Any:
    """Recover AgentSuite structures stored as Python-literal strings.

    Some ACEBench profiles are serialized dictionaries rather than paths or
    prose.  Leaving them as long strings makes BenchCore's context renderer
    probe them as possible artifact paths.  Literal evaluation is restricted
    to Python literals and fails closed to the original value.
    """
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    # ACEBench's normal_preference rows append prose punctuation after the
    # serialized dictionary (``{...}.``). Remove exactly that wrapper period.
    if stripped.endswith(("}.", "].", ").")):
        stripped = stripped[:-1]
    if not stripped.startswith(("{", "[", "(")):
        return value
    try:
        parsed = ast.literal_eval(stripped)
    except (SyntaxError, ValueError):
        return value
    return parsed if isinstance(parsed, (dict, list, tuple)) else value


def python_string_constant(path: Path, name: str) -> str:
    """Read a top-level string constant without executing upstream code."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value_node = node.value
        else:
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        value = ast.literal_eval(value_node)
        if not isinstance(value, str):
            raise SystemExit(f"{path}:{name} is not a string constant")
        return value
    raise SystemExit(f"missing upstream prompt constant {name} in {path}")


def build_solver_instructions(root: Path, source: dict[str, Any]) -> str:
    """Reconstruct the official ACEBench agent system prompt as inert data."""
    prompt_path = root / "ACEBench/model_inference/prompt_en.py"
    raw_id = str(source.get("id") or "")
    category = raw_id.rsplit("_", 1)[0]
    functions = source.get("function") or []
    time_info = source.get("time") or ""
    profile = source.get("profile") or ""
    if category.startswith("agent"):
        common_path = root / "ACEBench/model_inference/multi_step/common_agent_step.py"
        prompt = python_string_constant(
            common_path, "MULTI_TURN_AGENT_PROMPT_SYSTEM_EN"
        ).strip()
        classes = source.get("involved_classes") or []
        if any("Travel" in str(value) for value in classes):
            prompt += "\n\n" + python_string_constant(prompt_path, "TRAVEL_PROMPT_EN").strip()
        if any("BaseApi" in str(value) for value in classes):
            prompt += "\n\n" + python_string_constant(prompt_path, "BASE_PROMPT_EN").strip()
        return prompt
    if "special" in category:
        template = python_string_constant(prompt_path, "SYSTEM_PROMPT_FOR_SPECIAL_DATA_EN")
        return template.format(time=time_info, function=functions)
    if "preference" in category:
        template = python_string_constant(prompt_path, "SYSTEM_PROMPT_FOR_PREFERENCE_DATA_EN")
        return template.format(profile=profile, function=functions)
    template = python_string_constant(prompt_path, "SYSTEM_PROMPT_FOR_NORMAL_DATA_EN")
    return template.format(time=time_info, function=functions)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agentsuite-root", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()

    root = args.agentsuite_root.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    label_path = root / "pipeline/human_labelled_ground_truth/ACEBench.csv"
    issue_path = root / "ACEBench/acebench_issues.csv"
    data_dir = root / "ACEBench/data_all/data_en"
    answer_dir = data_dir / "possible_answer"
    for path in (label_path, issue_path, data_dir, answer_dir):
        if not path.exists():
            raise SystemExit(f"required AgentSuite path is missing: {path}")
    actual_label_sha = sha256_file(label_path)
    if actual_label_sha != EXPECTED_LABEL_SHA256:
        raise SystemExit(
            f"ACEBench label SHA mismatch: expected {EXPECTED_LABEL_SHA256}, got {actual_label_sha}"
        )

    task_rows = load_task_rows(data_dir)
    answer_rows = load_answer_rows(answer_dir)
    if len(task_rows) != EXPECTED_ITEM_COUNT or len(answer_rows) != EXPECTED_ITEM_COUNT:
        raise SystemExit(
            f"unexpected ACEBench source shape: {len(task_rows)} tasks / {len(answer_rows)} answers"
        )

    with label_path.open(encoding="utf-8-sig", newline="") as handle:
        labels = list(csv.DictReader(handle))
    counts = Counter(row.get("is_issue") for row in labels)
    if counts != EXPECTED_LABEL_COUNTS:
        raise SystemExit(f"unexpected label distribution: {counts!r}")

    audit_rows: list[dict[str, Any]] = []
    truth_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for label in labels:
        task_name = str(label.get("task_name") or "").strip()
        task_id = str(label.get("task_id") or "").strip()
        key = (task_name, task_id)
        if key not in task_rows or key not in answer_rows:
            raise SystemExit(f"human label does not map to source artifacts: {key!r}")
        source = task_rows[key]
        answer = answer_rows[key]
        item_id = stable_item_id(task_name, task_id)
        if item_id in seen_ids:
            raise SystemExit(f"duplicate materialized ID: {item_id}")
        seen_ids.add(item_id)

        functions = source.get("function") or []
        if not isinstance(functions, list) or not functions:
            raise SystemExit(f"{item_id}: missing function schemas")
        task = source.get("question")
        if not isinstance(task, str) or not task.strip():
            raise SystemExit(f"{item_id}: missing task text")
        gold = answer.get("ground_truth")
        if gold in (None, "", [], {}):
            raise SystemExit(f"{item_id}: missing ground truth")

        context = {
            "available_functions": functions,
        }
        for field in ("time", "profile", "initial_config", "path", "involved_classes"):
            value = source.get(field)
            if value not in (None, "", [], {}):
                if field == "profile":
                    value = parse_inline_structure(value)
                context[field] = value
        milestones = answer.get("mile_stone")
        if milestones not in (None, "", [], {}):
            # A bare list of long call strings is path-like to the generic
            # renderer.  Give the trajectory fragment an explicit container
            # so it is rendered as inline structured evidence instead.
            context["milestones"] = {"calls": milestones}

        audit_rows.append(
            {
                "id": item_id,
                "task": task.strip(),
                # Context fields stay flat because BenchCore's declared
                # context mapping is a list of source fields.  Wrapping them
                # in one dict would subject the whole tool list to the
                # per-dict 1,600-character preview cap.
                **context,
                # An ACEBench oracle is a structured call/trajectory, not a
                # scalar answer.  Keep it in the reference-solution channel so
                # scalar answer-contract rules cannot misinterpret incidental
                # numbers inside function arguments as a numeric gold.
                "reference_solution": gold,
                "solver_instructions": build_solver_instructions(root, source),
                "output_contract": {
                    "type": "tool_call_or_agent_trajectory",
                    "function_schema_source": "context.available_functions",
                },
                "evaluator": {
                    "type": "official_acebench_package_evaluator",
                    "scope": "benchmark_package",
                    "implementation": [
                        "ACEBench/eval_main.py",
                        "ACEBench/model_eval/evaluation_helper.py",
                        "ACEBench/model_eval/utils.py",
                    ],
                },
                "metadata": {
                    "source": "Agent-Suite/AgentSuite:ACEBench",
                    "task_name": task_name,
                    "task_id": task_id,
                },
            }
        )
        truth_rows.append({"id": item_id, "is_issue": int(label["is_issue"])})

    if len(audit_rows) != 102 or {r["id"] for r in audit_rows} != {r["id"] for r in truth_rows}:
        raise SystemExit("materialized audit/truth ID sets are inconsistent")
    forbidden = {"is_issue", "issue_type", "issue_reason", "resolution"}
    leaked = [
        row["id"]
        for row in audit_rows
        if (set(row) & forbidden) or (nested_keys(row.get("metadata", {})) & forbidden)
    ]
    if leaked:
        raise SystemExit(f"truth-like field names leaked into audit input: {leaked[:3]}")

    audit_path = out_dir / "audit_input.jsonl"
    truth_path = out_dir / "sealed_truth.jsonl"
    mapping_path = out_dir / "mapping.json"
    mapping_a0_path = out_dir / "mapping_a0.json"
    write_jsonl(audit_path, audit_rows)
    write_jsonl(truth_path, truth_rows)
    mapping = {
        "item_id": "id",
        "task": "task",
        "context": [
            "available_functions",
            "time",
            "profile",
            "initial_config",
            "path",
            "involved_classes",
            "milestones"
        ],
        "output_contract": "output_contract",
        "solver_instructions": "solver_instructions",
        "evaluator": "evaluator",
        "metadata": ["metadata"],
    }
    mapping_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mapping_a0 = {key: value for key, value in mapping.items() if key != "solver_instructions"}
    mapping_a0_path.write_text(
        json.dumps(mapping_a0, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    source_files = sorted(
        [label_path, issue_path]
        + list(data_dir.glob("data_*.json"))
        + list(answer_dir.glob("data_*.json"))
        + [root / "ACEBench/eval_main.py"]
        + list((root / "ACEBench/model_eval").glob("*.py"))
        + [
            root / "ACEBench/model_inference/prompt_en.py",
            root / "ACEBench/model_inference/multi_step/common_agent_step.py",
        ]
    )
    receipt = {
        "schema_version": 1,
        "status": "MATERIALIZED_AGENTSUITE_ACEBENCH_102",
        "source": {
            "agentsuite_root": str(root),
            "upstream_commit_verified_separately": "0f9eac1c1a376a411ad807bd974555055f08e6c5",
            "files": {
                str(path.relative_to(root)): sha256_file(path) for path in source_files
            },
        },
        "dataset": {
            "items": len(audit_rows),
            "positive": counts["1"],
            "negative": counts["0"],
            "sampling_scope": "public balanced human-alignment subset; not natural prevalence",
        },
        "isolation": {
            "truth_file_separate": True,
            "audit_input_contains_human_label": False,
            "audit_input_contains_official_issue_reason": False,
            "id_sets_equal": True,
        },
        "outputs": {
            path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in (audit_path, truth_path, mapping_path, mapping_a0_path)
        },
    }
    receipt_path = out_dir / "materialization_receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
