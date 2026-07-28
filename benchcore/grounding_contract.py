"""Shared semantic contract for Workspace rubric-grounding decisions.

The contract separates requirement legitimacy from output satisfaction and
detector responsibility. It is intentionally compact enough to be injected
into both scanner and verifier system prompts without creating a second,
divergent definition of the labels.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GroundingDecisionContract:
    version: str
    prompt_fragment: str
    statuses: tuple[str, ...]
    requirement_kinds: tuple[str, ...]
    detector_families: tuple[str, ...]


GROUNDING_DECISION_CONTRACT_V1 = GroundingDecisionContract(
    version="workspace-grounding-decision-contract-v1-20260729",
    statuses=("supported", "unsupported", "uncertain"),
    requirement_kinds=(
        "hidden_exact_constraint",
        "intrinsic_validity",
        "general_quality",
        "task_or_input_derived",
        "task_contract_conflict",
        "insufficient_evidence",
    ),
    detector_families=(
        "workspace_rubric_grounding",
        "task_contract",
        "artifact_execution",
        "input_recomputation",
        "subjective_quality_review",
        "unknown",
    ),
    prompt_fragment="""GROUNDING DECISION CONTRACT
version: workspace-grounding-decision-contract-v1-20260729

Judge requirement legitimacy, not whether an unseen candidate output satisfies
the requirement.
- supported: explicitly requested; uniquely derivable without an unstated
  filter, rounding rule, threshold or tie-break; intrinsic artifact validity;
  or an ordinary general-quality requirement.
- unsupported: a mandatory exact constraint lacks visible provenance, or the
  requirement conflicts with the task/output contract.
- uncertain: relevant evidence is missing, truncated, conflicting, or permits
  multiple legitimate interpretations.

Responsibility boundaries:
- Missing provenance for a rubric literal is workspace_rubric_grounding.
- A contradiction among task, required filename, delivery form and output
  contract is task_contract.
- Whether the delivered artifact actually opens or satisfies a valid
  requirement is artifact_execution, not grounding.
- Recomputing a value from visible inputs is input_recomputation.
- Clarity, professionalism and visual quality are legitimate requirements but
  normally require subjective_quality_review.

Never infer that a legitimate requirement is unsupported merely because the
candidate output is unavailable. Never treat a plausible implementation choice
as mandatory support.""",
)


def grounding_contract_prompt() -> str:
    return GROUNDING_DECISION_CONTRACT_V1.prompt_fragment

