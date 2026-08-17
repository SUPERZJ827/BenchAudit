#!/usr/bin/env python3
"""Characterize ACEBench evaluator routes without reading human issue labels.

This is a research prototype for the V3 evaluator-acceptance protocol.  It
derives a route fingerprint for each top-level reference parameter from the
call path taken by a passing reference, then applies bounded, single-parameter
P0 probes to deterministic samples from each route.

The output contains evaluator behaviour only.  It does not claim that a
rejected alternative is semantically valid or that the benchmark is flawed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from types import FrameType
from typing import Any, Callable


TRACE_FUNCTIONS = {
    "type_checker",
    "string_checker",
    "list_checker",
    "dict_checker",
    "list_dict_checker",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda value: value.as_posix()):
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")


def render_findings(
    *,
    selected_item_count: int,
    parameter_count: int,
    route_inventory: list[dict[str, Any]],
    probe_rows: list[dict[str, Any]],
    execution_errors: list[dict[str, Any]],
    evaluator_sha256: str,
    audit_input_sha256: str,
) -> str:
    lines = [
        "# ACEBench-102 评测器单参数路径与 P0 探针结果",
        "",
        "> 证据上限：仅描述 evaluator 机械行为，不宣称 benchmark 缺陷。",
        "",
        "## 汇总",
        "",
        f"- 输入条目：{selected_item_count}",
        f"- 成功映射的顶层参数比较：{parameter_count}",
        f"- 单参数 route：{len(route_inventory)}",
        f"- P0 探针：{len(probe_rows)}",
        f"- 未进入正常口径卡的条目：{len(execution_errors)}",
        "",
        "## 路径分布",
        "",
        "| 参数数 | 条目数 | 值形状 | reference 比较调用链 | 探针结果 |",
        "|---:|---:|---|---|---|",
    ]
    for route in route_inventory:
        probe_summary = "; ".join(
            f"{name}=" + ",".join(f"{verdict}:{count}" for verdict, count in verdicts.items())
            for name, verdicts in route["probe_verdicts"].items()
        ) or "未抽到可构造的 P0 探针"
        lines.append(
            f"| {route['parameter_count']} | {route['item_count']} | "
            f"`{'/'.join(route['value_shapes'])}` | `{' → '.join(route['trace_tokens'])}` | {probe_summary} |"
        )
    lines.extend([
        "",
        "## 未覆盖与基线不自洽",
        "",
    ])
    for error in execution_errors:
        lines.append(f"- `{error['item_id']}`（{error['stage']}）：`{canonical_json(error['error'])}`")
    lines.extend([
        "",
        "## 解释边界",
        "",
        "探针拒绝只证明对应候选未被 evaluator 接受。候选是否仍然满足任务，需要独立语义裁定；在完成该裁定前不得计算缺陷 TP/FP。",
        "",
        "## 绑定",
        "",
        f"- evaluator SHA-256：`{evaluator_sha256}`",
        f"- audit input SHA-256：`{audit_input_sha256}`",
        "",
    ])
    return "\n".join(lines)


def normalized_id(task_name: str, raw_id: Any) -> str:
    value = str(raw_id).strip()
    for prefix in (f"{task_name}_", f"{task_name}-"):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def load_rows(directory: Path, *, answer: bool) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(directory.glob("data_*.json")):
        task_name = path.stem.removeprefix("data_")
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            key = (task_name, normalized_id(task_name, row.get("id")))
            if key in rows:
                raise SystemExit(f"duplicate {'answer' if answer else 'task'} key {key!r} at {path}:{line_number}")
            rows[key] = row
    return rows


def load_selected_ids(audit_input: Path) -> list[str]:
    ids: list[str] = []
    for line_number, line in enumerate(audit_input.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        item_id = str(row.get("item_id") or row.get("id") or "")
        if not item_id.startswith("agentsuite-ace::"):
            raise SystemExit(f"unexpected item ID at {audit_input}:{line_number}: {item_id!r}")
        ids.append(item_id)
    if len(ids) != len(set(ids)):
        raise SystemExit("audit input contains duplicate item IDs")
    return ids


def split_item_id(item_id: str) -> tuple[str, str]:
    parts = item_id.split("::")
    if len(parts) != 3 or parts[0] != "agentsuite-ace":
        raise ValueError(f"invalid ACEBench item ID: {item_id!r}")
    return parts[1], parts[2]


def value_shape(value: Any, schema: dict[str, Any] | None) -> str:
    # Enum membership does not select a different ACEBench comparator.  An
    # enum string and a free string both reach string_checker, so including
    # the schema label in route_id would create artificial fragmentation.
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        if not value:
            return "list_empty"
        child_types = sorted({type(child).__name__ for child in value})
        return "list_" + "_".join(child_types)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # Both use ACEBench's scalar numeric type-checking route; preserve bool
        # separately because it has distinct schema and conversion semantics.
        return "number"
    return type(value).__name__


def function_description(functions: list[dict[str, Any]], reference_name: str) -> dict[str, Any] | None:
    for function in functions:
        name = str(function.get("name") or "")
        if name and name in reference_name:
            return function
    return None


def schema_parts(function: dict[str, Any] | None) -> tuple[dict[str, Any], set[str]]:
    if not function:
        return {}, set()
    container = function.get("parameters") or function.get("arguments") or {}
    properties = container.get("properties") or {}
    required = set(container.get("required") or [])
    return properties if isinstance(properties, dict) else {}, required


@dataclass(frozen=True)
class ParameterKey:
    function_name: str
    parameter_name: str


class ParameterTrace:
    """Collect checker call tokens keyed by function name and parameter name."""

    def __init__(self, checker_path: Path) -> None:
        self.checker_path = checker_path.resolve()
        self.tokens: dict[ParameterKey, list[str]] = defaultdict(list)

    @staticmethod
    def _key(function_name: str, locals_: dict[str, Any]) -> ParameterKey | None:
        param = locals_.get("param")
        if param is None:
            return None
        if function_name == "string_checker":
            function = locals_.get("function") or {}
            api_name = function.get("name") if isinstance(function, dict) else None
        else:
            api_name = locals_.get("func_name")
        if not api_name:
            return None
        return ParameterKey(str(api_name), str(param))

    def tracer(self, frame: FrameType, event: str, arg: Any) -> Callable[..., Any] | None:
        if event != "call":
            return self.tracer
        try:
            filename = Path(frame.f_code.co_filename).resolve()
        except OSError:
            return self.tracer
        function_name = frame.f_code.co_name
        if filename != self.checker_path or function_name not in TRACE_FUNCTIONS:
            return self.tracer
        key = self._key(function_name, frame.f_locals)
        if key is None:
            return self.tracer
        token = function_name
        if function_name == "string_checker":
            category = str(frame.f_locals.get("test_category") or "")
            token += ":agent" if "agent" in category else ":normal"
        if token not in self.tokens[key]:
            self.tokens[key].append(token)
        return self.tracer


def route_id(evaluator_sha256: str, entrypoint: str, shape: str, tokens: list[str]) -> str:
    payload = {
        "evaluator_sha256": evaluator_sha256,
        "entrypoint": entrypoint,
        "value_shape": shape,
        "reference_comparison_call_chain": tokens,
    }
    return "sha256:" + sha256_bytes(canonical_json(payload).encode("utf-8"))


def deterministic_rank(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def probe_candidates(
    *,
    reference: dict[str, Any],
    reference_function_name: str,
    parameter_name: str,
    schema: dict[str, Any],
    required: set[str],
) -> list[tuple[str, dict[str, Any], Any]]:
    """Return bounded single-parameter P0 mutations and their replacement value."""
    parameters = reference[reference_function_name]
    probes: list[tuple[str, dict[str, Any], Any]] = []
    if parameter_name not in required:
        omitted = copy.deepcopy(reference)
        del omitted[reference_function_name][parameter_name]
        probes.append(("omit_optional", omitted, None))
    enum_values = schema.get("enum") if isinstance(schema, dict) else None
    if isinstance(enum_values, list):
        current = parameters[parameter_name]
        alternatives = [value for value in enum_values if value != current]
        if alternatives:
            swapped = copy.deepcopy(reference)
            swapped[reference_function_name][parameter_name] = alternatives[0]
            probes.append(("enum_swap", swapped, alternatives[0]))
    return probes


def normal_model_output(reference: dict[str, Any]) -> list[dict[str, Any]]:
    """Encode a normal ACEBench ground truth as decoded model output.

    ACEBench represents parallel calls as one mapping in ``ground_truth`` but
    ``normal_checker`` expects a list containing one single-function mapping
    per call.  Wrapping the whole mapping in one list element incorrectly
    fails the function-count check.
    """
    return [
        {re.sub(r"_\d+$", "", name): copy.deepcopy(parameters)}
        for name, parameters in reference.items()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agentsuite-root", required=True, type=Path)
    parser.add_argument("--audit-input", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--sample-per-route", type=int, default=3)
    args = parser.parse_args()
    if args.sample_per_route < 1:
        raise SystemExit("--sample-per-route must be positive")

    root = args.agentsuite_root.expanduser().resolve()
    audit_input = args.audit_input.expanduser().resolve()
    out_dir = args.out_dir.expanduser().resolve()
    ace_root = root / "ACEBench"
    checker_path = ace_root / "model_eval/checker.py"
    data_dir = ace_root / "data_all/data_en"
    answer_dir = data_dir / "possible_answer"
    for path in (audit_input, checker_path, data_dir, answer_dir):
        if not path.exists():
            raise SystemExit(f"required path is missing: {path}")

    evaluator_files = [ace_root / "eval_main.py"] + sorted((ace_root / "model_eval").glob("*.py"))
    evaluator_sha256 = sha256_tree([path for path in evaluator_files if path.exists()])
    selected_ids = load_selected_ids(audit_input)
    tasks = load_rows(data_dir, answer=False)
    answers = load_rows(answer_dir, answer=True)

    sys.path.insert(0, str(ace_root))
    try:
        from model_eval.checker import normal_checker  # type: ignore
    finally:
        sys.path.pop(0)

    parameter_rows: list[dict[str, Any]] = []
    execution_errors: list[dict[str, Any]] = []
    for item_id in selected_ids:
        task_name, task_id = split_item_id(item_id)
        key = (task_name, task_id)
        if key not in tasks or key not in answers:
            raise SystemExit(f"selected item does not map to ACEBench source: {key!r}")
        task = tasks[key]
        reference = answers[key].get("ground_truth")
        if not isinstance(reference, dict):
            execution_errors.append({"item_id": item_id, "stage": "load", "error": "ground_truth_not_dict"})
            continue
        trace = ParameterTrace(checker_path)
        previous_trace = sys.gettrace()
        try:
            sys.settrace(trace.tracer)
            baseline = normal_checker(
                task.get("function") or [],
                normal_model_output(reference),
                reference,
                task.get("question") or "",
                task_name,
            )
        except Exception as exc:  # upstream evaluator failures are research output
            execution_errors.append({"item_id": item_id, "stage": "baseline", "error": f"{type(exc).__name__}: {exc}"})
            continue
        finally:
            sys.settrace(previous_trace)
        if not baseline.get("valid"):
            execution_errors.append({"item_id": item_id, "stage": "baseline", "error": baseline})
            continue

        for reference_function_name, parameters in reference.items():
            if not isinstance(parameters, dict):
                continue
            description = function_description(task.get("function") or [], reference_function_name)
            properties, required = schema_parts(description)
            actual_function_name = str((description or {}).get("name") or reference_function_name)
            for parameter_name, value in parameters.items():
                tokens = trace.tokens.get(ParameterKey(actual_function_name, parameter_name), [])
                shape = value_shape(value, properties.get(parameter_name))
                row = {
                    "item_id": item_id,
                    "task_name": task_name,
                    "reference_function": reference_function_name,
                    "evaluator_function": actual_function_name,
                    "parameter": parameter_name,
                    "value_shape": shape,
                    "schema": properties.get(parameter_name) or {},
                    "required": parameter_name in required,
                    "probe_kinds": [
                        *([] if parameter_name in required else ["omit_optional"]),
                        *(
                            ["enum_swap"]
                            if isinstance((properties.get(parameter_name) or {}).get("enum"), list)
                            and any(
                                candidate != value
                                for candidate in (properties.get(parameter_name) or {}).get("enum", [])
                            )
                            else []
                        ),
                    ],
                    "trace_tokens": tokens,
                    "route_id": route_id(evaluator_sha256, "normal_checker", shape, tokens) if tokens else "route_unknown",
                    "reference": reference,
                    "question": task.get("question") or "",
                }
                parameter_rows.append(row)

    by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in parameter_rows:
        by_route[row["route_id"]].append(row)

    sampled_keys: set[tuple[str, str, str]] = set()
    for route, rows in by_route.items():
        if route == "route_unknown":
            continue
        eligible = [row for row in rows if row["probe_kinds"]]
        ranked = sorted(eligible, key=lambda row: deterministic_rank(f"{row['item_id']}::{row['reference_function']}::{row['parameter']}"))
        for row in ranked[: args.sample_per_route]:
            sampled_keys.add((row["item_id"], row["reference_function"], row["parameter"]))

    probe_rows: list[dict[str, Any]] = []
    for row in parameter_rows:
        key = (row["item_id"], row["reference_function"], row["parameter"])
        if key not in sampled_keys:
            continue
        task_key = split_item_id(row["item_id"])
        task = tasks[task_key]
        reference = row["reference"]
        description = function_description(task.get("function") or [], row["reference_function"])
        properties, required = schema_parts(description)
        for probe_name, candidate, replacement in probe_candidates(
            reference=reference,
            reference_function_name=row["reference_function"],
            parameter_name=row["parameter"],
            schema=properties.get(row["parameter"]) or {},
            required=required,
        ):
            try:
                result = normal_checker(
                    task.get("function") or [],
                    normal_model_output(candidate),
                    reference,
                    task.get("question") or "",
                    row["task_name"],
                )
                verdict = "accepted" if result.get("valid") else "rejected"
                error = None if result.get("valid") else result
            except Exception as exc:
                verdict = "execution_error"
                error = f"{type(exc).__name__}: {exc}"
            probe_rows.append({
                "item_id": row["item_id"],
                "route_id": row["route_id"],
                "reference_function": row["reference_function"],
                "parameter": row["parameter"],
                "value_shape": row["value_shape"],
                "probe": probe_name,
                "replacement": replacement,
                "verdict": verdict,
                "error": error,
            })

    route_inventory: list[dict[str, Any]] = []
    probes_by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in probe_rows:
        probes_by_route[row["route_id"]].append(row)
    for route, rows in sorted(by_route.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        observed_probes = probes_by_route.get(route, [])
        distributions: dict[str, Counter[str]] = defaultdict(Counter)
        for probe in observed_probes:
            distributions[probe["probe"]][probe["verdict"]] += 1
        heterogeneous = any(len([count for count in counts.values() if count]) > 1 for counts in distributions.values())
        example = rows[0]
        route_inventory.append({
            "route_id": route,
            "parameter_count": len(rows),
            "item_count": len({row["item_id"] for row in rows}),
            "value_shapes": sorted({row["value_shape"] for row in rows}),
            "trace_tokens": example["trace_tokens"],
            "sampled_parameter_count": len({(probe["item_id"], probe["reference_function"], probe["parameter"]) for probe in observed_probes}),
            "probe_verdicts": {name: dict(sorted(counts.items())) for name, counts in sorted(distributions.items())},
            "heterogeneous": heterogeneous,
            "coverage": "unknown" if route == "route_unknown" else "sampled",
        })

    out_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = out_dir / "route_inventory.json"
    parameters_path = out_dir / "parameter_routes.jsonl"
    probes_path = out_dir / "probe_results.jsonl"
    errors_path = out_dir / "execution_errors.json"
    findings_path = out_dir / "FINDINGS.md"
    write_json(inventory_path, route_inventory)
    write_jsonl(parameters_path, [{key: value for key, value in row.items() if key not in {"reference", "question", "schema"}} for row in parameter_rows])
    write_jsonl(probes_path, probe_rows)
    write_json(errors_path, execution_errors)
    findings_path.write_text(
        render_findings(
            selected_item_count=len(selected_ids),
            parameter_count=len(parameter_rows),
            route_inventory=route_inventory,
            probe_rows=probe_rows,
            execution_errors=execution_errors,
            evaluator_sha256=evaluator_sha256,
            audit_input_sha256=sha256_file(audit_input),
        ),
        encoding="utf-8",
    )

    receipt = {
        "protocol": "evaluator-acceptance-route-v3-research-prototype",
        "claims_ceiling": "mechanical evaluator behaviour only; no benchmark defect claims",
        "agentsuite_root": str(root),
        "audit_input": str(audit_input),
        "audit_input_sha256": sha256_file(audit_input),
        "evaluator_sha256": evaluator_sha256,
        "selected_item_count": len(selected_ids),
        "parameter_count": len(parameter_rows),
        "route_count_including_unknown": len(by_route),
        "known_route_count": len([route for route in by_route if route != "route_unknown"]),
        "unknown_parameter_count": len(by_route.get("route_unknown", [])),
        "probe_count": len(probe_rows),
        "execution_error_count": len(execution_errors),
        "sample_per_route": args.sample_per_route,
        "outputs": {},
    }
    for path in (inventory_path, parameters_path, probes_path, errors_path, findings_path):
        receipt["outputs"][path.name] = sha256_file(path)
    write_json(out_dir / "receipt.json", receipt)

    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
