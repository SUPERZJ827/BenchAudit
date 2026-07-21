from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .checkers import DEFAULT_CHECKERS, Checker, _violation
from .coverage import (
    AuditControlFlow,
    AuditEligibility,
    AuditLedgerEntry,
)
from .methods import DatasetChecker
from .schema import BenchmarkItem, Violation
from .promotion import enforce_all


@dataclass
class AuditRunResult:
    """Findings and coverage are separate, equally important audit outputs."""

    violations: list[Violation]
    ledger: list[AuditLedgerEntry]

    @property
    def coverage_ledger(self) -> list[AuditLedgerEntry]:
        return self.ledger


def audit_items(
    items: list[BenchmarkItem],
    root: Path | None = None,
    checkers: list[Checker] | None = None,
    dataset_checkers: list[DatasetChecker] | None = None,
    progress_callback: Callable[[int, int, BenchmarkItem], None] | None = None,
    workers: int = 1,
) -> list[Violation]:
    """Compatibility API returning only findings.

    This retains the historical fail-fast exception behavior.  New production
    callers should use :func:`audit_items_with_ledger`, which isolates checker
    failures and makes coverage gaps explicit.
    """

    return audit_items_with_ledger(
        items,
        root=root,
        checkers=checkers,
        dataset_checkers=dataset_checkers,
        progress_callback=progress_callback,
        workers=workers,
        fail_fast=True,
    ).violations


def audit_items_with_ledger(
    items: list[BenchmarkItem],
    root: Path | None = None,
    checkers: list[Checker] | None = None,
    dataset_checkers: list[DatasetChecker] | None = None,
    progress_callback: Callable[[int, int, BenchmarkItem], None] | None = None,
    workers: int = 1,
    *,
    fail_fast: bool = False,
) -> AuditRunResult:
    """Audit items and record every planned item-by-checker outcome.

    A normal empty return becomes ``completed_no_finding``, never ``clean``.
    Legacy checkers without an explicit ``audit_eligibility`` contract retain
    ``eligible=None``, so reports expose their applicability as unknown.
    Unexpected checker exceptions are isolated as ``operational_failed`` by
    default.  Set ``fail_fast=True`` only for compatibility/debugging.
    """

    active = list(DEFAULT_CHECKERS if checkers is None else checkers)
    active_dataset = list(dataset_checkers or [])
    _ensure_unique_row_uids(items)
    violations: list[Violation] = []
    ledger: list[AuditLedgerEntry] = []
    total = len(items)

    def check_item(
        item: BenchmarkItem,
    ) -> tuple[list[Violation], list[AuditLedgerEntry]]:
        found: list[Violation] = []
        item_ledger: list[AuditLedgerEntry] = []
        for checker in active:
            checker_findings, entry = _run_item_checker(
                checker,
                item,
                root=root,
                fail_fast=fail_fast,
            )
            found.extend(checker_findings)
            item_ledger.append(entry)
        return found, item_ledger

    if workers <= 1:
        for completed, item in enumerate(items, 1):
            item_findings, item_ledger = check_item(item)
            violations.extend(item_findings)
            ledger.extend(item_ledger)
            if progress_callback is not None:
                progress_callback(completed, total, item)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(check_item, item): (index, item)
                for index, item in enumerate(items)
            }
            completed_rows: dict[
                int,
                tuple[list[Violation], list[AuditLedgerEntry]],
            ] = {}
            for completed, future in enumerate(as_completed(futures), 1):
                index, item = futures[future]
                completed_rows[index] = future.result()
                if progress_callback is not None:
                    progress_callback(completed, total, item)
            # Completion order depends on scheduling.  Reports and caches must
            # not, so merge worker-local results in the original item order.
            for index in range(len(items)):
                item_findings, item_ledger = completed_rows[index]
                violations.extend(item_findings)
                ledger.extend(item_ledger)

    for checker in active_dataset:
        checker_findings, checker_ledger = _run_dataset_checker(
            checker,
            items,
            fail_fast=fail_fast,
        )
        violations.extend(checker_findings)
        ledger.extend(checker_ledger)

    pre_fusion_count = len(violations)
    fused = fuse_llm_evidence(violations, items)
    enforced = enforce_all(fused, items)
    for finding in enforced[pre_fusion_count:]:
        # Fusion is a real post-checker audit phase.  Record it explicitly so
        # final findings cannot appear after the coverage ledger was closed.
        ledger.append(AuditLedgerEntry(
            item_id=finding.item_id,
            checker=finding.detection_method,
            status="finding",
            reason="post-checker evidence reconciliation emitted a finding",
            lifecycle=["planned", "eligible", "attempted", "finding"],
            eligible=True,
            attempted=True,
            completed=True,
            finding_count=1,
            substantive_finding_count=(
                0 if finding.defect_scope == "operational" else 1
            ),
            checker_scope="fusion",
            details={"phase": "post_checker_evidence_reconciliation"},
            row_uid=finding.row_uid,
        ))
    enforced = _consolidate_choice_encoding_candidates(enforced)
    return AuditRunResult(violations=enforced, ledger=ledger)


def _consolidate_choice_encoding_candidates(
    violations: list[Violation],
) -> list[Violation]:
    """Replace N unknown-encoding item candidates with one dataset review."""

    superseded_rows: set[str] = set()
    for finding in violations:
        if finding.defect_type != "choice_encoding_contract_mismatch":
            continue
        if finding.evidence.get("encoding_mode") != "unknown_cardinality_consistent":
            continue
        targets = finding.evidence.get("target_row_uids")
        if isinstance(targets, list):
            superseded_rows.update(str(value) for value in targets if value is not None)
    if not superseded_rows:
        return violations
    return [
        finding for finding in violations
        if not (
            finding.defect_type == "invalid_choice_gold"
            and finding.row_uid is not None
            and str(finding.row_uid) in superseded_rows
        )
    ]


def _checker_name(checker: Any) -> str:
    value = str(getattr(checker, "name", "")).strip()
    return value or checker.__class__.__name__


def _checker_eligibility(
    checker: Any,
    item: BenchmarkItem,
    root: Path | None,
) -> AuditEligibility:
    method = getattr(checker, "audit_eligibility", None)
    if not callable(method):
        return AuditEligibility.unknown(
            "legacy checker does not declare an applicability contract"
        )
    value = method(item, root=root)
    if isinstance(value, AuditEligibility):
        return value
    if isinstance(value, bool):
        return (
            AuditEligibility.applicable("checker declared the item applicable")
            if value
            else AuditEligibility.not_applicable(
                "checker declared the item inapplicable"
            )
        )
    if value is None:
        return AuditEligibility.unknown()
    raise TypeError(
        "audit_eligibility must return AuditEligibility, bool, or None; "
        f"got {type(value).__name__}"
    )


def _run_item_checker(
    checker: Checker,
    item: BenchmarkItem,
    *,
    root: Path | None,
    fail_fast: bool,
) -> tuple[list[Violation], AuditLedgerEntry]:
    checker_name = _checker_name(checker)
    try:
        eligibility = _checker_eligibility(checker, item, root)
    except AuditControlFlow as exc:
        return [], _control_entry(
            item.item_id,
            item.row_uid,
            checker_name,
            exc,
            eligible=None,
            attempted=False,
            checker_scope="item",
        )
    except Exception as exc:  # noqa: BLE001 - one checker must not erase a run
        if fail_fast:
            raise
        return [], _exception_entry(
            item.item_id,
            item.row_uid,
            checker_name,
            exc,
            eligible=None,
            attempted=False,
            phase="eligibility",
            checker_scope="item",
        )

    if eligibility.status is not None or eligibility.eligible is False:
        status = eligibility.status or "ineligible"
        lifecycle = ["planned", status]
        return [], AuditLedgerEntry(
            item_id=item.item_id,
            checker=checker_name,
            status=status,
            reason=eligibility.reason,
            lifecycle=lifecycle,
            eligible=False,
            attempted=False,
            completed=False,
            checker_scope="item",
            row_uid=item.row_uid,
        )

    findings: list[Violation] = []
    try:
        result = checker.check(item, root=root)
        _extend_validated(findings, result, item=item)
    except AuditControlFlow as exc:
        return findings, _control_entry(
            item.item_id,
            item.row_uid,
            checker_name,
            exc,
            eligible=eligibility.eligible,
            attempted=True,
            checker_scope="item",
            findings=findings,
        )
    except Exception as exc:  # noqa: BLE001 - coverage must retain the failure
        if fail_fast:
            raise
        return findings, _exception_entry(
            item.item_id,
            item.row_uid,
            checker_name,
            exc,
            eligible=eligibility.eligible,
            attempted=True,
            phase="check",
            checker_scope="item",
            findings=findings,
        )

    return findings, _completed_entry(
        item.item_id,
        item.row_uid,
        checker_name,
        eligibility,
        findings,
        checker_scope="item",
    )


def _run_dataset_checker(
    checker: DatasetChecker,
    items: list[BenchmarkItem],
    *,
    fail_fast: bool,
) -> tuple[list[Violation], list[AuditLedgerEntry]]:
    """Project one dataset-level invocation onto item-by-checker coverage rows."""

    checker_name = _checker_name(checker)
    eligibilities: list[AuditEligibility] = []
    for item in items:
        try:
            value = checker.audit_eligibility(item, items)
            if not isinstance(value, AuditEligibility):
                raise TypeError(
                    "dataset audit_eligibility must return AuditEligibility; "
                    f"got {type(value).__name__}"
                )
            eligibilities.append(value)
        except Exception:
            if fail_fast:
                raise
            eligibilities.append(AuditEligibility.unknown(
                "dataset checker applicability evaluation failed"
            ))
    findings: list[Violation] = []
    failure: AuditControlFlow | Exception | None = None
    should_attempt = any(
        value.eligible is not False and value.status is None
        for value in eligibilities
    )
    if should_attempt:
        try:
            result = checker.check(items)
            _extend_validated(findings, result, dataset_items=items)
        except AuditControlFlow as exc:
            failure = exc
        except Exception as exc:  # noqa: BLE001 - isolate a failed dataset method
            if fail_fast:
                raise
            failure = exc

    findings_by_row: dict[str, list[Violation]] = {}
    for violation in findings:
        targets = violation.evidence.get("target_row_uids")
        if not isinstance(targets, list) or not targets:
            targets = [violation.row_uid] if violation.row_uid is not None else []
        for row_uid in dict.fromkeys(
            str(value) for value in targets if value is not None
        ):
            findings_by_row.setdefault(row_uid, []).append(violation)

    entries: list[AuditLedgerEntry] = []
    for item_index, item in enumerate(items):
        item_findings = findings_by_row.get(str(item.row_uid), [])
        eligibility = eligibilities[item_index]
        if eligibility.status is not None or eligibility.eligible is False:
            status = eligibility.status or "ineligible"
            entry = AuditLedgerEntry(
                item_id=item.item_id,
                checker=checker_name,
                status=status,
                reason=eligibility.reason,
                lifecycle=["planned", status],
                eligible=False,
                attempted=False,
                completed=False,
                checker_scope="dataset",
                row_uid=item.row_uid,
            )
        elif isinstance(failure, AuditControlFlow):
            entry = _control_entry(
                item.item_id,
                item.row_uid,
                checker_name,
                failure,
                eligible=eligibility.eligible,
                attempted=True,
                checker_scope="dataset",
                findings=item_findings,
            )
        elif failure is not None:
            entry = _exception_entry(
                item.item_id,
                item.row_uid,
                checker_name,
                failure,
                eligible=eligibility.eligible,
                attempted=True,
                phase="dataset_check",
                checker_scope="dataset",
                findings=item_findings,
            )
        else:
            entry = _completed_entry(
                item.item_id,
                item.row_uid,
                checker_name,
                eligibility,
                item_findings,
                checker_scope="dataset",
            )
        entries.append(entry)
    return findings, entries


def _extend_validated(
    destination: list[Violation],
    values: Iterable[Violation] | None,
    *,
    item: BenchmarkItem | None = None,
    dataset_items: list[BenchmarkItem] | None = None,
) -> None:
    if values is None:
        return
    for value in values:
        if not isinstance(value, Violation):
            raise TypeError(
                "checker.check must yield Violation objects; "
                f"got {type(value).__name__}"
            )
        if item is not None:
            if value.item_id != item.item_id:
                raise ValueError(
                    "item checker emitted a finding for a different item_id"
                )
            if value.row_uid is None:
                value.row_uid = item.row_uid
            elif value.row_uid != item.row_uid:
                raise ValueError(
                    "item checker emitted a finding for a different row_uid"
                )
            if value.source_row_sha256 is None:
                value.source_row_sha256 = item.source_row_sha256
            elif value.source_row_sha256 != item.source_row_sha256:
                raise ValueError(
                    "item checker emitted a finding for different source-row bytes"
                )
        if dataset_items is not None:
            _validate_dataset_finding_identity(value, dataset_items)
        destination.append(value)


def _validate_dataset_finding_identity(
    finding: Violation,
    items: list[BenchmarkItem],
) -> None:
    by_uid = {
        str(item.row_uid): item
        for item in items
        if item.row_uid is not None
    }
    targets = finding.evidence.get("target_row_uids")
    if targets is not None:
        if (
            not isinstance(targets, list)
            or not targets
            or any(not isinstance(value, str) for value in targets)
            or len(set(targets)) != len(targets)
            or any(value not in by_uid for value in targets)
        ):
            raise ValueError(
                "dataset checker emitted invalid or unknown target_row_uids"
            )
        if finding.row_uid is None:
            finding.row_uid = targets[0]
        elif str(finding.row_uid) not in targets:
            raise ValueError(
                "dataset finding row_uid is not one of its declared targets"
            )
    elif finding.row_uid is None:
        matches = [item for item in items if item.item_id == finding.item_id]
        if len(matches) != 1:
            raise ValueError(
                "dataset finding without row_uid has an ambiguous item_id"
            )
        finding.row_uid = matches[0].row_uid

    source = by_uid.get(str(finding.row_uid))
    if source is None or source.item_id != finding.item_id:
        raise ValueError(
            "dataset finding identity does not match a live canonical row"
        )
    if finding.source_row_sha256 is None:
        finding.source_row_sha256 = source.source_row_sha256
    elif finding.source_row_sha256 != source.source_row_sha256:
        raise ValueError(
            "dataset finding identity does not match live source-row bytes"
        )


def _completed_entry(
    item_id: str,
    row_uid: str | None,
    checker_name: str,
    eligibility: AuditEligibility,
    findings: list[Violation],
    *,
    checker_scope: str,
) -> AuditLedgerEntry:
    operational = [
        finding
        for finding in findings
        if finding.defect_type == "llm_audit_failure"
        or finding.evidence.get("audit_coverage_status") == "operational_failed"
    ]
    security = [
        finding
        for finding in findings
        if finding.evidence.get("audit_coverage_status") == "security_blocked"
        or finding.evidence.get("evidence_level") == "path_policy_block"
        or bool(finding.evidence.get("blocked_paths"))
    ]
    substantive = [
        finding
        for finding in findings
        if finding.defect_scope != "operational"
        and finding.defect_type != "llm_audit_failure"
    ]

    inferred_eligible = eligibility.eligible
    if substantive:
        # Producing a benchmark finding is direct evidence that the checker
        # considered itself applicable, even for a legacy checker.
        inferred_eligible = True

    if security:
        status = "security_blocked"
        reason = (
            f"checker was blocked by security policy evidence in {len(security)} "
            "finding(s); audit coverage is incomplete"
        )
        completed = False
    elif operational:
        status = "operational_failed"
        reason = (
            f"checker emitted {len(operational)} operational failure finding(s); "
            "no benchmark-quality conclusion is available"
        )
        completed = False
    elif findings:
        status = "finding"
        reason = f"checker completed and emitted {len(findings)} finding(s)"
        completed = True
    else:
        status = "completed_no_finding"
        reason = (
            "checker completed without emitting a finding; this is not evidence "
            "that the item is clean"
        )
        if eligibility.eligible is None:
            reason += "; checker applicability was not declared"
        completed = True

    lifecycle = ["planned"]
    if inferred_eligible is True:
        lifecycle.append("eligible")
    lifecycle.append("attempted")
    lifecycle.append(status)
    return AuditLedgerEntry(
        item_id=item_id,
        checker=checker_name,
        status=status,
        reason=reason,
        lifecycle=lifecycle,
        eligible=inferred_eligible,
        attempted=True,
        completed=completed,
        finding_count=len(findings),
        substantive_finding_count=len(substantive),
        checker_scope=checker_scope,
        details={"eligibility_reason": eligibility.reason},
        row_uid=row_uid,
    )


def _control_entry(
    item_id: str,
    row_uid: str | None,
    checker_name: str,
    exc: AuditControlFlow,
    *,
    eligible: bool | None,
    attempted: bool,
    checker_scope: str,
    findings: list[Violation] | None = None,
) -> AuditLedgerEntry:
    findings = findings or []
    lifecycle = ["planned"]
    if eligible is True:
        lifecycle.append("eligible")
    if attempted:
        lifecycle.append("attempted")
    lifecycle.append(exc.status)
    return AuditLedgerEntry(
        item_id=item_id,
        checker=checker_name,
        status=exc.status,
        reason=exc.reason,
        lifecycle=lifecycle,
        eligible=eligible,
        attempted=attempted,
        completed=False,
        finding_count=len(findings),
        substantive_finding_count=sum(
            finding.defect_scope != "operational" for finding in findings
        ),
        checker_scope=checker_scope,
        details={**exc.details, "partial_findings": len(findings)},
        row_uid=row_uid,
    )


def _exception_entry(
    item_id: str,
    row_uid: str | None,
    checker_name: str,
    exc: Exception,
    *,
    eligible: bool | None,
    attempted: bool,
    phase: str,
    checker_scope: str,
    findings: list[Violation] | None = None,
) -> AuditLedgerEntry:
    findings = findings or []
    lifecycle = ["planned"]
    if eligible is True:
        lifecycle.append("eligible")
    if attempted:
        lifecycle.append("attempted")
    lifecycle.append("operational_failed")
    return AuditLedgerEntry(
        item_id=item_id,
        checker=checker_name,
        status="operational_failed",
        reason=f"{phase} raised {type(exc).__name__}: {exc}",
        lifecycle=lifecycle,
        eligible=eligible,
        attempted=attempted,
        completed=False,
        finding_count=len(findings),
        substantive_finding_count=sum(
            finding.defect_scope != "operational" for finding in findings
        ),
        checker_scope=checker_scope,
        details={
            "phase": phase,
            "exception_type": type(exc).__name__,
            "partial_findings": len(findings),
        },
        row_uid=row_uid,
    )


def fuse_llm_evidence(
    violations: list[Violation],
    items: list[BenchmarkItem],
) -> list[Violation]:
    _ensure_unique_row_uids(items)
    id_groups: dict[str, list[BenchmarkItem]] = {}
    for item in items:
        id_groups.setdefault(item.item_id, []).append(item)
    for violation in violations:
        if violation.row_uid is None and len(id_groups.get(violation.item_id, [])) == 1:
            violation.row_uid = id_groups[violation.item_id][0].row_uid
    items_by_row = {
        str(item.row_uid): item for item in items if item.row_uid is not None
    }
    by_item: dict[str, list[Violation]] = {}
    added_violations: list[Violation] = []
    for violation in violations:
        row_key = str(violation.row_uid) if violation.row_uid is not None else ""
        by_item.setdefault(row_key, []).append(violation)

    for row_uid, item_violations in by_item.items():
        item = items_by_row.get(row_uid)
        observations = (
            item.metadata.get("_llm_observations", {})
            if item is not None
            else {}
        )
        llm_methods = {
            violation.detection_method.split("+", 1)[0]
            for violation in item_violations
            if violation.detection_method.startswith("llm_")
            and violation.defect_type != "llm_audit_failure"
        }
        non_llm_defects = {
            violation.defect_type
            for violation in item_violations
            if not violation.detection_method.startswith("llm_")
        }
        corroborated = len(llm_methods) >= 2
        contradictions = observation_contradictions(observations)
        # Applicability-only: substantive violations from llm_option_applicability
        # with no other LLM or static method corroboration are exploratory signals.
        other_substantive_llm = llm_methods - {"llm_option_applicability"}
        applicability_only = (
            not other_substantive_llm
            and not non_llm_defects
            and "llm_option_applicability" in llm_methods
        )

        for violation in item_violations:
            if not violation.detection_method.startswith("llm_"):
                continue
            if violation.defect_type == "llm_audit_failure":
                continue
            base_method = violation.detection_method.split("+", 1)[0]
            relevant_contradictions = [
                contradiction["reason"]
                for contradiction in contradictions
                if base_method in contradiction["affected_methods"]
            ]
            if relevant_contradictions:
                violation.review_only = True
                violation.severity = "review"
                violation.evidence["auditor_contradictions"] = relevant_contradictions
                continue
            result = violation.evidence.get("llm_result", {})
            if (
                violation.detection_method == "llm_question_clarity"
                and violation.defect_type in non_llm_defects
            ):
                # Corroboration is useful ranking evidence, but the LLM row is
                # never itself promoted.  Any objective non-LLM finding is
                # already present as its own independently tiered violation.
                violation.evidence["corroborated_by_non_llm"] = True
            if bool(result.get("needs_expert", False)):
                violation.review_only = True
                violation.severity = "review"
                continue
            if corroborated:
                violation.evidence["llm_corroborated_by"] = sorted(llm_methods)
            if applicability_only and violation.detection_method == "llm_option_applicability":
                violation.evidence["exploratory"] = True
        if contradictions and item is not None:
            added_violations.append(
                _violation(
                    item,
                    "auditor_contradiction",
                    1.0,
                    "LLM auditors produced mutually inconsistent conclusions.",
                    {
                        "reasons": [
                            contradiction["reason"]
                            for contradiction in contradictions
                        ],
                        "affected_methods": sorted(
                            {
                                method
                                for contradiction in contradictions
                                for method in contradiction["affected_methods"]
                            }
                        ),
                        "observations": observations,
                    },
                    severity="review",
                    review_only=True,
                    repair="Resolve the auditor disagreement before confirming a benchmark defect.",
                    method="llm_evidence_fusion",
                    scope="operational",
                )
            )
    violations.extend(added_violations)
    return violations


def _ensure_unique_row_uids(items: list[BenchmarkItem]) -> None:
    """Assign deterministic identities without trusting benchmark item IDs."""

    seen: set[str] = set()
    for index, item in enumerate(items):
        candidate = str(item.row_uid or "")
        if not candidate or candidate in seen:
            candidate = f"audit-row-{index:08d}"
            while candidate in seen:  # defensive against adversarial explicit IDs
                candidate += "-dup"
            item.row_uid = candidate
        seen.add(candidate)


def observation_contradictions(observations: dict) -> list[dict]:
    contradictions = []
    gold = observations.get("llm_gold_audit", {})
    option = observations.get("llm_option_set", {})

    gold_answers = {
        str(value).strip().upper()
        for value in gold.get("correct_answers", [])
        if value not in (None, "")
    }
    option_best = set()
    for entry in option.get("option_statuses", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("best_answer_status") in {"best", "acceptable"}:
            label = entry.get("label")
            if label:
                option_best.add(str(label).strip().upper())

    if gold_answers and option_best and gold_answers.isdisjoint(option_best):
        contradictions.append(
            {
                "reason": (
                    f"gold correct_answers={sorted(gold_answers)} conflicts with "
                    f"option best_answers={sorted(option_best)}"
                ),
                "affected_methods": {"llm_gold_audit", "llm_option_set"},
            }
        )

    option_defect = option.get("defect_type")
    best_cardinality = option.get(
        "best_answer_cardinality",
        option.get("cardinality"),
    )
    if option_defect == "multiple_correct_answers" and best_cardinality == "exactly_one":
        contradictions.append(
            {
                "reason": (
                    "option defect says multiple_correct_answers but cardinality is exactly_one"
                ),
                "affected_methods": {"llm_option_set"},
            }
        )
    if option_defect == "no_correct_answer" and best_cardinality == "exactly_one":
        contradictions.append(
            {
                "reason": (
                    "option defect says no_correct_answer but cardinality is exactly_one"
                ),
                "affected_methods": {"llm_option_set"},
            }
        )

    declared_gold = str(observations.get("_declared_gold", "")).strip().upper()
    if (
        gold.get("gold_status") == "contradicted"
        and declared_gold
        and declared_gold in option_best
    ):
        contradictions.append(
            {
                "reason": (
                    "gold auditor contradicts the declared gold while option auditor "
                    "still marks it as best"
                ),
                "affected_methods": {"llm_gold_audit", "llm_option_set"},
            }
        )
    return contradictions
