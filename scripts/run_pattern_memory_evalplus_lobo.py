"""Zero-API leave-one-benchmark-out validation for defect-pattern memory."""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import math
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datasets import load_dataset

from benchcore.audit_memory import (
    MEMORY_SCHEMA_VERSION,
    DefectPattern,
    DefectPatternMatcher,
    DefectPatternStore,
    PatternQuery,
)
from benchcore.execution import CommandSpec, ContainerRunner, ExecutionPolicy


DRIVER = r'''
import contextlib
import io
import json
import os
import signal
import sys

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

class ProbeTimeout(Exception):
    pass

def timeout_handler(signum, frame):
    raise ProbeTimeout("probe timeout")

signal.signal(signal.SIGALRM, timeout_handler)
payload = json.loads(sys.stdin.read())

def execute(source, tests, call):
    namespace = {}
    stream = io.StringIO()
    try:
        signal.setitimer(signal.ITIMER_REAL, payload["per_probe_timeout"])
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            exec(compile(source, "<candidate>", "exec"), namespace)
            exec(compile(tests, "<tests>", "exec"), namespace)
            if call:
                exec(call, namespace)
        return {"passed": True, "error": None}
    except BaseException as exc:
        return {
            "passed": False,
            "error": f"{type(exc).__name__}: {exc}"[:500],
        }
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)

rows = []
for mutant in payload["mutants"]:
    original = execute(mutant["source"], payload["original_test"], payload["original_call"])
    plus = execute(mutant["source"], payload["plus_test"], payload["plus_call"])
    rows.append({
        "mutant_id": mutant["mutant_id"],
        "family": mutant["family"],
        "original": original,
        "plus": plus,
    })
print(json.dumps({"rows": rows}, sort_keys=True))
'''


@dataclass(frozen=True)
class Task:
    benchmark: str
    task_id: str
    source: str
    original_test: str
    plus_test: str
    original_call: str
    plus_call: str


COMPARE_REPLACEMENTS = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}
BINOP_REPLACEMENTS = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv,
    ast.FloorDiv: ast.Mult,
    ast.Mod: ast.Add,
}
BOOLOP_REPLACEMENTS = {ast.And: ast.Or, ast.Or: ast.And}
WRAPPER_CALLS = frozenset({"abs", "sorted", "list", "tuple", "set", "reversed"})
FAMILIES = (
    "comparison_boundary",
    "arithmetic_operator",
    "boolean_operator",
    "condition_negation",
    "numeric_constant",
    "range_boundary",
    "slice_boundary",
    "drop_wrapper_call",
    "return_default",
)


def _is_docstring_constant(node: ast.Constant, parent: ast.AST | None) -> bool:
    return (
        isinstance(node.value, str)
        and isinstance(parent, ast.Expr)
    )


def mutation_points(tree: ast.AST) -> dict[str, list[ast.AST]]:
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    points = {family: [] for family in FAMILIES}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Compare)
            and node.ops
            and type(node.ops[0]) in COMPARE_REPLACEMENTS
        ):
            points["comparison_boundary"].append(node)
        if isinstance(node, ast.BinOp) and type(node.op) in BINOP_REPLACEMENTS:
            points["arithmetic_operator"].append(node)
        if isinstance(node, ast.BoolOp) and type(node.op) in BOOLOP_REPLACEMENTS:
            points["boolean_operator"].append(node)
        if isinstance(node, (ast.If, ast.While, ast.IfExp)):
            points["condition_negation"].append(node)
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
            and not _is_docstring_constant(node, parents.get(id(node)))
        ):
            points["numeric_constant"].append(node)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "range"
            and node.args
        ):
            points["range_boundary"].append(node)
        if isinstance(node, ast.Slice) and (node.lower is not None or node.upper is not None):
            points["slice_boundary"].append(node)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in WRAPPER_CALLS
            and len(node.args) == 1
            and not node.keywords
        ):
            points["drop_wrapper_call"].append(node)
        if isinstance(node, ast.Return) and node.value is not None:
            points["return_default"].append(node)
    return points


class TargetedMutator(ast.NodeTransformer):
    def __init__(self, family: str, target_index: int) -> None:
        self.family = family
        self.target_index = target_index
        self.seen = 0
        self.changed = False

    def _target(self) -> bool:
        selected = self.seen == self.target_index
        self.seen += 1
        return selected

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if (
            self.family == "comparison_boundary"
            and node.ops
            and type(node.ops[0]) in COMPARE_REPLACEMENTS
            and self._target()
        ):
            node.ops[0] = COMPARE_REPLACEMENTS[type(node.ops[0])]()
            self.changed = True
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if (
            self.family == "arithmetic_operator"
            and type(node.op) in BINOP_REPLACEMENTS
            and self._target()
        ):
            node.op = BINOP_REPLACEMENTS[type(node.op)]()
            self.changed = True
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        if (
            self.family == "boolean_operator"
            and type(node.op) in BOOLOP_REPLACEMENTS
            and self._target()
        ):
            node.op = BOOLOP_REPLACEMENTS[type(node.op)]()
            self.changed = True
        return node

    def _negate_test(self, node: ast.AST) -> ast.AST:
        if self.family == "condition_negation" and self._target():
            node = ast.UnaryOp(op=ast.Not(), operand=node)
            self.changed = True
        return node

    def visit_If(self, node: ast.If) -> ast.AST:
        self.generic_visit(node)
        node.test = self._negate_test(node.test)
        return node

    def visit_While(self, node: ast.While) -> ast.AST:
        self.generic_visit(node)
        node.test = self._negate_test(node.test)
        return node

    def visit_IfExp(self, node: ast.IfExp) -> ast.AST:
        self.generic_visit(node)
        node.test = self._negate_test(node.test)
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if (
            self.family == "numeric_constant"
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
            and self._target()
        ):
            node.value = node.value + 1 if node.value >= 0 else node.value - 1
            self.changed = True
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if (
            self.family == "range_boundary"
            and isinstance(node.func, ast.Name)
            and node.func.id == "range"
            and node.args
            and self._target()
        ):
            node.args[-1] = ast.BinOp(
                left=node.args[-1],
                op=ast.Add(),
                right=ast.Constant(value=1),
            )
            self.changed = True
            return node
        if (
            self.family == "drop_wrapper_call"
            and isinstance(node.func, ast.Name)
            and node.func.id in WRAPPER_CALLS
            and len(node.args) == 1
            and not node.keywords
            and self._target()
        ):
            self.changed = True
            return node.args[0]
        return node

    def visit_Slice(self, node: ast.Slice) -> ast.AST:
        self.generic_visit(node)
        if (
            self.family == "slice_boundary"
            and (node.lower is not None or node.upper is not None)
            and self._target()
        ):
            target = node.upper if node.upper is not None else node.lower
            changed = ast.BinOp(left=target, op=ast.Add(), right=ast.Constant(value=1))
            if node.upper is not None:
                node.upper = changed
            else:
                node.lower = changed
            self.changed = True
        return node

    def visit_Return(self, node: ast.Return) -> ast.AST:
        self.generic_visit(node)
        if (
            self.family == "return_default"
            and node.value is not None
            and self._target()
        ):
            node.value = ast.Constant(value=None)
            self.changed = True
        return node


def generate_mutants(source: str, per_family: int) -> list[dict[str, str]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    points = mutation_points(tree)
    mutants: list[dict[str, str]] = []
    seen_source: set[str] = set()
    for family in FAMILIES:
        for target_index in range(min(len(points[family]), per_family)):
            candidate = copy.deepcopy(tree)
            mutator = TargetedMutator(family, target_index)
            candidate = mutator.visit(candidate)
            ast.fix_missing_locations(candidate)
            if not mutator.changed:
                continue
            mutated_source = ast.unparse(candidate) + "\n"
            if mutated_source in seen_source:
                continue
            seen_source.add(mutated_source)
            mutants.append({
                "mutant_id": f"{family}:{target_index}",
                "family": family,
                "source": mutated_source,
            })
    return mutants


def load_tasks(benchmark: str, limit: int) -> list[Task]:
    if benchmark == "humaneval":
        original = {
            row["task_id"]: row
            for row in load_dataset("openai/openai_humaneval", split="test")
        }
        plus = load_dataset("evalplus/humanevalplus", split="test")
        tasks = []
        for row in plus:
            base = original[row["task_id"]]
            tasks.append(Task(
                benchmark=benchmark,
                task_id=str(row["task_id"]),
                # EvalPlus repairs several original reference solutions.  The
                # stronger reference must pass both oracles; using the legacy
                # solution would incorrectly turn reference bugs into invalid
                # evaluation tasks.
                source=row["prompt"] + row["canonical_solution"],
                original_test=base["test"],
                plus_test=row["test"],
                original_call=f"check({base['entry_point']})",
                plus_call=f"check({base['entry_point']})",
            ))
        return tasks[:limit]
    if benchmark == "mbpp":
        plus = load_dataset("evalplus/mbppplus", split="test")
        tasks = []
        for row in plus:
            imports = "\n".join(row.get("test_imports") or [])
            original_test = "\n".join(
                part for part in [imports, "\n".join(row["test_list"])] if part
            )
            tasks.append(Task(
                benchmark=benchmark,
                task_id=str(row["task_id"]),
                source=row["code"],
                original_test=original_test,
                plus_test=row["test"],
                original_call="",
                plus_call="",
            ))
        return tasks[:limit]
    raise ValueError(benchmark)


def run_task(
    runner: ContainerRunner,
    task: Task,
    *,
    per_family: int,
    per_probe_timeout: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    mutants = generate_mutants(task.source, per_family)
    payload = {
        "mutants": [
            {"mutant_id": "canonical", "family": "canonical", "source": task.source},
            *mutants,
        ],
        "original_test": task.original_test,
        "plus_test": task.plus_test,
        "original_call": task.original_call,
        "plus_call": task.plus_call,
        "per_probe_timeout": per_probe_timeout,
    }
    result = runner.run(
        CommandSpec(
            argv=(sys.executable, "-c", DRIVER),
            cwd=Path.cwd(),
            env={
                "PYTHONHASHSEED": "0",
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "TZ": "UTC",
            },
            stdin=json.dumps(payload, ensure_ascii=False),
        ),
        ExecutionPolicy(
            timeout_seconds=timeout_seconds,
            max_output_chars=200_000,
            memory_mb=768,
            cpu_count=1.0,
            pids_limit=64,
            allowed_environment=frozenset({
                "PYTHONHASHSEED",
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_NUM_THREADS",
                "TZ",
            }),
        ),
    )
    row: dict[str, Any] = {
        "benchmark": task.benchmark,
        "task_id": task.task_id,
        "mutants_generated": len(mutants),
        "runner": result.to_dict(),
        "rows": [],
        "valid": False,
    }
    if not result.succeeded:
        return row
    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        return row
    rows = parsed.get("rows", [])
    row["rows"] = rows
    canonical = next(
        (candidate for candidate in rows if candidate["mutant_id"] == "canonical"),
        None,
    )
    row["valid"] = bool(
        canonical
        and canonical["original"]["passed"]
        and canonical["plus"]["passed"]
    )
    return row


def collect(
    benchmark: str,
    *,
    limit: int,
    workers: int,
    per_family: int,
    per_probe_timeout: float,
    container_image: str,
) -> list[dict[str, Any]]:
    tasks = load_tasks(benchmark, limit)
    runner = ContainerRunner(container_image, engine="docker")
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                run_task,
                runner,
                task,
                per_family=per_family,
                per_probe_timeout=per_probe_timeout,
                timeout_seconds=max(
                    30.0,
                    per_family * len(FAMILIES) * per_probe_timeout * 2.5,
                ),
            ): task
            for task in tasks
        }
        for index, future in enumerate(as_completed(futures), 1):
            try:
                results.append(future.result())
            except Exception as exc:
                task = futures[future]
                results.append({
                    "benchmark": benchmark,
                    "task_id": task.task_id,
                    "valid": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "rows": [],
                })
            if index % 20 == 0:
                print(f"{benchmark}: {index}/{len(tasks)}", file=sys.stderr)
    return sorted(results, key=lambda row: row["task_id"])


def witness(row: dict[str, Any]) -> bool:
    return bool(row["original"]["passed"] and not row["plus"]["passed"])


def family_statistics(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats = {
        family: {
            "probes": 0,
            "original_pass": 0,
            "witnesses": 0,
            "witness_tasks": set(),
        }
        for family in FAMILIES
    }
    for task in results:
        if not task.get("valid"):
            continue
        for row in task["rows"]:
            family = row["family"]
            if family not in stats:
                continue
            stats[family]["probes"] += 1
            if row["original"]["passed"]:
                stats[family]["original_pass"] += 1
            if witness(row):
                stats[family]["witnesses"] += 1
                stats[family]["witness_tasks"].add(task["task_id"])
    for row in stats.values():
        row["witness_task_count"] = len(row.pop("witness_tasks"))
        row["yield"] = (
            row["witnesses"] / row["probes"] if row["probes"] else 0.0
        )
    return stats


def build_memory(
    source_benchmark: str,
    stats: dict[str, dict[str, Any]],
    source_results: list[dict[str, Any]],
    *,
    minimum_witness_tasks: int,
) -> tuple[DefectPatternStore, list[str]]:
    patterns: list[DefectPattern] = []
    selected_families = [
        family
        for family in FAMILIES
        if stats[family]["witness_task_count"] >= minimum_witness_tasks
    ]
    selected_families.sort(
        key=lambda family: (-stats[family]["yield"], family)
    )
    for rank, family in enumerate(selected_families):
        cases = []
        for task in source_results:
            if not task.get("valid"):
                continue
            if any(
                row["family"] == family and witness(row)
                for row in task["rows"]
            ):
                cases.append({
                    "case_id": f"{source_benchmark}:{task['task_id']}:{family}",
                    "source_type": "evalplus_differential_replay",
                    "evidence_tier": "confirmed",
                    "dataset": source_benchmark,
                    "dataset_family": f"{source_benchmark}-code-eval",
                    "item_id": task["task_id"],
                })
            if len(cases) >= 16:
                break
        patterns.append(DefectPattern.from_dict({
            "schema_version": MEMORY_SCHEMA_VERSION,
            "pattern_id": f"{rank:02d}-{family}-weak-test-pattern",
            "defect_family": f"evaluator_incompleteness:{family}",
            "summary": (
                f"An incorrect {family} mutant passed the original evaluator "
                "but failed the stronger EvalPlus oracle."
            ),
            "status": "objective_confirmed",
            "required_features": [
                "field:evaluator",
                "evaluator:type:unit_test",
                "capability:execute_candidate",
                f"mutation_point:{family}",
            ],
            "indicative_features": [],
            "counter_features": [
                "evaluator:property_based:allows_multiple_outputs",
            ],
            "verifier_steps": [
                f"Generate one semantics-changing {family} mutant.",
                "Run the original evaluator and an independent stronger oracle.",
                "Treat original-pass/stronger-oracle-fail as a review candidate.",
            ],
            "evidence_cases": cases,
        }))
    return DefectPatternStore(patterns), selected_families


def task_mutants(task: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_family = {family: [] for family in FAMILIES}
    for row in task["rows"]:
        if row["family"] in by_family:
            by_family[row["family"]].append(row)
    return by_family


def round_robin_select(
    by_family: dict[str, list[dict[str, Any]]],
    families: list[str],
    budget: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    depth = 0
    while len(selected) < budget:
        added = False
        for family in families:
            rows = by_family.get(family, [])
            if depth < len(rows):
                selected.append(rows[depth])
                added = True
                if len(selected) >= budget:
                    break
        if not added:
            break
        depth += 1
    return selected


def fill_to_budget(
    selected: list[dict[str, Any]],
    by_family: dict[str, list[dict[str, Any]]],
    family_order: list[str],
    budget: int,
) -> list[dict[str, Any]]:
    result = list(selected)
    used_ids = {row["mutant_id"] for row in result}
    unique_family_order = list(dict.fromkeys(family_order))
    for row in round_robin_select(
        by_family,
        unique_family_order,
        sum(map(len, by_family.values())),
    ):
        if row["mutant_id"] in used_ids:
            continue
        result.append(row)
        used_ids.add(row["mutant_id"])
        if len(result) >= budget:
            break
    return result[:budget]


def evaluate_direction(
    source_benchmark: str,
    target_benchmark: str,
    source_results: list[dict[str, Any]],
    target_results: list[dict[str, Any]],
    *,
    budget: int,
    minimum_witness_tasks: int,
) -> dict[str, Any]:
    source_stats = family_statistics(source_results)
    store, learned_families = build_memory(
        source_benchmark,
        source_stats,
        source_results,
        minimum_witness_tasks=minimum_witness_tasks,
    )
    matcher = DefectPatternMatcher(store)
    schemes = {
        "A_generic": [],
        "D_pattern_guided": [],
        "F_half_guided_half_exploration": [],
    }
    task_pools: list[tuple[str, bool, dict[str, list[dict[str, Any]]]]] = []
    witnessable_tasks = 0
    valid_tasks = 0
    routing_eligible = 0
    for task in target_results:
        if not task.get("valid"):
            continue
        valid_tasks += 1
        by_family = task_mutants(task)
        exhaustive = [
            row
            for family in FAMILIES
            for row in by_family[family]
        ]
        has_witness = any(witness(row) for row in exhaustive)
        witnessable_tasks += int(has_witness)
        task_pools.append((task["task_id"], has_witness, by_family))

        generic = round_robin_select(by_family, list(FAMILIES), budget)
        features = {
            "field:evaluator",
            "evaluator:type:unit_test",
            "capability:execute_candidate",
            *(
                f"mutation_point:{family}"
                for family, rows in by_family.items()
                if rows
            ),
        }
        query = PatternQuery(
            query_id=task["task_id"],
            features=frozenset(features),
            dataset=target_benchmark,
            dataset_family=f"{target_benchmark}-code-eval",
            item_ids=frozenset({task["task_id"]}),
        )
        hits = matcher.match(query, top_k=max(len(learned_families), 1))
        matched = {
            hit.pattern.defect_family.split(":", 1)[1]
            for hit in hits
        }
        guided_families = [
            family for family in learned_families if family in matched
        ]
        routing_eligible += int(bool(guided_families))
        guided = fill_to_budget(
            round_robin_select(by_family, guided_families, budget),
            by_family,
            list(FAMILIES),
            budget,
        )
        half = math.ceil(budget / 2)
        mixed_guided = round_robin_select(by_family, guided_families, half)
        exploration_families = [
            family for family in FAMILIES if family not in set(guided_families)
        ]
        mixed = fill_to_budget(
            mixed_guided,
            by_family,
            [*exploration_families, *FAMILIES],
            budget,
        )
        for name, selected in (
            ("A_generic", generic),
            ("D_pattern_guided", guided),
            ("F_half_guided_half_exploration", mixed),
        ):
            schemes[name].append({
                "task_id": task["task_id"],
                "witnessable": has_witness,
                "probes": len(selected),
                "witnesses": sum(witness(row) for row in selected),
                "detected": any(witness(row) for row in selected),
            })

    def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
        probes = sum(row["probes"] for row in rows)
        witnesses = sum(row["witnesses"] for row in rows)
        detected = sum(row["detected"] for row in rows if row["witnessable"])
        return {
            "probes": probes,
            "witnesses": witnesses,
            "witness_yield": witnesses / probes if probes else 0.0,
            "detected_witnessable_tasks": detected,
            "task_recall": detected / witnessable_tasks if witnessable_tasks else 0.0,
        }
    metrics = {name: summarize(rows) for name, rows in schemes.items()}

    rng = random.Random(20260724)
    random_metrics = []
    for _ in range(500):
        order = list(FAMILIES)
        rng.shuffle(order)
        rows = []
        for task_id, has_witness, by_family in task_pools:
            selected = round_robin_select(by_family, order, budget)
            rows.append({
                "task_id": task_id,
                "witnessable": has_witness,
                "probes": len(selected),
                "witnesses": sum(witness(row) for row in selected),
                "detected": any(witness(row) for row in selected),
            })
        random_metrics.append(summarize(rows))

    def percentile(values: list[float], quantile: float) -> float:
        ordered = sorted(values)
        if not ordered:
            return 0.0
        index = min(int(quantile * len(ordered)), len(ordered) - 1)
        return ordered[index]

    random_control = {}
    for key in ("witness_yield", "task_recall"):
        values = [row[key] for row in random_metrics]
        random_control[key] = {
            "mean": sum(values) / len(values),
            "p05": percentile(values, 0.05),
            "p95": percentile(values, 0.95),
            "maximum": max(values),
        }

    bootstrap_rng = random.Random(20260725)
    paired_differences = {"witness_yield": [], "task_recall": []}
    valid_rows = len(schemes["A_generic"])
    for _ in range(2_000):
        indices = [
            bootstrap_rng.randrange(valid_rows) for _ in range(valid_rows)
        ]
        sampled = {}
        for name in ("A_generic", "D_pattern_guided"):
            rows = [schemes[name][index] for index in indices]
            probes = sum(row["probes"] for row in rows)
            witnesses = sum(row["witnesses"] for row in rows)
            witnessable = sum(row["witnessable"] for row in rows)
            detected = sum(
                row["detected"] for row in rows if row["witnessable"]
            )
            sampled[name] = {
                "witness_yield": witnesses / probes if probes else 0.0,
                "task_recall": detected / witnessable if witnessable else 0.0,
            }
        for key in paired_differences:
            paired_differences[key].append(
                sampled["D_pattern_guided"][key] - sampled["A_generic"][key]
            )
    paired_bootstrap = {
        key: {
            "observed_difference": (
                metrics["D_pattern_guided"][key] - metrics["A_generic"][key]
            ),
            "ci95": [
                percentile(values, 0.025),
                percentile(values, 0.975),
            ],
            "probability_positive": (
                sum(value > 0 for value in values) / len(values)
            ),
        }
        for key, values in paired_differences.items()
    }
    return {
        "source": source_benchmark,
        "target": target_benchmark,
        "budget_per_task": budget,
        "minimum_source_witness_tasks": minimum_witness_tasks,
        "valid_target_tasks": valid_tasks,
        "witnessable_target_tasks": witnessable_tasks,
        "routing_eligible_target_tasks": routing_eligible,
        "learned_pattern_families": learned_families,
        "source_family_statistics": source_stats,
        "memory_sha256": store.sha256,
        "metrics": metrics,
        "random_family_order_control": random_control,
        "paired_bootstrap_D_minus_A": paired_bootstrap,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-humaneval", type=int, default=100)
    parser.add_argument("--limit-mbpp", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--per-family", type=int, default=2)
    parser.add_argument("--budget", type=int, default=6)
    parser.add_argument("--minimum-source-witness-tasks", type=int, default=2)
    parser.add_argument("--per-probe-timeout", type=float, default=5.0)
    parser.add_argument("--container-image", default="ds1000-audit:v1")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if min(
        args.limit_humaneval,
        args.limit_mbpp,
        args.workers,
        args.per_family,
        args.budget,
        args.minimum_source_witness_tasks,
    ) < 1:
        raise ValueError("limits, workers, budgets, and thresholds must be positive")
    if args.per_probe_timeout <= 0:
        raise ValueError("--per-probe-timeout must be positive")
    resolved_image = subprocess.check_output(
        [
            "docker",
            "image",
            "inspect",
            args.container_image,
            "--format",
            "{{.Id}}",
        ],
        text=True,
    ).strip()
    if not resolved_image.startswith("sha256:"):
        raise RuntimeError("container image did not resolve to a Docker sha256 ID")

    humaneval = collect(
        "humaneval",
        limit=args.limit_humaneval,
        workers=args.workers,
        per_family=args.per_family,
        per_probe_timeout=args.per_probe_timeout,
        container_image=resolved_image,
    )
    mbpp = collect(
        "mbpp",
        limit=args.limit_mbpp,
        workers=args.workers,
        per_family=args.per_family,
        per_probe_timeout=args.per_probe_timeout,
        container_image=resolved_image,
    )
    result = {
        "protocol": {
            "selection_features": "solution/evaluator AST structure only",
            "task_text_used_for_selection": False,
            "gold_or_plus_results_used_for_target_selection": False,
            "oracle": "original-pass and EvalPlus-fail",
            "promotion_ceiling": "review",
            "per_family": args.per_family,
            "per_probe_timeout": args.per_probe_timeout,
            "budget_per_task": args.budget,
            "container_image_requested": args.container_image,
            "container_image_resolved": resolved_image,
        },
        "collection": {
            "humaneval": {
                "requested": args.limit_humaneval,
                "valid": sum(row.get("valid", False) for row in humaneval),
            },
            "mbpp": {
                "requested": args.limit_mbpp,
                "valid": sum(row.get("valid", False) for row in mbpp),
            },
        },
        "directions": [
            evaluate_direction(
                "mbpp",
                "humaneval",
                mbpp,
                humaneval,
                budget=args.budget,
                minimum_witness_tasks=args.minimum_source_witness_tasks,
            ),
            evaluate_direction(
                "humaneval",
                "mbpp",
                humaneval,
                mbpp,
                budget=args.budget,
                minimum_witness_tasks=args.minimum_source_witness_tasks,
            ),
        ],
        "raw": {"humaneval": humaneval, "mbpp": mbpp},
    }
    stable_summary = {
        "protocol": result["protocol"],
        "collection": result["collection"],
        "directions": [{
            key: direction[key]
            for key in (
                "source",
                "target",
                "valid_target_tasks",
                "witnessable_target_tasks",
                "learned_pattern_families",
                "metrics",
                "random_family_order_control",
                "paired_bootstrap_D_minus_A",
                "memory_sha256",
            )
        } for direction in result["directions"]],
    }
    result["reproducibility"] = {
        "stable_summary_sha256": hashlib.sha256(
            json.dumps(
                stable_summary,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "excludes_nondeterministic_fields": [
            "runner.elapsed_seconds",
            "raw result ordering",
        ],
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(
        {
            "collection": result["collection"],
            "directions": [
                {
                    "source": row["source"],
                    "target": row["target"],
                    "witnessable_target_tasks": row["witnessable_target_tasks"],
                    "learned_pattern_families": row["learned_pattern_families"],
                    "metrics": row["metrics"],
                }
                for row in result["directions"]
            ],
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
