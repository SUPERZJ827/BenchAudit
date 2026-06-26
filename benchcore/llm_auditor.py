from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .checkers import Checker, _violation
from .evaluators import CHOICE_LABELS, choice_label_to_index, parse_number
from .llm_client import LLMClient
from .schema import BenchmarkItem, Violation


DIRECT_AUDIT_SYSTEM_PROMPT = """You are a benchmark quality auditor.
Given a multiple-choice benchmark item with its declared gold answer, determine whether the item contains any quality defects.

Return only JSON:
{
  "has_defect": true | false,
  "defect_types": [],
  "confidence": 0.0,
  "needs_expert": false,
  "rationale": "under 100 words"
}

Defect types to assess (list all that apply, or empty list if none):
- "wrong_gold_answer"         – declared gold is incorrect
- "no_correct_answer"         – no supplied option is correct
- "multiple_correct_answers"  – more than one option is correct
- "bad_options_clarity"       – options are unclear, ambiguous, or uninterpretable
- "ambiguous_goal"            – question has multiple interpretations that change the answer
- "missing_condition"         – task requires unstated information to determine the answer
- "missing_context"           – task references external material not provided

Rules:
- Evaluate all choices, not just the gold.
- Only report defects that materially affect evaluation validity.
- Factual difficulty alone is not a defect.
- Use needs_expert=true when the conclusion depends on professional, textbook, or jurisdictional conventions.
"""


GOLD_SYSTEM_PROMPT = """You are the Gold Auditor in a benchmark quality audit system.
Evaluate whether the declared gold answer is supported by the task, context, and choices.

Return only JSON:
{
  "gold_status": "supported" | "contradicted" | "uncertain",
  "defect_type": "none" | "wrong_gold_answer" | "no_correct_answer",
  "correct_answers": ["A"] or [],
  "confidence": 0.0,
  "needs_expert": false,
  "rationale": "under 80 words"
}

Rules:
- Solve the task independently before inspecting whether the gold agrees.
- Preserve notation and definitions introduced by the task.
- Do not reinterpret a defined symbol with its ordinary meaning to rescue the gold.
- For best/most complete/most specific questions, accept the unique best answer.
- If the answer depends on a convention, source, jurisdiction, or expert knowledge, return uncertain and needs_expert=true.
- For medicine, law, psychology, accounting, and other professional domains, mark needs_expert=true when the conclusion depends on a textbook-specific or professional convention rather than a direct formal derivation.
- Use no_correct_answer only when none of the supplied choices/accepted forms is correct.
"""

BLIND_SOLVER_SYSTEM_PROMPT = """You are the Blind Solver in a benchmark quality audit system.
Solve the task without access to its declared gold answer.

Return only JSON:
{
  "solution_status": "solved" | "ambiguous" | "uncertain",
  "derived_answers": ["the answer in open-ended form"],
  "confidence": 0.0,
  "needs_expert": false,
  "assumption_risk": "none" | "conventional" | "answer_changing",
  "required_assumptions": ["..."],
  "claims": [
    {
      "claim": "short atomic claim",
      "evidence_type": "calculation" | "definition" | "task_text" | "external_source" | "assumption",
      "support": "short derivation or evidence"
    }
  ],
  "rationale": "under 100 words"
}

Rules:
- The answer choices and declared benchmark gold are deliberately hidden. Do not infer them.
- Preserve notation and definitions introduced by the task.
- Solve the task in open-ended form and state the most precise answer justified by the question.
- Before calculating, build a consistency ledger over entities, quantities, events, and time points.
- Check that quantities remain feasible: counts cannot become negative, consumed or removed subsets cannot
  exceed the available total, and stated subtotals must be compatible with stated totals.
- Resolve pronouns and repeated entity names literally. A self-comparison, wrong subject, or impossible
  event history is a task defect, not an invitation to silently repair the wording.
- Answer the exact temporal or action question asked. Distinguish brought from later bought, initial from
  final, and rate-duration statements from already-produced quantities.
- Irrelevant numbers are allowed and should simply be ignored when the task remains internally consistent.
- If the question itself has multiple genuinely different answers, return ambiguous.
- If the premises are internally contradictory or arithmetically impossible and no unique answer is
  justified, return ambiguous with assumption_risk=answer_changing.
- Put standard notation or universally conventional definitions under assumption_risk=conventional.
- Use assumption_risk=answer_changing only for an unstated choice that could materially change the answer.
- Expose answer-changing assumptions instead of silently selecting one.
- Mark needs_expert=true for source-, textbook-, jurisdiction-, or professional-convention-dependent conclusions.
"""

ANSWER_OPTION_MATCHER_SYSTEM_PROMPT = """You are the Answer-to-Option Matcher in a benchmark quality audit system.
The task was solved without seeing its choices. Compare the open-ended derived answer with every choice.

Return only JSON:
{
  "matches": [
    {
      "label": "A",
      "relation": "equivalent" | "not_equivalent" | "uncertain",
      "confidence": 0.0,
      "rationale": "short"
    }
  ],
  "needs_expert": false,
  "rationale": "under 80 words"
}

Rules:
- Match semantic equivalence to the derived answer, not mere logical implication.
- A weaker property, broader superclass, narrower special case, related fact, or partially correct statement is not equivalent.
- Example: if the derived answer is 'Abelian group', 'commutative semigroup' is not equivalent.
- Equivalent notation, paraphrases, numeric forms, and choice text expressing the same answer are equivalent.
- Do not select the closest option when no option is equivalent.
- Do not use the declared gold; it is deliberately hidden.
- Return uncertain only when equivalence truly depends on missing context or convention.
"""

OPTION_APPLICABILITY_SYSTEM_PROMPT = """You are the Independent Option Applicability Auditor in a benchmark quality audit system.
Evaluate whether each answer choice independently satisfies the task as written.
Do not compare choices only to the blind solver's answer, and do not assume the declared gold is correct.

Return only JSON:
{
  "option_assessments": [
    {
      "label": "A",
      "status": "acceptable" | "not_acceptable" | "uncertain",
      "confidence": 0.0,
      "assumptions": ["..."],
      "rationale": "short"
    }
  ],
  "question_mode": "identity" | "property" | "best_answer" | "statement_combination" | "other",
  "needs_expert": false,
  "rationale": "under 80 words"
}

Rules:
- Test each choice directly against the task, using the same task interpretation for every choice.
- acceptable means the evaluator should accept that option as a correct answer.
- A choice may be acceptable even when it is not semantically equivalent to another acceptable choice.
- Example: for 'Which number is prime?', both 2 and 3 are acceptable although they are not equivalent.
- For identity/definition questions, a weaker property, superclass, subclass, or related fact is not acceptable when it does not answer the requested identity.
- For explicit or conventional best/most/primary questions, mark only choices that satisfy the requested best-answer criterion as acceptable.
- Use the ordinary educational reading of the wording. If rejecting an option requires a stricter technical interpretation of an otherwise compatible qualifier, return uncertain rather than not_acceptable.
- A partially more specific description remains acceptable when the added qualifier is true under the ordinary intended reading; reject it only when the qualifier is materially false.
- Invalid, malformed, or low-quality non-gold distractors are not substantive defects unless they affect the accepted answer set; presentation corruption is handled separately.
- Return uncertain when acceptance depends on missing context, source convention, jurisdiction, or an answer-changing assumption.
"""


GOLD_DEFENDER_SYSTEM_PROMPT = """You are the Gold Defender in a benchmark quality audit system.
Given a task, its declared gold, and a blind solution, construct the strongest valid case for the gold.
Do not rescue the gold by changing task notation, inventing missing facts, or using an unreasonable convention.

Return only JSON:
{
  "gold_support": "supported" | "unsupported" | "uncertain",
  "confidence": 0.0,
  "needs_expert": false,
  "assumptions_required": ["..."],
  "claims": [
    {
      "claim": "short atomic claim",
      "evidence_type": "calculation" | "definition" | "task_text" | "external_source" | "assumption",
      "support": "short support"
    }
  ],
  "rationale": "under 100 words"
}

Rules:
- Explicitly identify assumptions required to support the gold.
- If support depends on missing source context or a disputed convention, return uncertain.
- If the gold cannot be defended under the task as written, return unsupported.
"""


GOLD_CHALLENGER_SYSTEM_PROMPT = """You are the Gold Challenger in a benchmark quality audit system.
Given a task, its declared gold, and a blind solution, actively search for a decisive counterexample,
an alternative correct answer, or proof that no supplied answer is correct.

Return only JSON:
{
  "gold_validity": "valid" | "invalid" | "uncertain",
  "defect_type": "none" | "wrong_gold_answer" | "no_correct_answer" | "multiple_correct_answers",
  "alternative_answers": ["B"],
  "confidence": 0.0,
  "needs_expert": false,
  "counterclaims": [
    {
      "claim": "short atomic challenge",
      "evidence_type": "calculation" | "definition" | "task_text" | "external_source" | "assumption",
      "support": "short counterevidence"
    }
  ],
  "rationale": "under 100 words"
}

Rules:
- Try to falsify the gold rather than merely restating the blind solution.
- Preserve definitions and notation from the task.
- A weak or malformed non-gold distractor is not a defect unless grading is affected.
- For best-answer questions, distinguish weaker literal truths from accepted best answers.
- Return uncertain when the challenge depends on unavailable sources or professional conventions.
"""


QUESTION_SYSTEM_PROMPT = """You are the Question Clarity Auditor in a benchmark quality audit system.
Do not solve only for the gold. Audit whether the task statement contains enough information to determine the intended answer.

Return only JSON:
{
  "clarity_status": "clear" | "answer_changing_ambiguity" | "missing_condition" | "missing_context" | "uncertain",
  "confidence": 0.0,
  "needs_expert": false,
  "assumptions_used": ["..."],
  "missing_information": ["..."],
  "alternative_interpretations": [
    {"interpretation": "short description", "answer": "A"}
  ],
  "rationale": "under 80 words"
}

Rules:
- Flag only defects that can change the answer, make the task unsolvable, or leave multiple materially different interpretations.
- Do not flag harmless grammar, awkward wording, minor typos, or information already embedded in the task.
- Build a consistency ledger over entities, quantities, events, and time points before declaring the task clear.
- Treat impossible quantity histories as substantive defects: negative remaining counts, consuming or
  removing more than exists, exceeding a stated number of distinct items, or incompatible totals and subtotals.
- Treat a repeated or wrong entity reference that changes the unknown as a defect; do not silently repair it.
- Distinguish the time or action named by the question, such as brought versus later bought and initial versus final.
- Extra irrelevant quantities are not defects when the requested answer remains uniquely determined.
- Do not assume separately counted groups are disjoint unless the wording states or entails exclusivity.
- If a grammatically plausible scope changes whether a rate is per individual or collective, return
  answer_changing_ambiguity and include both resulting answers.
- If you can state a plausible alternative interpretation with a different numeric answer, do not dismiss
  it merely because one reading is more conventional.
- Do not assume an unstated linearity, jurisdiction, date, convention, source, population, or unit when it changes the answer.
- Do not flag a conventional textbook default merely because it is unstated when the convention is standard in the named task and the choices make the intended interpretation unique. Flag only when a plausible alternative changes the answer.
- A symbolic graph written in text, such as H -> U <- P, counts as provided context; do not demand an image.
- If a standard field convention resolves the task but conventions differ, return uncertain and needs_expert=true.
"""


OPTION_SYSTEM_PROMPT = """You are the Option Set Auditor in a benchmark quality audit system.
Audit every answer choice, not just the gold.

Return only JSON:
{
  "option_statuses": [
    {
      "label": "A",
      "literal_truth": "true" | "false" | "uncertain" | "invalid",
      "best_answer_status": "best" | "acceptable" | "weaker" | "irrelevant" | "invalid",
      "clarity": "clear" | "unclear" | "corrupted",
      "equivalence_group": "optional group id or null",
      "confidence": 0.0,
      "rationale": "short"
    }
  ],
  "literal_cardinality": "exactly_one" | "multiple" | "none" | "uncertain",
  "best_answer_cardinality": "exactly_one" | "multiple" | "none" | "uncertain",
  "defect_type": "none" | "multiple_correct_answers" | "no_correct_answer" | "bad_options_clarity",
  "confidence": 0.0,
  "needs_expert": false,
  "rationale": "under 80 words"
}

Rules:
- Evaluate each option using the same definitions and notation as the task.
- Separate literal truth from best-answer status. A weaker true property may be literally true but not an acceptable best answer.
- Only use the best-answer convention when the stem explicitly or conventionally asks for best/most/primary/generally/most appropriate. Do not use it to hide two independently valid answers in an ordinary "which is true" question.
- Equivalent logical/program expressions must share an equivalence_group even when variable names or syntax differ.
- A bad distractor is not a benchmark defect unless it creates multiple valid answers, no valid answer, is uninterpretable, or overlaps the gold in an answer-changing way.
- Do not flag an irrelevant invalid non-gold distractor if the gold remains uniquely correct and grading is unaffected.
- Mark presentation-only corruption in clarity, even if it does not change the best answer; use bad_options_clarity with review-level confidence.
- Use uncertain and needs_expert=true for textbook, professional, jurisdictional, or source conventions.
"""

PRESENTATION_SYSTEM_PROMPT = """You are the Presentation Integrity Auditor in a benchmark quality audit system.
Inspect the exact task package for OCR, encoding, segmentation, truncation, and formatting corruption.
Report corruption even when a capable model can silently repair it and still solve the task.

Return only JSON:
{
  "issues": [
    {
      "artifact": "task_specification" | "context_attachment" | "choices" | "oracle_ground_truth" | "expected_output" | "evaluator",
      "location": "short field/choice location",
      "issue_type": "ocr_corruption" | "encoding_corruption" | "lost_math_markup" | "truncation" | "segmentation_error" | "format_conversion",
      "raw_text": "exact problematic text",
      "interpreted_text": "the repaired form required to understand it",
      "repair_operations": ["inserted ^", "merged choices C and D"],
      "confidence": 0.0,
      "rationale": "short"
    }
  ],
  "confidence": 0.0,
  "rationale": "under 80 words"
}

Rules:
- Compare the exact raw text with the form you must mentally reconstruct to understand it.
- Report silent repairs such as 1.5 x 1017 interpreted as 1.5 × 10^17, lost superscripts, broken LaTeX, mojibake, OCR substitutions, truncated expressions, or one option split into two.
- Inspect task text, context, every choice, gold representation, output contract, evaluator, tests, and rubric when present.
- Do not report grammar style, awkward but understandable wording, difficulty, factual incorrectness, or harmless representation differences.
- 0.025 versus 2.5% is not corruption when both are explicit and unambiguous.
- A malformed non-gold distractor is still a presentation defect, even when it does not change the unique correct answer.
- If a field is represented as a BenchCore transport preview with "__benchcore_payload_truncated__": true,
  do not report that preview truncation as a benchmark artifact defect. Only report truncation when
  the original artifact itself visibly contains a truncation marker or missing segment.
- Do not silently normalize corrupted text and return no issues.
"""

QUANTITY_CONSISTENCY_SYSTEM_PROMPT = """You are a structured quantity parser for benchmark auditing.
Do not decide whether the benchmark is defective. Convert the task into explicit, machine-checkable
quantity constraints and identify material entity/action reference issues.

Return only JSON:
{
  "derived_answers": ["numeric answer justified by the task"] or [],
  "solution_status": "solved" | "contradictory" | "ambiguous" | "uncertain",
  "checks": [
    {
      "check_type": "availability" | "subset_total" | "state_transition" | "rate_time" | "total_parts" | "other",
      "left_expression": "14 + 13",
      "left_value": 27,
      "relation": "<=" | ">=" | "==" | "<" | ">",
      "right_expression": "initial cookies",
      "right_value": 17,
      "fully_grounded": true,
      "material_to_answer": true,
      "confidence": 0.0,
      "evidence": "short quote or derivation"
    }
  ],
  "reference_issues": [
    {
      "issue_type": "wrong_entity" | "self_reference" | "action_scope" | "time_scope" | "semantic_role",
      "material_to_answer": true | false,
      "confidence": 0.0,
      "evidence": "short exact explanation"
    }
  ],
  "confidence": 0.0,
  "rationale": "under 100 words"
}

Rules:
- The declared gold answer is hidden. Solve independently.
- Emit a check whenever the story implies a necessary numeric invariant.
- Set fully_grounded=true only when every variable in both expressions has been substituted with a
  concrete number. For example, after deriving 3 packages, use 13 * 3 == 39, never 13 * packages == 39.
- Set material_to_answer=true only when failure of the constraint changes the requested answer,
  prevents a unique answer, or makes a quantity directly used by the answer invalid.
- Contradictions confined to an irrelevant entity or unused historical detail are not material.
- For removal or consumption, total removed must not exceed the available amount.
- A subset or completed count must not exceed its explicitly stated total.
- Initial + additions - removals must equal a stated final amount.
- Parts and subtotals must be compatible with an explicitly stated total.
- In recipes or capacity statements, an already-added amount exceeding the required amount is an internal
  inconsistency even when a different ingredient is queried; mark whether it affects the requested answer.
- Preserve units and entities; do not combine unrelated quantities.
- Preserve semantic roles such as price, cost, revenue, profit, amount earned, inventory, and capacity.
  Do not silently treat "the shop makes $X off an item" as the item's customer price or cost.
- When a number of people is mentioned next to a rate, determine whether the rate is per person or collective.
  If both readings are grammatically plausible and yield different answers, report a material reference issue.
- Distinguish brought from later bought, initial from final, and yesterday from today.
- A number may be irrelevant. Do not invent a constraint merely because two numbers coexist.
- Use the numeric values implied by the literal text, even when they make a constraint fail.
- Report repeated or wrong subjects and action/time mismatches only when they change what is asked.
- For reference issues, set material_to_answer=true only when the issue changes the requested quantity
  or makes that quantity indeterminate. An impossible event concerning an unused entity is false.
"""

EVENT_STATE_SYSTEM_PROMPT = """You are an event-state parser for benchmark auditing.
Do not judge the benchmark and do not use a declared gold answer. Extract state transitions and
semantic-role conflicts so a program can validate them.

Return only JSON:
{
  "state_models": [
    {
      "entity": "salty cookies",
      "unit": "cookies",
      "initial_value": 6 or null,
      "events": [
        {
          "operation": "add" | "remove" | "set",
          "amount": 3,
          "stage": 1,
          "evidence": "ate 3 salty cookies"
        }
      ],
      "stated_final_value": 3 or null,
      "required_limit": null,
      "material_to_answer": true,
      "confidence": 0.0
    }
  ],
  "role_conflicts": [
    {
      "stated_role": "profit per item",
      "queried_role": "customer price",
      "same_quantity_justified": false,
      "material_to_answer": true,
      "confidence": 0.0,
      "evidence": "The shop makes $X off each item, but the question asks what it costs."
    }
  ],
  "confidence": 0.0,
  "rationale": "under 100 words"
}

Rules:
- Keep distinct entities separate, including sweet versus salty cookies and wrappers versus bottle caps.
- Order events by their occurrence in the story.
- add means found, received, bought, entered, produced, or otherwise increased.
- remove means ate, gave, sold, lost, left, got off, used, or otherwise decreased.
- set records an explicit observed state such as "now has 12".
- required_limit is an explicit recipe requirement, capacity, depth, inventory maximum, or stated total
  that the entity must not exceed under the described action.
- Always emit a state model when the text contains both a required/capacity amount and an actual amount,
  even if that entity is not used by the final arithmetic. Example: "recipe calls for 6 cups of flour;
  already added 12" means required_limit=6 and the post-event flour state is 12.
- Treat depth, total path length, distance already traveled, and remaining distance as distinct roles.
  If the described travel exceeds an explicit total depth/length without explanation, emit a state model
  with that depth/length as required_limit or a role conflict.
- If initial is unstated but additions/removals and a final value imply it, leave initial_value null;
  the program will infer it.
- Phrases such as "after deleting some", "after selling some", or "some more got on" contain an unknown
  add/remove event. Emit that event with amount=null before the observed final set.
- Mark material_to_answer=true only when the invalid state changes the requested answer, invalidates an
  event directly used to derive it, or makes the requested quantity impossible. Otherwise use false.
- Do not equate profit, revenue, earnings, selling price, purchase price, and cost unless the text does.
- Do not flag harmless irrelevant numbers or merely unrealistic magnitudes.
"""


class BaseLLMAuditor(Checker):
    prompt = ""
    name = "llm_auditor"

    def __init__(
        self,
        client: LLMClient,
        confirm_threshold: float = 0.75,
        review_threshold: float = 0.45,
    ):
        self.client = client
        self.confirm_threshold = confirm_threshold
        self.review_threshold = review_threshold
        self.last_error: str | None = None

    def query(self, item: BenchmarkItem) -> dict[str, Any] | None:
        self.last_error = None
        item.metadata.setdefault("_llm_observations", {})["_declared_gold"] = item.gold
        try:
            result = self.client.chat_json(self.prompt, build_user_prompt(item))
            item.metadata.setdefault("_llm_observations", {})[self.name] = result
            return result
        except RuntimeError as exc:
            self.last_error = str(exc)
            item.metadata.setdefault("_llm_observations", {})[self.name] = {
                "audit_failure": str(exc)
            }
            return None

    def failure_violation(self, item: BenchmarkItem) -> Violation:
        return _violation(
            item,
            "llm_audit_failure",
            1.0,
            f"{self.name} failed to produce a usable result.",
            {"auditor": self.name, "error": self.last_error},
            severity="review",
            review_only=True,
            repair="Retry the failed auditor call or inspect provider output.",
            method=self.name,
            scope="operational",
        )


class GoldLLMAuditor(BaseLLMAuditor):
    name = "llm_gold_audit"
    prompt = GOLD_SYSTEM_PROMPT

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if not item.task or item.gold in (None, ""):
            return []
        result = self.query(item)
        if not result:
            return [self.failure_violation(item)] if self.last_error else []
        return list(gold_violations(item, result, self.confirm_threshold, self.review_threshold))


class EvidenceGoldLLMAuditor(BaseLLMAuditor):
    """Blind solve first, then use adversarial evidence only when risk warrants it."""

    name = "llm_gold_audit"

    def __init__(
        self,
        client: LLMClient,
        confirm_threshold: float = 0.75,
        review_threshold: float = 0.45,
        mode: str = "cascade",
    ):
        super().__init__(client, confirm_threshold, review_threshold)
        if mode not in {"cascade", "full"}:
            raise ValueError(f"Unknown evidence gold mode: {mode}")
        self.mode = mode

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if not item.task or item.gold in (None, ""):
            return []
        self.last_error = None
        observations = item.metadata.setdefault("_llm_observations", {})
        observations["_declared_gold"] = item.gold
        try:
            blind = self.client.chat_json(
                BLIND_SOLVER_SYSTEM_PROMPT,
                build_blind_user_prompt(item),
            )
            observations["llm_blind_solver"] = blind
        except RuntimeError as exc:
            self.last_error = f"blind_solver: {exc}"
            observations["llm_blind_solver"] = {"audit_failure": str(exc)}
            return [self.failure_violation(item)]

        try:
            matcher = self.client.chat_json(
                ANSWER_OPTION_MATCHER_SYSTEM_PROMPT,
                build_option_match_user_prompt(item, blind),
            )
            observations["llm_answer_option_matcher"] = matcher
        except RuntimeError as exc:
            self.last_error = f"answer_option_matcher: {exc}"
            observations["llm_answer_option_matcher"] = {"audit_failure": str(exc)}
            return [self.failure_violation(item)]

        try:
            applicability = self.client.chat_json(
                OPTION_APPLICABILITY_SYSTEM_PROMPT,
                build_option_applicability_user_prompt(item, blind, matcher),
            )
            observations["llm_option_applicability"] = applicability
        except RuntimeError as exc:
            self.last_error = f"option_applicability: {exc}"
            observations["llm_option_applicability"] = {"audit_failure": str(exc)}
            return [self.failure_violation(item)]

        option_evidence = option_match_evidence(
            item,
            blind,
            matcher,
            applicability,
        )
        observations["llm_programmatic_answer_set"] = option_evidence
        if (
            self.mode == "cascade"
            and not option_evidence_is_risky(item, option_evidence)
        ):
            result = aggregate_gold_evidence(item, option_evidence, None, None)
            observations[self.name] = result
            return list(
                gold_violations(
                    item,
                    result,
                    self.confirm_threshold,
                    self.review_threshold,
                )
            )

        stage_payload = build_gold_evidence_user_prompt(
            item,
            blind,
            matcher,
            option_evidence,
        )
        try:
            challenger = self.client.chat_json(GOLD_CHALLENGER_SYSTEM_PROMPT, stage_payload)
            observations["llm_gold_challenger"] = challenger
        except RuntimeError as exc:
            challenger = {"audit_failure": str(exc)}
            observations["llm_gold_challenger"] = challenger
        defender = None
        if self.mode == "full" or defender_is_needed(item, option_evidence, challenger):
            try:
                defender = self.client.chat_json(GOLD_DEFENDER_SYSTEM_PROMPT, stage_payload)
                observations["llm_gold_defender"] = defender
            except RuntimeError as exc:
                defender = {"audit_failure": str(exc)}
                observations["llm_gold_defender"] = defender

        result = aggregate_gold_evidence(item, option_evidence, defender, challenger)
        observations[self.name] = result
        failed_stages = [
            name
            for name, stage in (
                ("defender", defender),
                ("challenger", challenger),
            )
            if stage is not None and "audit_failure" in stage
        ]
        if failed_stages:
            self.last_error = (
                "structured gold evidence stages failed: "
                + ", ".join(failed_stages)
            )
        violations = list(
            gold_violations(
                item,
                result,
                self.confirm_threshold,
                self.review_threshold,
            )
        )
        existing_defects = {violation.defect_type for violation in violations}
        violations.extend(
            violation
            for violation in option_applicability_violations(item, option_evidence)
            if violation.defect_type not in existing_defects
        )
        if self.last_error:
            violations.append(self.failure_violation(item))
        return violations


class QuestionClarityLLMAuditor(BaseLLMAuditor):
    name = "llm_question_clarity"
    prompt = QUESTION_SYSTEM_PROMPT

    def query(self, item: BenchmarkItem) -> dict[str, Any] | None:
        self.last_error = None
        payload = common_item_payload(item)
        payload.pop("gold", None)
        payload.pop("aliases", None)
        payload.pop("evaluator", None)
        try:
            result = self.client.chat_json(
                self.prompt,
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
            item.metadata.setdefault("_llm_observations", {})[self.name] = result
            return result
        except RuntimeError as exc:
            self.last_error = str(exc)
            item.metadata.setdefault("_llm_observations", {})[self.name] = {
                "audit_failure": str(exc)
            }
            return None

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if not item.task:
            return []
        result = self.query(item)
        if not result:
            return [self.failure_violation(item)] if self.last_error else []
        return list(question_violations(item, result, self.confirm_threshold, self.review_threshold))


class OptionSetLLMAuditor(BaseLLMAuditor):
    name = "llm_option_set"
    prompt = OPTION_SYSTEM_PROMPT

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if not item.task or not item.choices:
            return []
        result = self.query(item)
        if not result:
            return [self.failure_violation(item)] if self.last_error else []
        return list(option_violations(item, result, self.confirm_threshold, self.review_threshold))


class PresentationLLMAuditor(BaseLLMAuditor):
    name = "llm_presentation_integrity"
    prompt = PRESENTATION_SYSTEM_PROMPT

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if not item.task:
            return []
        result = self.query(item)
        if not result:
            return [self.failure_violation(item)] if self.last_error else []
        return list(
            presentation_violations(
                item,
                result,
                self.review_threshold,
            )
        )


class QuantityConsistencyLLMAuditor(BaseLLMAuditor):
    name = "llm_quantity_consistency"
    prompt = QUANTITY_CONSISTENCY_SYSTEM_PROMPT

    def query(self, item: BenchmarkItem) -> dict[str, Any] | None:
        self.last_error = None
        payload = {
            "item_id": item.item_id,
            "task": item.task,
            "context": compact_value(item.context, 4000),
            "output_contract": item.output_contract,
            "metadata_without_verified_labels": strip_verified_metadata(item.metadata),
        }
        try:
            result = self.client.chat_json(
                self.prompt,
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
            item.metadata.setdefault("_llm_observations", {})[self.name] = result
            return result
        except RuntimeError as exc:
            self.last_error = str(exc)
            item.metadata.setdefault("_llm_observations", {})[self.name] = {
                "audit_failure": str(exc)
            }
            return None

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if not item.task:
            return []
        result = self.query(item)
        if not result:
            return [self.failure_violation(item)] if self.last_error else []
        return list(
            quantity_consistency_violations(
                item,
                result,
                self.confirm_threshold,
                self.review_threshold,
            )
        )


class EventStateLLMAuditor(BaseLLMAuditor):
    name = "llm_event_state"
    prompt = EVENT_STATE_SYSTEM_PROMPT

    def query(self, item: BenchmarkItem) -> dict[str, Any] | None:
        self.last_error = None
        payload = {
            "item_id": item.item_id,
            "task": item.task,
            "context": compact_value(item.context, 4000),
            "output_contract": item.output_contract,
            "metadata_without_verified_labels": strip_verified_metadata(item.metadata),
        }
        try:
            result = self.client.chat_json(
                self.prompt,
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
            item.metadata.setdefault("_llm_observations", {})[self.name] = result
            return result
        except RuntimeError as exc:
            self.last_error = str(exc)
            item.metadata.setdefault("_llm_observations", {})[self.name] = {
                "audit_failure": str(exc)
            }
            return None

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if not item.task:
            return []
        result = self.query(item)
        if not result:
            return [self.failure_violation(item)] if self.last_error else []
        return list(
            event_state_violations(
                item,
                result,
                self.confirm_threshold,
                self.review_threshold,
            )
        )


_DIRECT_AUDIT_DEFECT_TYPES = frozenset({
    "wrong_gold_answer",
    "no_correct_answer",
    "multiple_correct_answers",
    "bad_options_clarity",
    "ambiguous_goal",
    "missing_condition",
    "missing_context",
})


class DirectLLMAuditor(BaseLLMAuditor):
    """Single-call baseline: LLM sees the full item (including gold) and judges directly."""

    name = "llm_direct_audit"
    prompt = DIRECT_AUDIT_SYSTEM_PROMPT

    def check(self, item: BenchmarkItem, root: Path | None = None) -> Iterable[Violation]:
        if not item.task:
            return []
        result = self.query(item)
        if not result:
            return [self.failure_violation(item)] if self.last_error else []
        return list(self._violations(item, result))

    def _violations(self, item: BenchmarkItem, result: dict[str, Any]) -> Iterable[Violation]:
        if not result.get("has_defect", False):
            return
        confidence = _float(result.get("confidence"), 0.0)
        needs_expert = bool(result.get("needs_expert", False))
        if confidence < self.review_threshold:
            return
        defect_types = [
            dt for dt in result.get("defect_types", [])
            if dt in _DIRECT_AUDIT_DEFECT_TYPES
        ]
        if not defect_types:
            defect_types = ["wrong_gold_answer"]
        review_only = needs_expert or confidence < self.confirm_threshold
        for defect_type in defect_types:
            yield _llm_violation(
                item,
                defect_type,
                confidence,
                result,
                review_only,
                self.name,
                f"Direct audit reported {defect_type}.",
            )


# Backward-compatible alias for callers that still request one semantic auditor.
LLMSemanticChecker = GoldLLMAuditor


def build_user_prompt(item: BenchmarkItem) -> str:
    payload = {
        "item_id": item.item_id,
        "task": item.task,
        "context": compact_value(item.context, 4000),
        "choices": item.choices,
        "gold": item.gold,
        "aliases": item.aliases,
        "output_contract": item.output_contract,
        "evaluator": item.evaluator,
        "metadata_without_verified_labels": strip_verified_metadata(item.metadata),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_blind_user_prompt(item: BenchmarkItem) -> str:
    payload = common_item_payload(item)
    payload.pop("choices", None)
    payload.pop("gold", None)
    payload.pop("aliases", None)
    payload.pop("evaluator", None)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_gold_evidence_user_prompt(
    item: BenchmarkItem,
    blind_solution: dict[str, Any],
    option_matching: dict[str, Any] | None = None,
    option_evidence: dict[str, Any] | None = None,
) -> str:
    payload = common_item_payload(item)
    payload["blind_solution"] = blind_solution
    if option_matching is not None:
        payload["answer_option_matching"] = option_matching
    if option_evidence is not None:
        payload["programmatic_answer_set"] = option_evidence
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_option_match_user_prompt(
    item: BenchmarkItem,
    blind_solution: dict[str, Any],
) -> str:
    payload = {
        "item_id": item.item_id,
        "task": item.task,
        "context": compact_value(item.context, 4000),
        "choices": item.choices,
        "blind_solution": blind_solution,
        "metadata_without_verified_labels": strip_verified_metadata(item.metadata),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_option_applicability_user_prompt(
    item: BenchmarkItem,
    blind_solution: dict[str, Any],
    option_matching: dict[str, Any],
) -> str:
    payload = {
        "item_id": item.item_id,
        "task": item.task,
        "context": compact_value(item.context, 4000),
        "choices": item.choices,
        "blind_solution": blind_solution,
        "answer_option_matching": option_matching,
        "metadata_without_verified_labels": strip_verified_metadata(item.metadata),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def common_item_payload(item: BenchmarkItem) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "task": item.task,
        "context": compact_value(item.context, 4000),
        "choices": item.choices,
        "gold": item.gold,
        "aliases": item.aliases,
        "output_contract": item.output_contract,
        "evaluator": item.evaluator,
        "metadata_without_verified_labels": strip_verified_metadata(item.metadata),
    }


def strip_verified_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    blocked = {
        "_llm_observations",
        "audit_label",
        "cleaning_status",
        "error_type",
        "gold_verified_disagree",
        "human_defect",
        "verified_gold",
        "verified_answer_text",
        "platinum_target",
        "injected_defects",
        "potential_reason",
        "source_evidence",
    }
    blocked_fragments = (
        "ground_truth",
        "human_label",
        "oracle_label",
        "verified_answer",
        "verified_gold",
    )
    return {
        key: value
        for key, value in metadata.items()
        if key.lower() not in blocked
        and not any(fragment in key.lower() for fragment in blocked_fragments)
    }


def compact_value(value: Any, max_chars: int) -> Any:
    text = json.dumps(value, ensure_ascii=False)
    if len(text) <= max_chars:
        return value
    return {
        "__benchcore_payload_truncated__": True,
        "preview": text[:max_chars],
        "original_serialized_chars": len(text),
        "note": (
            "Transport preview truncated to fit the LLM prompt. Do not treat this "
            "preview truncation as a benchmark artifact defect."
        ),
    }


def gold_violations(
    item: BenchmarkItem,
    result: dict[str, Any],
    confirm_threshold: float,
    review_threshold: float,
) -> Iterable[Violation]:
    status = str(result.get("gold_status", "uncertain"))
    defect_type = str(result.get("defect_type", "none"))
    confidence = _float(result.get("confidence"), 0.0)
    needs_expert = bool(result.get("needs_expert", False))

    notation_conflict = detects_notation_reinterpretation(item, result)
    if notation_conflict:
        yield _llm_violation(
            item,
            "no_correct_answer",
            max(confidence, 0.8),
            result,
            False,
            "llm_gold_audit+notation_consistency",
            "Gold support requires reinterpreting notation explicitly defined by the task.",
        )
        return
    if confidence < review_threshold:
        return
    if defect_type == "none" and status != "contradicted":
        return
    if defect_type not in {
        "wrong_gold_answer",
        "no_correct_answer",
        "multiple_correct_answers",
    }:
        defect_type = "wrong_gold_answer" if status == "contradicted" else "none"
    if defect_type == "none":
        return
    review_only = needs_expert or confidence < confirm_threshold
    yield _llm_violation(
        item,
        defect_type,
        confidence,
        result,
        review_only,
        "llm_gold_audit",
        f"Gold auditor reported {defect_type} with gold_status={status}.",
    )


def blind_solution_is_risky(
    item: BenchmarkItem,
    blind: dict[str, Any],
) -> bool:
    if blind.get("solution_status") != "solved":
        return True
    if bool(blind.get("needs_expert", False)):
        return True
    if _float(blind.get("confidence"), 0.0) < 0.85:
        return True
    if blind.get("assumption_risk") == "answer_changing":
        return True
    answers = normalize_answer_set(
        item,
        blind.get("valid_answers", blind.get("derived_answers", [])),
    )
    gold = normalize_answer(item, item.gold)
    return len(answers) != 1 or gold not in answers


def defender_is_needed(
    item: BenchmarkItem,
    option_evidence: dict[str, Any],
    challenger: dict[str, Any],
) -> bool:
    if "audit_failure" in challenger:
        return True
    if option_evidence_is_risky(item, option_evidence):
        return True
    if challenger.get("gold_validity") != "valid":
        return True
    if challenger.get("defect_type") not in {None, "", "none"}:
        return True
    return False


def option_match_evidence(
    item: BenchmarkItem,
    blind: dict[str, Any],
    matcher: dict[str, Any],
    applicability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matches = matcher.get("matches", [])
    equivalent = set()
    uncertain = set()
    confidences = [_float(blind.get("confidence"), 0.0)]
    for entry in matches:
        if not isinstance(entry, dict):
            continue
        label = normalize_answer(item, entry.get("label"))
        relation = entry.get("relation")
        confidence = _float(entry.get("confidence"), 0.0)
        confidences.append(confidence)
        if relation == "equivalent" and label:
            equivalent.add(label)
        elif relation == "uncertain" and label:
            uncertain.add(label)

    independently_acceptable = set()
    independently_uncertain = set()
    assessed_labels = set()
    for entry in (applicability or {}).get("option_assessments", []):
        if not isinstance(entry, dict):
            continue
        label = normalize_answer(item, entry.get("label"))
        if label:
            assessed_labels.add(label)
        status = entry.get("status")
        confidence = _float(entry.get("confidence"), 0.0)
        confidences.append(confidence)
        if confidence < 0.8 and label:
            independently_uncertain.add(label)
        elif status == "acceptable" and label:
            independently_acceptable.add(label)
        elif status == "uncertain" and label:
            independently_uncertain.add(label)

    missing_assessments = set()
    if applicability is not None and item.choices:
        expected_labels = set(CHOICE_LABELS[: len(item.choices)])
        missing_assessments = expected_labels - assessed_labels
        independently_uncertain |= missing_assessments

    # For open-ended tasks (no choices), compare derived answers to gold directly.
    # This prevents every item from triggering the challenger/defender needlessly.
    if not item.choices and not equivalent and item.gold is not None:
        gold_norm = normalize_answer(item, item.gold)
        for derived in blind.get("derived_answers", []):
            derived_norm = normalize_answer(item, derived)
            if derived_norm and derived_norm == gold_norm:
                equivalent.add(gold_norm)
                break

    accepted = equivalent | independently_acceptable
    uncertain |= independently_uncertain
    if uncertain or blind.get("solution_status") in {"ambiguous", "uncertain"}:
        status = "uncertain"
    elif not accepted:
        status = "none"
    elif len(accepted) == 1:
        status = "solved"
    else:
        status = "multiple"

    return {
        "solution_status": status,
        "valid_answers": sorted(accepted),
        "equivalent_answers": sorted(equivalent),
        "independently_acceptable_answers": sorted(independently_acceptable),
        "missing_option_assessments": sorted(missing_assessments),
        "uncertain_answers": sorted(uncertain),
        "confidence": (
            sum(confidences) / len(confidences)
            if confidences
            else 0.0
        ),
        "needs_expert": bool(blind.get("needs_expert", False))
        or bool(matcher.get("needs_expert", False))
        or bool((applicability or {}).get("needs_expert", False)),
        "assumption_risk": blind.get("assumption_risk", "none"),
        "required_assumptions": blind.get("required_assumptions", []),
        "claims": blind.get("claims", []),
        "derived_answers": blind.get(
            "derived_answers",
            blind.get("valid_answers", []),
        ),
        "option_matching": matcher,
        "option_applicability": applicability or {},
    }


def option_evidence_is_risky(
    item: BenchmarkItem,
    option_evidence: dict[str, Any],
) -> bool:
    if option_evidence.get("solution_status") != "solved":
        return True
    if option_evidence.get("uncertain_answers"):
        return True
    if bool(option_evidence.get("needs_expert", False)):
        return True
    if option_evidence.get("assumption_risk") == "answer_changing":
        return True
    answers = normalize_answer_set(item, option_evidence.get("valid_answers", []))
    gold = normalize_answer(item, item.gold)
    return len(answers) != 1 or gold not in answers


def option_applicability_violations(
    item: BenchmarkItem,
    option_evidence: dict[str, Any],
) -> Iterable[Violation]:
    # Require non-empty option assessments when the applicability payload is present.
    # An applicability result with no assessed options is an unsubstantiated judgment.
    applicability_payload = option_evidence.get("option_applicability")
    if applicability_payload is not None and not applicability_payload.get("option_assessments"):
        return

    status = option_evidence.get("solution_status")
    valid_answers = option_evidence.get("valid_answers", [])
    uncertain_answers = option_evidence.get("uncertain_answers", [])
    confidence = _float(option_evidence.get("confidence"), 0.0)
    if status == "multiple":
        yield _violation(
            item,
            "multiple_correct_answers",
            confidence,
            "Independent option checks found multiple choices that satisfy the task.",
            {"option_evidence": option_evidence},
            severity="review",
            review_only=True,
            repair=repair_for_defect("multiple_correct_answers"),
            method="llm_option_applicability",
        )
    elif status == "none":
        yield _violation(
            item,
            "no_correct_answer",
            confidence,
            "Independent option checks found no choice that satisfies the task.",
            {"option_evidence": option_evidence},
            severity="review",
            review_only=True,
            repair=repair_for_defect("no_correct_answer"),
            method="llm_option_applicability",
        )
    elif (
        status == "uncertain"
        and len(valid_answers) == 1
        and uncertain_answers
    ):
        yield _violation(
            item,
            "multiple_correct_answers_risk",
            confidence,
            "One accepted choice and additional uncertain choices may create multiple valid answers.",
            {"option_evidence": option_evidence},
            severity="review",
            review_only=True,
            repair="Independently verify the uncertain choices and clarify the acceptance criterion.",
            method="llm_option_applicability",
        )


def aggregate_gold_evidence(
    item: BenchmarkItem,
    blind: dict[str, Any],
    defender: dict[str, Any] | None,
    challenger: dict[str, Any] | None,
) -> dict[str, Any]:
    gold = normalize_answer(item, item.gold)
    blind_answers = normalize_answer_set(item, blind.get("valid_answers", []))
    blind_defect = defect_from_blind(item, blind, blind_answers, gold)
    votes: list[str] = []
    stage_confidences = []
    source_sensitive = task_requires_specific_source(item)
    expert_flags = [
        bool(blind.get("needs_expert", False)),
        evidence_requires_external_validation(blind, source_sensitive),
    ]

    if blind_defect:
        votes.append(blind_defect)
    else:
        votes.append("none")
    stage_confidences.append(_float(blind.get("confidence"), 0.0))

    if defender and "audit_failure" not in defender:
        support = defender.get("gold_support")
        if support == "supported":
            votes.append("none")
        elif support == "unsupported":
            votes.append(infer_defect_from_answers(blind_answers, gold))
        else:
            votes.append("uncertain")
        stage_confidences.append(_float(defender.get("confidence"), 0.0))
        expert_flags.append(bool(defender.get("needs_expert", False)))
        expert_flags.append(
            evidence_requires_external_validation(defender, source_sensitive)
        )

    challenger_answers: set[str] = set()
    if challenger and "audit_failure" not in challenger:
        challenger_answers = normalize_answer_set(
            item,
            challenger.get("alternative_answers", []),
        )
        challenger_defect = str(challenger.get("defect_type", "none"))
        if challenger.get("gold_validity") == "invalid" and challenger_defect == "none":
            challenger_defect = infer_defect_from_answers(challenger_answers, gold)
        if challenger.get("gold_validity") == "valid":
            challenger_defect = "none"
        if challenger_defect not in {
            "none",
            "wrong_gold_answer",
            "no_correct_answer",
            "multiple_correct_answers",
        }:
            challenger_defect = "uncertain"
        votes.append(challenger_defect)
        stage_confidences.append(_float(challenger.get("confidence"), 0.0))
        expert_flags.append(bool(challenger.get("needs_expert", False)))
        expert_flags.append(
            evidence_requires_external_validation(challenger, source_sensitive)
        )

    defect_votes = [vote for vote in votes if vote not in {"none", "uncertain"}]
    vote_counts: dict[str, int] = {}
    for vote in defect_votes:
        vote_counts[vote] = vote_counts.get(vote, 0) + 1
    chosen_defect = (
        max(vote_counts, key=lambda value: (vote_counts[value], value))
        if vote_counts
        else "none"
    )
    chosen_votes = vote_counts.get(chosen_defect, 0)
    opposing_votes = sum(1 for vote in votes if vote == "none")
    valid_stages = len(stage_confidences)
    agreement = chosen_votes / valid_stages if valid_stages else 0.0
    mean_stage_confidence = (
        sum(stage_confidences) / valid_stages
        if valid_stages
        else 0.0
    )
    confidence = agreement * mean_stage_confidence

    if chosen_defect == "none":
        status = "supported" if opposing_votes else "uncertain"
        confidence = (
            opposing_votes / valid_stages * mean_stage_confidence
            if valid_stages
            else 0.0
        )
    elif opposing_votes and chosen_votes <= opposing_votes:
        status = "uncertain"
    else:
        status = "contradicted"

    answers = sorted(blind_answers | challenger_answers)
    return {
        "gold_status": status,
        "defect_type": chosen_defect,
        "correct_answers": answers,
        "confidence": round(confidence, 6),
        "needs_expert": any(expert_flags),
        "rationale": (
            f"Programmatic evidence aggregation: votes={votes}; "
            f"agreement={chosen_votes}/{valid_stages}; "
            f"mean_stage_confidence={mean_stage_confidence:.3f}."
        ),
        "evidence_votes": votes,
        "evidence_agreement": agreement,
        "valid_evidence_stages": valid_stages,
        "blind_solution": blind,
        "defender": defender,
        "challenger": challenger,
    }


def defect_from_blind(
    item: BenchmarkItem,
    blind: dict[str, Any],
    answers: set[str],
    gold: str,
) -> str:
    status = blind.get("solution_status")
    if status == "none":
        return "no_correct_answer"
    if status == "multiple":
        return "multiple_correct_answers"
    if status == "solved" and answers and gold not in answers:
        return "wrong_gold_answer"
    return ""


def infer_defect_from_answers(answers: set[str], gold: str) -> str:
    if not answers:
        return "no_correct_answer"
    if len(answers) > 1:
        return "multiple_correct_answers"
    if gold not in answers:
        return "wrong_gold_answer"
    return "wrong_gold_answer"


def normalize_answer_set(item: BenchmarkItem, values: Any) -> set[str]:
    if not isinstance(values, list):
        values = [values]
    return {
        normalized
        for value in values
        if (normalized := normalize_answer(item, value))
    }


def normalize_answer(item: BenchmarkItem, value: Any) -> str:
    if value in (None, ""):
        return ""
    if item.choices:
        index = choice_label_to_index(value, item.choices)
        if index is not None and index < len(CHOICE_LABELS):
            return CHOICE_LABELS[index]
    return str(value).strip()


def evidence_requires_external_validation(
    stage: dict[str, Any],
    source_sensitive: bool = False,
) -> bool:
    if stage.get("assumption_risk") == "answer_changing":
        return True
    if (
        stage.get("gold_support") in {"supported", "uncertain"}
        and stage.get("assumptions_required")
    ):
        return True
    claims = [
        *stage.get("claims", []),
        *stage.get("counterclaims", []),
    ]
    if source_sensitive and any(
        isinstance(claim, dict)
        and claim.get("evidence_type") == "external_source"
        for claim in claims
    ):
        return True
    return (
        stage.get("gold_support") != "unsupported"
        and any(
            isinstance(claim, dict)
            and claim.get("evidence_type") == "assumption"
            for claim in claims
        )
    )


def task_requires_specific_source(item: BenchmarkItem) -> bool:
    task = str(item.task or "")
    if item.context:
        return True
    if re.search(
        r"\b(according to|in the (?:passage|article|report|study|case|statute|"
        r"table|figure)|the author|the excerpt|as of|current|latest|today)\b",
        task,
        re.I,
    ):
        return True
    metadata_keys = {str(key).lower() for key in item.metadata}
    return bool(
        metadata_keys
        & {
            "jurisdiction",
            "textbook",
            "source_document",
            "source_version",
            "as_of",
            "date",
        }
    )


def question_violations(
    item: BenchmarkItem,
    result: dict[str, Any],
    confirm_threshold: float,
    review_threshold: float,
) -> Iterable[Violation]:
    status = str(result.get("clarity_status", "uncertain"))
    confidence = _float(result.get("confidence"), 0.0)
    needs_expert = bool(result.get("needs_expert", False))
    mapping = {
        "answer_changing_ambiguity": "ambiguous_goal",
        "missing_condition": "missing_condition",
        "missing_context": "missing_context",
    }
    defect_type = mapping.get(status)
    if defect_type is None or confidence < review_threshold:
        return
    # Natural-language clarity judgments remain review signals unless a
    # non-LLM checker later provides independent evidence.
    review_only = True
    yield _llm_violation(
        item,
        defect_type,
        confidence,
        result,
        review_only,
        "llm_question_clarity",
        f"Question clarity auditor reported {status}.",
    )


def quantity_consistency_violations(
    item: BenchmarkItem,
    result: dict[str, Any],
    confirm_threshold: float,
    review_threshold: float,
) -> Iterable[Violation]:
    violated_checks = []
    nonmaterial_violated_checks = []
    for check in result.get("checks", []):
        if not isinstance(check, dict):
            continue
        confidence = _float(check.get("confidence"), _float(result.get("confidence"), 0.0))
        if confidence < review_threshold:
            continue
        left = _finite_float(check.get("left_value"))
        right = _finite_float(check.get("right_value"))
        relation = str(check.get("relation", "")).strip()
        if (
            left is None
            or right is None
            or relation not in {"<=", ">=", "==", "<", ">"}
            or not bool(check.get("fully_grounded", False))
        ):
            continue
        if not _numeric_relation_holds(left, relation, right):
            finding = {
                **check,
                "programmatic_result": False,
                "left_value": left,
                "right_value": right,
            }
            if bool(check.get("material_to_answer", False)):
                violated_checks.append(finding)
            else:
                nonmaterial_violated_checks.append(finding)

    if violated_checks:
        confidence = max(
            _float(check.get("confidence"), _float(result.get("confidence"), 0.0))
            for check in violated_checks
        )
        yield _llm_violation(
            item,
            "ambiguous_goal",
            confidence,
            {
                **result,
                "programmatically_violated_checks": violated_checks,
                "programmatic_violation": True,
            },
            confidence < confirm_threshold,
            "llm_quantity_consistency",
            "Programmatic validation found an impossible or contradictory quantity constraint.",
        )

    if nonmaterial_violated_checks:
        confidence = max(
            _float(check.get("confidence"), _float(result.get("confidence"), 0.0))
            for check in nonmaterial_violated_checks
        )
        yield _llm_violation(
            item,
            "ambiguous_goal",
            confidence,
            {
                **result,
                "programmatically_violated_checks": nonmaterial_violated_checks,
                "programmatic_violation": True,
                "material_to_answer": False,
            },
            True,
            "llm_quantity_consistency_nonmaterial",
            (
                "Programmatic validation found an internal quantity inconsistency "
                "that does not change the requested answer."
            ),
        )

    material_reference_issues = [
        issue
        for issue in result.get("reference_issues", [])
        if isinstance(issue, dict)
        and bool(issue.get("material_to_answer", False))
        and _float(issue.get("confidence"), 0.0) >= review_threshold
    ]
    if material_reference_issues:
        confidence = max(_float(issue.get("confidence"), 0.0) for issue in material_reference_issues)
        yield _llm_violation(
            item,
            "ambiguous_goal",
            confidence,
            {**result, "material_reference_issues": material_reference_issues},
            True,
            "llm_quantity_consistency",
            "Quantity parsing found a material entity, action, or time-scope mismatch.",
        )

    nonmaterial_reference_issues = [
        issue
        for issue in result.get("reference_issues", [])
        if isinstance(issue, dict)
        and not bool(issue.get("material_to_answer", False))
        and _float(issue.get("confidence"), 0.0) >= review_threshold
    ]
    if nonmaterial_reference_issues:
        confidence = max(
            _float(issue.get("confidence"), 0.0)
            for issue in nonmaterial_reference_issues
        )
        yield _llm_violation(
            item,
            "ambiguous_goal",
            confidence,
            {
                **result,
                "nonmaterial_reference_issues": nonmaterial_reference_issues,
                "material_to_answer": False,
            },
            True,
            "llm_quantity_consistency_nonmaterial",
            (
                "Quantity parsing found an internal entity or semantic-role "
                "inconsistency that does not change the requested answer."
            ),
        )

    derived = [parse_number(answer) for answer in result.get("derived_answers", [])]
    derived = [answer for answer in derived if answer is not None]
    gold = parse_number(item.gold)
    confidence = _float(result.get("confidence"), 0.0)
    unique_derived = sorted(set(derived))
    if (
        str(result.get("solution_status", "uncertain")) == "solved"
        and len(unique_derived) == 1
        and gold is not None
        and abs(unique_derived[0] - gold) > 1e-9
        and confidence >= review_threshold
    ):
        yield _llm_violation(
            item,
            "wrong_gold_answer",
            confidence,
            {
                **result,
                "programmatic_gold_comparison": {
                    "derived": unique_derived[0],
                    "gold": gold,
                    "equal": False,
                },
            },
            True,
            "llm_quantity_consistency",
            "Independently parsed numeric answer disagrees with the declared gold.",
        )


def event_state_violations(
    item: BenchmarkItem,
    result: dict[str, Any],
    confirm_threshold: float,
    review_threshold: float,
) -> Iterable[Violation]:
    material_findings: list[dict[str, Any]] = []
    nonmaterial_findings: list[dict[str, Any]] = []

    for model in result.get("state_models", []):
        if not isinstance(model, dict):
            continue
        confidence = _float(model.get("confidence"), _float(result.get("confidence"), 0.0))
        if confidence < review_threshold:
            continue
        findings = _validate_state_model(model)
        target = material_findings if bool(model.get("material_to_answer", False)) else nonmaterial_findings
        target.extend({**finding, "entity": model.get("entity")} for finding in findings)

    for conflict in result.get("role_conflicts", []):
        if not isinstance(conflict, dict):
            continue
        confidence = _float(conflict.get("confidence"), _float(result.get("confidence"), 0.0))
        if (
            confidence < review_threshold
            or bool(conflict.get("same_quantity_justified", True))
        ):
            continue
        finding = {
            "finding_type": "semantic_role_conflict",
            "stated_role": conflict.get("stated_role"),
            "queried_role": conflict.get("queried_role"),
            "evidence": conflict.get("evidence"),
            "confidence": confidence,
        }
        if bool(conflict.get("material_to_answer", False)):
            material_findings.append(finding)
        else:
            nonmaterial_findings.append(finding)

    if material_findings:
        confidence = max(
            _float(finding.get("confidence"), _float(result.get("confidence"), 0.0))
            for finding in material_findings
        )
        yield _llm_violation(
            item,
            "ambiguous_goal",
            confidence,
            {
                **result,
                "programmatic_event_state_findings": material_findings,
                "material_to_answer": True,
            },
            confidence < confirm_threshold,
            "llm_event_state",
            "Programmatic event-state validation found an answer-relevant inconsistency.",
        )

    if nonmaterial_findings:
        confidence = max(
            _float(finding.get("confidence"), _float(result.get("confidence"), 0.0))
            for finding in nonmaterial_findings
        )
        yield _llm_violation(
            item,
            "ambiguous_goal",
            confidence,
            {
                **result,
                "programmatic_event_state_findings": nonmaterial_findings,
                "material_to_answer": False,
            },
            True,
            "llm_event_state_nonmaterial",
            (
                "Programmatic event-state validation found an internal inconsistency "
                "that does not change the requested answer."
            ),
        )


def _validate_state_model(model: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    confidence = _float(model.get("confidence"), 0.0)
    initial = _finite_float(model.get("initial_value"))
    stated_final = _finite_float(model.get("stated_final_value"))
    required_limit = _finite_float(model.get("required_limit"))
    events = sorted(
        (event for event in model.get("events", []) if isinstance(event, dict)),
        key=lambda event: _float(event.get("stage"), 0.0),
    )

    current = initial
    net_delta = 0.0
    has_set = False
    has_unknown_delta = False
    for event in events:
        operation = str(event.get("operation", "")).lower()
        amount = _finite_float(event.get("amount"))
        if amount is None:
            if operation in {"add", "remove"}:
                has_unknown_delta = True
                current = None
            continue
        if amount < 0:
            continue
        if operation == "add":
            net_delta += amount
            if current is not None:
                current += amount
        elif operation == "remove":
            net_delta -= amount
            if current is not None:
                if amount > current + 1e-9:
                    findings.append(
                        {
                            "finding_type": "removal_exceeds_available",
                            "available": current,
                            "removed": amount,
                            "evidence": event.get("evidence"),
                            "confidence": confidence,
                        }
                    )
                current -= amount
        elif operation == "set":
            has_set = True
            evidence = str(event.get("evidence", ""))
            implicit_unknown_event = bool(
                re.search(
                    r"\bafter\b.*\b(some|several|an unknown number|an unknown amount)\b",
                    evidence,
                    re.I,
                )
            )
            if implicit_unknown_event:
                has_unknown_delta = True
            if current is not None and not has_unknown_delta and abs(current - amount) > 1e-9:
                findings.append(
                    {
                        "finding_type": "state_transition_mismatch",
                        "computed": current,
                        "stated": amount,
                        "evidence": event.get("evidence"),
                        "confidence": confidence,
                    }
                )
            current = amount

    if initial is None and stated_final is not None and not has_set and not has_unknown_delta:
        inferred_initial = stated_final - net_delta
        if inferred_initial < -1e-9:
            findings.append(
                {
                    "finding_type": "negative_inferred_initial_state",
                    "inferred_initial": inferred_initial,
                    "stated_final": stated_final,
                    "net_delta": net_delta,
                    "confidence": confidence,
                }
            )

    if initial is not None and stated_final is not None and not has_set and not has_unknown_delta:
        computed_final = initial + net_delta
        if abs(computed_final - stated_final) > 1e-9:
            findings.append(
                {
                    "finding_type": "final_state_mismatch",
                    "computed_final": computed_final,
                    "stated_final": stated_final,
                    "confidence": confidence,
                }
            )

    effective_final = stated_final if stated_final is not None else current
    if (
        required_limit is not None
        and effective_final is not None
        and effective_final > required_limit + 1e-9
    ):
        findings.append(
            {
                "finding_type": "state_exceeds_required_limit",
                "state_value": effective_final,
                "required_limit": required_limit,
                "confidence": confidence,
            }
        )
    return findings


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _numeric_relation_holds(left: float, relation: str, right: float) -> bool:
    if relation == "<=":
        return left <= right + 1e-9
    if relation == ">=":
        return left + 1e-9 >= right
    if relation == "==":
        return abs(left - right) <= 1e-9
    if relation == "<":
        return left < right and abs(left - right) > 1e-9
    return left > right and abs(left - right) > 1e-9


def option_violations(
    item: BenchmarkItem,
    result: dict[str, Any],
    confirm_threshold: float,
    review_threshold: float,
) -> Iterable[Violation]:
    defect_type = str(result.get("defect_type", "none"))
    literal_cardinality = str(
        result.get("literal_cardinality", result.get("cardinality", "uncertain"))
    )
    best_cardinality = str(
        result.get("best_answer_cardinality", result.get("cardinality", "uncertain"))
    )
    confidence = _float(result.get("confidence"), 0.0)
    needs_expert = bool(result.get("needs_expert", False))
    if confidence < review_threshold:
        return
    if defect_type == "none":
        if best_cardinality == "multiple":
            defect_type = "multiple_correct_answers"
        elif best_cardinality == "none":
            defect_type = "no_correct_answer"
        elif has_option_clarity_issue(result):
            defect_type = "bad_options_clarity"
    if defect_type not in {
        "multiple_correct_answers",
        "no_correct_answer",
        "bad_options_clarity",
    }:
        return
    review_only = needs_expert or confidence < confirm_threshold or defect_type == "bad_options_clarity"
    yield _llm_violation(
        item,
        defect_type,
        confidence,
        result,
        review_only,
        "llm_option_set",
        (
            f"Option set auditor reported {defect_type} with "
            f"literal_cardinality={literal_cardinality}, "
            f"best_answer_cardinality={best_cardinality}."
        ),
    )


def has_option_clarity_issue(result: dict[str, Any]) -> bool:
    for option in result.get("option_statuses", []):
        if not isinstance(option, dict):
            continue
        if option.get("clarity") in {"unclear", "corrupted"}:
            return True
        if option.get("literal_truth") == "invalid" or option.get("status") == "invalid":
            return True
    return False


def presentation_violations(
    item: BenchmarkItem,
    result: dict[str, Any],
    review_threshold: float,
) -> Iterable[Violation]:
    artifact_map = {
        "task_specification": "task_specification",
        "context_attachment": "context_attachment",
        "choices": "expected_output",
        "oracle_ground_truth": "oracle_ground_truth",
        "expected_output": "expected_output",
        "evaluator": "evaluator",
    }
    for issue in result.get("issues", []):
        if not isinstance(issue, dict):
            continue
        confidence = _float(
            issue.get("confidence"),
            _float(result.get("confidence"), 0.0),
        )
        if confidence < review_threshold:
            continue
        raw_text = str(issue.get("raw_text", "")).strip()
        interpreted_text = str(issue.get("interpreted_text", "")).strip()
        if not raw_text or not interpreted_text or raw_text == interpreted_text:
            continue
        if _is_transport_truncation_issue(item, issue):
            continue
        artifact = artifact_map.get(
            str(issue.get("artifact", "")),
            "expected_output",
        )
        yield _violation(
            item,
            "presentation_corruption",
            confidence,
            (
                "Understanding the artifact requires an implicit formatting or "
                "OCR repair."
            ),
            {
                "presentation_issue": issue,
                "llm_result": result,
            },
            severity="review",
            review_only=True,
            repair=(
                "Restore the original notation, encoding, segmentation, or "
                "formatting without relying on reader reconstruction."
            ),
            method="llm_presentation_integrity",
            scope="presentation",
            artifact=artifact,
        )


def _is_transport_truncation_issue(item: BenchmarkItem, issue: dict[str, Any]) -> bool:
    issue_type = str(issue.get("issue_type", "")).lower()
    raw_text = str(issue.get("raw_text", ""))
    rationale = str(issue.get("rationale", ""))
    combined = f"{raw_text}\n{rationale}".lower()
    if "truncation" not in issue_type and "truncated" not in combined:
        return False
    source_text = json.dumps(
        {
            "task": item.task,
            "context": item.context,
            "choices": item.choices,
            "gold": item.gold,
            "aliases": item.aliases,
            "output_contract": item.output_contract,
            "evaluator": item.evaluator,
        },
        ensure_ascii=False,
        default=str,
    ).lower()
    if any(marker in source_text for marker in ("[truncated]", "...[truncated]", "__benchcore_payload_truncated__")):
        return False
    return (
        "__benchcore_payload_truncated__" in combined
        or "...[truncated]" in combined
        or "full table" in combined
        or "preview" in combined
    )


def _llm_violation(
    item: BenchmarkItem,
    defect_type: str,
    confidence: float,
    result: dict[str, Any],
    review_only: bool,
    method: str,
    message: str,
) -> Violation:
    severity = "review" if review_only else severity_for_defect(defect_type)
    return _violation(
        item,
        defect_type,
        confidence,
        message,
        {"llm_result": result, "gold": item.gold, "choices": item.choices},
        severity=severity,
        review_only=review_only,
        repair=repair_for_defect(defect_type),
        method=method,
    )


def severity_for_defect(defect_type: str) -> str:
    if defect_type == "wrong_gold_answer":
        return "critical"
    if defect_type in {
        "multiple_correct_answers",
        "no_correct_answer",
        "ambiguous_goal",
        "missing_condition",
        "missing_context",
    }:
        return "major"
    return "review"


def repair_for_defect(defect_type: str) -> str:
    repairs = {
        "wrong_gold_answer": "Review and correct the gold answer or reference solution.",
        "multiple_correct_answers": "Broaden accepted alternatives or rewrite the item to have a unique correct answer.",
        "no_correct_answer": "Add a correct answer, revise choices, or remove the item.",
        "ambiguous_goal": "Clarify the task goal and answer-changing assumptions.",
        "missing_condition": "Add the missing condition or source convention required to determine the answer.",
        "missing_context": "Attach the missing context or remove context-dependent wording.",
        "duplicate_choices": "Rewrite unclear, overlapping, or uninterpretable answer choices.",
        "bad_options_clarity": "Rewrite unclear, overlapping, or uninterpretable answer choices.",
    }
    return repairs.get(defect_type, "Review and repair the benchmark artifact at fault.")


def _float(value: Any, default: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, out))


def detects_notation_reinterpretation(
    item: BenchmarkItem,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    task = str(item.task or "")
    rationale = str(result.get("rationale", ""))
    if not rationale:
        return None
    defined_symbols = []
    for symbol in ("*", "⊕", "⊗", "∘", "#", "@"):
        escaped = re.escape(symbol)
        if re.search(rf"\b\w+\s*{escaped}\s*\w+\s*(?:=|:=)", task):
            defined_symbols.append(symbol)
    if not defined_symbols:
        return None
    reinterpretation = re.search(
        r"\b(ordinary|usual|standard|normal)\s+(multiplication|meaning|interpretation|operator)\b",
        rationale,
        re.I,
    )
    if not reinterpretation:
        return None
    return {
        "defined_symbols": defined_symbols,
        "rationale_phrase": reinterpretation.group(0),
    }
