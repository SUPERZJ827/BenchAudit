"""Offline counterfactual: blanket response downgrade vs claim-scoped invalidation.

Reads only the five frozen SVAMP reports.  Zero API calls, zero re-runs, and
labels are loaded after the rule has already decided what to drop.

The question it answers: when a quantity response contradicts itself, must the
whole response be discarded, or only the claims whose evidence was the
contradicted field?

Usage:
    python scripts/verify_quantity_consistency_scoping.py [handoff_dir]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DEFAULT_HANDOFF = Path("/home/zhoujun/llmdata/handoff_svamp_fp_n5")

# A stand-in for the real rationale extractor.  It reproduces the blanket-rule
# counts on four of the five runs and differs by one finding on full_4, so the
# comparison below is directional; rerun it with the production extractor
# before quoting exact numbers.
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_FINAL_CLAIM = re.compile(
    r"(?:derived answer is|answer is|answer should be|final answer is)\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

# Claims whose evidence *is* the structured answer.  A response that
# contradicts its own structured answer cannot support these.  Everything else
# -- notably a constraint violation recorded in `checks` -- is grounded
# elsewhere in the same response and survives.
DERIVED_ANSWER_CLAIMS = frozenset({"wrong_gold_answer"})


def _single_number(values: object) -> float | None:
    if not isinstance(values, list) or len(values) != 1:
        return None
    match = _NUMBER.fullmatch(str(values[0]).strip().replace(",", ""))
    return float(match.group()) if match else None


def response_contradicts_itself(result: dict) -> bool:
    """Whether the structured answer disagrees with the rationale's conclusion.

    Abstains rather than guessing: no single parseable answer, or no explicit
    final claim in the rationale, means not identifiable.
    """

    derived = _single_number(result.get("derived_answers"))
    if derived is None or result.get("solution_status") != "solved":
        return False
    claims = _FINAL_CLAIM.findall(result.get("rationale") or "")
    if not claims:
        return False
    return abs(float(claims[-1]) - derived) > 1e-9


def _predicted_items(report: dict) -> tuple[set[str], set[str], set[str]]:
    """Item sets under: no rule, blanket downgrade, claim-scoped invalidation."""

    baseline: set[str] = set()
    blanket: set[str] = set()
    scoped: set[str] = set()
    for violation in report["violations"]:
        if violation.get("defect_scope") == "presentation":
            continue
        item = violation["item_id"]
        baseline.add(item)
        result = (violation.get("evidence") or {}).get("llm_result") or {}
        contradicted = "quantity" in str(
            violation.get("detection_method")
        ) and response_contradicts_itself(result)
        if not contradicted:
            blanket.add(item)
        if not (contradicted and violation["defect_type"] in DERIVED_ANSWER_CLAIMS):
            scoped.add(item)
    return baseline, blanket, scoped


def main(handoff: Path) -> int:
    manifest = json.loads(
        (handoff / "svamp_platinum_pilot100.manifest.json").read_text(encoding="utf-8")
    )
    # Labels are read here and used only for scoring, never by the rule above.
    truth = {
        entry["item_id"]
        for entry in manifest["selected"]
        if entry.get("label") not in (None, "", "clean")
    }
    print(f"scope={len(manifest['selected'])}  labelled-defective={len(truth)}\n")

    header = f"{'run':<8}{'baseline':>12}{'blanket':>12}{'claim-scoped':>15}"
    print(header)
    print("-" * len(header))
    totals = {"baseline": [0, 0], "blanket": [0, 0], "scoped": [0, 0]}
    divergences: list[str] = []
    for index in range(1, 6):
        report = json.loads(
            (handoff / f"runs/full_{index}.json").read_text(encoding="utf-8")
        )
        baseline, blanket, scoped = _predicted_items(report)
        cells = []
        for name, predicted in (
            ("baseline", baseline), ("blanket", blanket), ("scoped", scoped)
        ):
            tp, fp = len(predicted & truth), len(predicted - truth)
            totals[name][0] += tp
            totals[name][1] += fp
            cells.append(f"{tp}/{fp}")
        print(f"full_{index:<3}{cells[0]:>12}{cells[1]:>12}{cells[2]:>15}")
        for item in sorted(scoped - blanket):
            kind = "TP" if item in truth else "FP"
            divergences.append(f"  full_{index}  {item.split('-', 2)[-1]:<10} kept as {kind}")

    print("-" * len(header))
    summary = {name: "{}/{}".format(*counts) for name, counts in totals.items()}
    print(
        f"{'total':<8}{summary['baseline']:>12}"
        f"{summary['blanket']:>12}{summary['scoped']:>15}"
    )
    print("\nWhere the two rules disagree (blanket drops it, claim-scoped keeps it):")
    print("\n".join(divergences) if divergences else "  none")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_HANDOFF))
