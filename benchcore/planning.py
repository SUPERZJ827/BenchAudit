from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .coverage import AuditLedgerEntry, COMPLETED_STATUSES, ledger_entry_dict
from .package_scan import ArtifactKind, BenchmarkPackage
from .schema import BenchmarkItem


@dataclass(frozen=True)
class CheckerCapability:
    name: str
    requires_any: frozenset[ArtifactKind] = frozenset()
    requires_all: frozenset[ArtifactKind] = frozenset()
    families: frozenset[str] = frozenset({"generic"})
    evidence_level: str = "static"
    cost_class: str = "low"
    needs_llm: bool = False
    needs_execution: bool = False


@dataclass(frozen=True)
class PlannedCheck:
    name: str
    status: str
    reason: str
    evidence_level: str
    cost_class: str


@dataclass
class AuditPlan:
    family: str
    family_confidence: float
    checks: list[PlannedCheck] = field(default_factory=list)
    artifact_coverage: dict[str, str] = field(default_factory=dict)
    unknowns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "family_confidence": self.family_confidence,
            "checks": [asdict(check) for check in self.checks],
            "artifact_coverage": dict(self.artifact_coverage),
            "unknowns": list(self.unknowns),
            "summary": {
                "executed": sum(check.status == "executed" for check in self.checks),
                "partial": sum(check.status == "partial" for check in self.checks),
                "failed": sum(check.status == "failed" for check in self.checks),
                "ineligible": sum(check.status == "ineligible" for check in self.checks),
                "selected": sum(check.status == "selected" for check in self.checks),
                "skipped": sum(check.status == "skipped" for check in self.checks),
                "unsupported": sum(check.status == "unsupported" for check in self.checks),
            },
        }


CORE_CAPABILITIES: tuple[CheckerCapability, ...] = (
    CheckerCapability("task_specification", requires_any=frozenset({ArtifactKind.TASK_SPECIFICATION})),
    CheckerCapability("context_attachment", requires_any=frozenset({ArtifactKind.CONTEXT, ArtifactKind.TASK_SPECIFICATION})),
    CheckerCapability("expected_output", requires_any=frozenset({ArtifactKind.OUTPUT_CONTRACT, ArtifactKind.TASK_SPECIFICATION})),
    CheckerCapability("oracle_ground_truth", requires_any=frozenset({ArtifactKind.ORACLE, ArtifactKind.TASK_SPECIFICATION})),
    CheckerCapability("evaluator", requires_any=frozenset({ArtifactKind.EVALUATOR, ArtifactKind.TASK_SPECIFICATION})),
    CheckerCapability("contract_consistency", requires_all=frozenset({ArtifactKind.TASK_SPECIFICATION, ArtifactKind.EVALUATOR})),
    # This replays BenchAudit's declared answer contract parser; it does not
    # execute benchmark-supplied code and therefore needs no sandbox backend.
    CheckerCapability(
        "evaluator_replay",
        requires_all=frozenset({ArtifactKind.ORACLE, ArtifactKind.EVALUATOR}),
        evidence_level="deterministic_replay",
    ),
    CheckerCapability(
        "execution_evaluator_audit",
        requires_all=frozenset({ArtifactKind.ORACLE, ArtifactKind.EVALUATOR}),
        evidence_level="executed_differential",
        cost_class="high",
        needs_llm=True,
        needs_execution=True,
    ),
    CheckerCapability("metamorphic_answer", requires_any=frozenset({ArtifactKind.ORACLE, ArtifactKind.EVALUATOR})),
    CheckerCapability("evaluator_mutation", requires_any=frozenset({ArtifactKind.EVALUATOR}), evidence_level="counterfactual"),
    CheckerCapability("task_integrity", requires_any=frozenset({ArtifactKind.TASK_SPECIFICATION})),
    CheckerCapability("executable_evidence", requires_any=frozenset({ArtifactKind.ORACLE, ArtifactKind.TASK_SPECIFICATION}), evidence_level="execution"),
    CheckerCapability("differential_candidate", requires_any=frozenset({ArtifactKind.ORACLE, ArtifactKind.TASK_SPECIFICATION}), evidence_level="differential"),
    CheckerCapability("duplicate_conflict", requires_any=frozenset({ArtifactKind.TASK_SPECIFICATION})),
    CheckerCapability("schema_drift", requires_any=frozenset({ArtifactKind.TASK_SPECIFICATION})),
    CheckerCapability("llm_semantic_audit", requires_any=frozenset({ArtifactKind.TASK_SPECIFICATION}), evidence_level="llm", cost_class="medium", needs_llm=True),
    CheckerCapability("cross_artifact_consistency", requires_all=frozenset({ArtifactKind.TASK_SPECIFICATION, ArtifactKind.EVALUATOR}), evidence_level="llm", cost_class="medium", needs_llm=True),
    CheckerCapability("grounded_rubric_consistency", requires_all=frozenset({ArtifactKind.TASK_SPECIFICATION, ArtifactKind.EVALUATOR}), families=frozenset({"workspacebench", "rubric"}), evidence_level="llm", cost_class="medium", needs_llm=True),
    CheckerCapability("rubric_output_contract_consistency", requires_all=frozenset({ArtifactKind.EVALUATOR, ArtifactKind.OUTPUT_CONTRACT}), families=frozenset({"workspacebench", "rubric"}), evidence_level="llm", cost_class="medium", needs_llm=True),
    CheckerCapability("workspace_artifact_invariants", requires_all=frozenset({ArtifactKind.TASK_SPECIFICATION, ArtifactKind.EVALUATOR}), families=frozenset({"workspacebench"}), evidence_level="artifact_replay", cost_class="low"),
    CheckerCapability("workspace_rubric_grounding", requires_all=frozenset({ArtifactKind.TASK_SPECIFICATION, ArtifactKind.EVALUATOR}), families=frozenset({"workspacebench"}), evidence_level="llm_verified", cost_class="high", needs_llm=True),
    CheckerCapability("solution_leak", requires_all=frozenset({ArtifactKind.TASK_SPECIFICATION, ArtifactKind.ORACLE}), families=frozenset({"swebench", "code"}), evidence_level="static"),
    CheckerCapability("trace_failure_cluster", requires_any=frozenset({ArtifactKind.TRACE}), evidence_level="behavioral", cost_class="medium"),
    CheckerCapability("environment_replay", requires_all=frozenset({ArtifactKind.ENVIRONMENT, ArtifactKind.EVALUATOR}), evidence_level="execution", cost_class="high", needs_execution=True),
    CheckerCapability("provenance_contamination", requires_any=frozenset({ArtifactKind.PROVENANCE, ArtifactKind.ORACLE}), evidence_level="provenance", cost_class="medium"),
)


def detect_benchmark_family(
    package: BenchmarkPackage,
    items: Iterable[BenchmarkItem] | None = None,
) -> tuple[str, float, list[str]]:
    paths = "\n".join(
        artifact.relative_path.lower()
        for artifact in package.artifacts
        if not artifact.relative_path.startswith("@canonical/")
    )
    kinds = package.kinds()
    reasons: list[str] = []
    scores = {
        "generic": 0.1,
        "swebench": 0.0,
        "workspacebench": 0.0,
        "terminalbench": 0.0,
        "code": 0.0,
        "rubric": 0.0,
    }
    if "problem_statement" in paths or "gold_patch" in paths or "fail_to_pass" in paths:
        scores["swebench"] += 0.8
        reasons.append("SWE-bench field/file naming detected")
    if any(token in paths for token in ("rubric", "workspacebench", "input_files", "output_files")):
        scores["workspacebench"] += 0.7
        scores["rubric"] += 0.4
        reasons.append("rubric/workspace artifact naming detected")
    if any(path.endswith((".py", ".java", ".go", ".rs", ".js", ".ts")) for path in paths.splitlines()):
        scores["code"] += 0.45
        reasons.append("source code artifacts detected")
    if ArtifactKind.EVALUATOR in kinds and ArtifactKind.OUTPUT_CONTRACT in kinds:
        scores["rubric"] += 0.25
    sampled_items = list(items or [])[:100]
    if sampled_items:
        raw_keys = {
            str(key).lower()
            for item in sampled_items
            for key in item.raw
        }
        evaluator_text = "\n".join(
            str(item.evaluator).lower()
            for item in sampled_items
            if item.evaluator not in (None, "", [], {})
        )
        contract_text = "\n".join(
            str(item.output_contract).lower()
            for item in sampled_items
            if item.output_contract not in (None, "", [], {})
        )
        if (
            {"problem_statement", "patch", "test_patch", "fail_to_pass"}.intersection(raw_keys)
            or "swebench" in evaluator_text
            or "git_patch" in contract_text
        ):
            scores["swebench"] += 0.95
            reasons.append("SWE-bench record schema/evaluator detected")
        if (
            {"rubrics", "rubric_types", "file_dep_graph", "tested_capabilities"}.intersection(raw_keys)
            or "workspacebench" in evaluator_text
            or "workspace_files" in contract_text
        ):
            scores["workspacebench"] += 0.9
            scores["rubric"] += 0.5
            reasons.append("Workspace/rubric record schema detected")
        if (
            {"task_toml", "instruction", "has_tests", "has_environment"}.intersection(raw_keys)
            or "terminal_bench" in evaluator_text
            or "terminal_task" in contract_text
        ):
            scores["terminalbench"] += 0.9
            reasons.append("terminal-agent record schema/evaluator detected")
    family, raw_score = max(scores.items(), key=lambda entry: entry[1])
    if family == "generic" or raw_score < 0.35:
        return "generic", 0.35, reasons or ["no family-specific signature detected"]
    return family, min(raw_score, 0.99), reasons


def build_audit_plan(
    package: BenchmarkPackage,
    *,
    items: Iterable[BenchmarkItem] | None = None,
    family_override: str | None = None,
    capabilities: Iterable[CheckerCapability] = CORE_CAPABILITIES,
    available_llm: bool = False,
    available_execution: bool = False,
) -> AuditPlan:
    family, confidence, reasons = detect_benchmark_family(package, items)
    if family_override is not None:
        family = family_override
        confidence = 1.0
        reasons.append(f"family explicitly selected as {family_override}")
    kinds = package.kinds()
    checks: list[PlannedCheck] = []
    for capability in capabilities:
        status, reason = _plan_capability(
            capability,
            family=family,
            kinds=kinds,
            available_llm=available_llm,
            available_execution=available_execution,
        )
        checks.append(PlannedCheck(
            name=capability.name,
            status=status,
            reason=reason,
            evidence_level=capability.evidence_level,
            cost_class=capability.cost_class,
        ))
    coverage = {
        kind.value: ("present" if kind in kinds else "missing")
        for kind in ArtifactKind
        if kind != ArtifactKind.UNKNOWN
    }
    unknowns = list(package.warnings)
    unknowns.extend(reasons)
    if package.truncated:
        unknowns.append("package scan was truncated; artifact coverage is incomplete")
    if ArtifactKind.UNKNOWN in kinds:
        unknowns.append("one or more files have an unresolved artifact role")
    return AuditPlan(
        family=family,
        family_confidence=confidence,
        checks=checks,
        artifact_coverage=coverage,
        unknowns=_deduplicate(unknowns),
    )


def plan_for_executed_methods(
    package: BenchmarkPackage,
    methods_run: Iterable[str],
    *,
    base_plan: AuditPlan | None = None,
    audit_ledger: Iterable[AuditLedgerEntry | dict[str, Any]] | None = None,
) -> AuditPlan:
    methods = list(dict.fromkeys(methods_run))
    capabilities = {capability.name: capability for capability in CORE_CAPABILITIES}
    plan = base_plan or build_audit_plan(
        package, available_llm=True, available_execution=True
    )
    by_name = {check.name: check for check in plan.checks}
    ledger_rows = [ledger_entry_dict(row) for row in (audit_ledger or [])]
    rows_by_checker: dict[str, list[dict[str, Any]]] = {}
    for row in ledger_rows:
        rows_by_checker.setdefault(str(row.get("checker") or ""), []).append(row)
    executed: list[PlannedCheck] = []
    for method in methods:
        known = capabilities.get(method)
        planned = by_name.get(method)
        status, reason = _ledger_method_status(method, rows_by_checker.get(method, []))
        executed.append(PlannedCheck(
            name=method,
            status=status,
            reason=reason,
            evidence_level=(known.evidence_level if known else (planned.evidence_level if planned else "unknown")),
            cost_class=(known.cost_class if known else (planned.cost_class if planned else "unknown")),
        ))
    executed_names = set(methods)
    executed_capabilities = {_capability_alias(method) for method in methods}
    for check in plan.checks:
        if check.name not in executed_names and check.name not in executed_capabilities:
            executed.append(check)
    plan.checks = executed
    return plan


def _ledger_method_status(
    method: str,
    rows: list[dict[str, Any]],
) -> tuple[str, str]:
    """Summarize actual checker outcomes, never checker instantiation.

    Deliberate inapplicability is not a failure.  Conversely, an exception,
    security refusal, abstention, unsupported input, or undeclared eligibility
    must prevent the plan from claiming that a method "executed" completely.
    """

    if not rows:
        return "failed", "checker was instantiated but produced no coverage-ledger rows"
    distribution: dict[str, int] = {}
    for row in rows:
        status = str(row["status"])
        distribution[status] = distribution.get(status, 0) + 1
    completed = sum(
        str(row["status"]) in COMPLETED_STATUSES and bool(row.get("completed"))
        for row in rows
    )
    unknown = sum(bool(row.get("coverage_unknown")) for row in rows)
    ineligible = distribution.get("ineligible", 0)
    detail = ", ".join(f"{key}={value}" for key, value in sorted(distribution.items()))
    if ineligible == len(rows):
        return "ineligible", f"checker was not applicable to any item ({detail})"
    if completed and unknown:
        return "partial", (
            f"checker completed {completed}/{len(rows)} ledger rows but {unknown} "
            f"row(s) retain unresolved coverage ({detail})"
        )
    if completed:
        return "executed", f"checker completed all applicable rows ({detail})"
    return "failed", f"checker completed no auditable row ({detail})"


def apply_family_policy(plan: AuditPlan) -> AuditPlan:
    """Apply narrow family exclusions without discarding common checks.

    Agent benchmarks use executable tests or rubrics as their oracle and often
    have no scalar reference answer. Only that incompatible scalar-gold check is
    disabled; all family-agnostic structural checks remain eligible.
    """
    if plan.family not in {"workspacebench", "terminalbench"}:
        return plan
    plan.checks = [
        PlannedCheck(
            name=check.name,
            status="skipped",
            reason=(
                "agent-family policy: evaluator/tests/rubric are the oracle; "
                "a scalar gold answer is not required"
            ),
            evidence_level=check.evidence_level,
            cost_class=check.cost_class,
        )
        if check.name == "oracle_ground_truth"
        else check
        for check in plan.checks
    ]
    return plan


def _plan_capability(
    capability: CheckerCapability,
    *,
    family: str,
    kinds: set[ArtifactKind],
    available_llm: bool,
    available_execution: bool,
) -> tuple[str, str]:
    if capability.families != frozenset({"generic"}) and family not in capability.families:
        return "skipped", f"not applicable to detected family {family}"
    missing_all = capability.requires_all - kinds
    if missing_all:
        return "unsupported", "missing required artifacts: " + ", ".join(sorted(kind.value for kind in missing_all))
    if capability.requires_any and not capability.requires_any.intersection(kinds):
        return "unsupported", "none of the alternative required artifacts are present"
    if capability.needs_llm and not available_llm:
        return "skipped", "LLM capability not enabled"
    if capability.needs_execution and not available_execution:
        return "skipped", "safe execution capability not enabled"
    return "selected", "requirements satisfied"


def _deduplicate(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _capability_alias(method: str) -> str:
    if method.startswith("llm_"):
        return "llm_semantic_audit"
    return method


def write_audit_plan_markdown(path: Path, package: BenchmarkPackage, plan: AuditPlan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = plan.to_dict()
    lines = [
        "# Benchmark Audit Plan",
        "",
        f"- Package root: `{package.root}`",
        f"- Detected family: `{plan.family}` (confidence={plan.family_confidence:.2f})",
        f"- Files scanned: `{package.scan_metadata.get('files_scanned', len(package.artifacts))}`",
        f"- Selected checks: `{data['summary']['selected']}`",
        f"- Skipped checks: `{data['summary']['skipped']}`",
        f"- Unsupported checks: `{data['summary']['unsupported']}`",
        "",
        "## Artifact Coverage",
        "",
    ]
    for name, status in sorted(plan.artifact_coverage.items()):
        lines.append(f"- `{name}`: `{status}`")
    lines.extend(["", "## Checks", ""])
    for check in plan.checks:
        lines.append(
            f"- `{check.name}`: **{check.status}** — {check.reason} "
            f"(evidence={check.evidence_level}, cost={check.cost_class})"
        )
    if plan.unknowns:
        lines.extend(["", "## Unknowns and Warnings", ""])
        lines.extend(f"- {warning}" for warning in plan.unknowns)
    lines.extend(["", "## Artifact Inventory", ""])
    for artifact in package.artifacts:
        lines.append(
            f"- `{artifact.relative_path}` — `{artifact.kind.value}`; "
            f"{artifact.size_bytes} bytes; sha256=`{artifact.sha256[:16]}…`"
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
