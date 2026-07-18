# Benchmark Audit Report

- Input: `experiments/mmlu_redux_pilot1000.jsonl`
- Items: `1000`
- Violations: `711`
- Confirmed: `0`
- Review signals: `384`
- Unknown-tier findings: `327`
- Affected items: `398`
- Operationally affected items: `135`
- Methods run: `task_specification, context_attachment, expected_output, oracle_ground_truth, evaluator, task_integrity, contract_consistency, evaluator_replay, metamorphic_answer, evaluator_mutation, executable_evidence, differential_candidate, llm_gold_audit, llm_question_clarity, llm_option_set, duplicate_conflict, schema_drift`
- Planned item×checker checks: `17123`
- Eligible checks: `12668`
- Completed checks: `15106`
- Coverage unknown: `2459`
- Operational failures: `17`
- Elapsed seconds: `4819.882`
- Git commit: `2b3ce354683132ef03eafe684fc79600200f8c9b dirty`
- LLM: `deepseek-v4-flash` (API attempts=5917, cache hits=58)

## Audit Coverage

- Detected family: `generic` (confidence=0.35)
- Executed checks: `12`
- Partially executed checks: `3`
- Failed checks: `0`
- Ineligible checks: `2`
- Selected checks not run: `2`
- Skipped checks: `6`
- Unsupported checks: `2`
- `context_attachment`: `missing`
- `environment_initial_state`: `missing`
- `evaluator_tests_rubric`: `present`
- `expected_output`: `missing`
- `interaction_protocol`: `missing`
- `oracle_ground_truth`: `present`
- `provenance_versioning`: `present`
- `task_specification`: `present`
- `tool_action_space`: `missing`
- `trace_evidence`: `missing`
- Unknown: no family-specific signature detected

## Item × Checker Coverage Ledger

`completed_no_finding` means only that a checker returned normally without emitting a finding. It is not a clean-benchmark verdict.

- Planned: `17123`
- Explicitly eligible: `12668`
- Eligibility unknown: `2455`
- Attempted: `15123`
- Completed: `15106`
- Completed without finding: `14417`
- Finding: `689`
- Unknown/incomplete: `2459`
- Operational failures: `17`
- Security blocked: `0`
- Unsupported: `0`
- Abstained: `0`
- Ineligible: `2000`

### Coverage gaps

- `mmlu-redux-jurisprudence-67` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-jurisprudence-67` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-jurisprudence-67` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-college_physics-16` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-college_physics-16` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-college_physics-16` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-abstract_algebra-52` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-abstract_algebra-52` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-abstract_algebra-52` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_european_history-58` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_european_history-58` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_european_history-58` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-clinical_knowledge-85` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-professional_psychology-71` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-professional_psychology-71` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-professional_psychology-71` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-conceptual_physics-69` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-conceptual_physics-69` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-conceptual_physics-69` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-abstract_algebra-89` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-abstract_algebra-89` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-abstract_algebra-89` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-virology-85` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-us_foreign_policy-34` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-us_foreign_policy-34` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-us_foreign_policy-34` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-international_law-16` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-international_law-16` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-elementary_mathematics-57` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-elementary_mathematics-57` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-elementary_mathematics-57` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-computer_security-0` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-computer_security-0` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-computer_security-0` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-formal_logic-64` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-formal_logic-64` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-formal_logic-64` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-professional_psychology-72` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-professional_psychology-72` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-professional_psychology-72` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-public_relations-84` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-public_relations-84` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-public_relations-84` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-computer_security-23` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-computer_security-23` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-college_chemistry-88` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-college_chemistry-88` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-virology-22` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-virology-22` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-virology-22` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-virology-37` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-prehistory-38` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-prehistory-38` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-prehistory-38` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_us_history-15` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_us_history-15` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_us_history-15` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-virology-81` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-virology-81` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_biology-53` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_biology-53` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_biology-53` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-college_chemistry-55` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-college_chemistry-55` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-college_chemistry-55` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_government_and_politics-6` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_government_and_politics-6` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_government_and_politics-6` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-formal_logic-76` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-formal_logic-76` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-formal_logic-76` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-philosophy-81` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-philosophy-81` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-philosophy-81` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-virology-96` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-virology-96` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-professional_law-71` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-professional_law-71` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-professional_law-71` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_computer_science-64` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_computer_science-64` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_computer_science-64` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_computer_science-22` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_computer_science-22` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_computer_science-22` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_psychology-34` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_psychology-34` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_psychology-34` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-logical_fallacies-66` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-logical_fallacies-66` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-logical_fallacies-66` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_macroeconomics-8` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_macroeconomics-8` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-high_school_macroeconomics-8` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-world_religions-0` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-world_religions-0` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-world_religions-0` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-miscellaneous-6` × `llm_gold_audit`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-miscellaneous-6` × `llm_question_clarity`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- `mmlu-redux-miscellaneous-6` × `llm_option_set`: `completed_no_finding` — checker completed without emitting a finding; this is not evidence that the item is clean; checker applicability was not declared
- … 2359 additional gap(s); see JSON ledger.

## Artifact Distribution

- `context_attachment`: 100
- `evaluator`: 140
- `expected_output`: 87
- `oracle_ground_truth`: 321
- `task_specification`: 63

## Defect Distribution

- `ambiguous_goal`: 43
- `auditor_contradiction`: 123
- `bad_options_clarity`: 83
- `duplicate_choices`: 3
- `incomplete_task_instruction`: 1
- `llm_audit_failure`: 17
- `missing_condition`: 18
- `missing_context`: 91
- `multiple_correct_answers`: 69
- `no_correct_answer`: 148
- `presentation_corruption`: 4
- `source_reference_missing`: 9
- `temporal_scope_missing`: 1
- `wrong_gold_answer`: 101

## Detection Method Distribution

- `llm_evidence_fusion`: 123
- `llm_gold_audit`: 197
- `llm_option_applicability`: 36
- `llm_option_set`: 183
- `llm_question_clarity`: 147
- `static_rule`: 10
- `task_integrity_rule`: 15

## Defect Scope Distribution

- `operational`: 140
- `presentation`: 4
- `substantive`: 567

## Field Mapping

- `item_id`: `id`
- `task`: `question`
- `context`: `[]`
- `choices`: `choices`
- `gold`: `gold`
- `aliases`: `None`
- `output_contract`: `None`
- `evaluator`: `evaluator`
- `metadata`: `['metadata', 'task_type', 'metadata.subject', 'metadata.source', 'metadata.error_type', 'metadata.verified_gold', 'metadata.verified_answer_text']`
- `diagnostics`: `{'source': 'inferred', 'rows_profiled': 1000, 'fields': {'item_id': {'selected': 'id', 'coverage': 1.0, 'type_coverage': 1.0, 'status': 'complete', 'conflicting_candidates': [], 'candidates': [{'candidate': 'id', 'selected_actual': 'id', 'present': 1000, 'coverage': 1.0, 'type_compatible': 1000, 'type_coverage': 1.0}]}, 'task': {'selected': 'question', 'coverage': 1.0, 'type_coverage': 1.0, 'status': 'complete', 'conflicting_candidates': [], 'candidates': [{'candidate': 'question', 'selected_actual': 'question', 'present': 1000, 'coverage': 1.0, 'type_compatible': 1000, 'type_coverage': 1.0}]}, 'choices': {'selected': 'choices', 'coverage': 1.0, 'type_coverage': 1.0, 'status': 'complete', 'conflicting_candidates': [], 'candidates': [{'candidate': 'choices', 'selected_actual': 'choices', 'present': 1000, 'coverage': 1.0, 'type_compatible': 1000, 'type_coverage': 1.0}]}, 'gold': {'selected': 'gold', 'coverage': 1.0, 'type_coverage': 1.0, 'status': 'complete', 'conflicting_candidates': [], 'candidates': [{'candidate': 'gold', 'selected_actual': 'gold', 'present': 1000, 'coverage': 1.0, 'type_compatible': 1000, 'type_coverage': 1.0}]}, 'aliases': {'selected': None, 'coverage': 0.0, 'type_coverage': 0.0, 'status': 'unmapped', 'candidates': []}, 'output_contract': {'selected': None, 'coverage': 0.0, 'type_coverage': 0.0, 'status': 'unmapped', 'candidates': []}, 'evaluator': {'selected': 'evaluator', 'coverage': 1.0, 'type_coverage': 1.0, 'status': 'complete', 'conflicting_candidates': [], 'candidates': [{'candidate': 'evaluator', 'selected_actual': 'evaluator', 'present': 1000, 'coverage': 1.0, 'type_compatible': 1000, 'type_coverage': 1.0}]}}}`

## Cases

### `mmlu-redux-clinical_knowledge-85` (row_uid=`source-row-00000004`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.56)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["A", "D"], "confidence": 0.561728, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.843.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solut...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.60)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.7, "rationale": "Some elderly may have visual impairments, but not universal."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.8, "rationale": "Statistic may be outdated or context-dependent, yet intended as key barrier."}, {"la...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Because older adults may have lower digital literacy, limited internet access, and are more vulnerable to misinformation, so internet-based information should be carefully evaluated for reliability and accessibility."], "confid...`

### `mmlu-redux-virology-85` (row_uid=`source-row-00000008`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The four special characteristics of MERS are not provided, so it's impossible to determine which is the exception."], "alternative_interpretations": [{"interpretation": "Each choice could be the exception depending on the unknown list of four characteristics.", "answer": "Any of the four choices could be correct."}], "rationale": "The task asks for the e...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=multiple, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "MERS is not spread by faecal-oral route; it is transmitted via droplets, reservoir in bats, and camels as intermediate."}, {"label": "B", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Aerosol droplet transmission is a know...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": true, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The question requires knowledge of MERS characteristics and the provided choices.", "evidence_type": "task_text", "support": "Task asks for e...`

### `mmlu-redux-international_law-16` (row_uid=`source-row-00000010`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.56)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.562963, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.844.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Collective security is a system in which states agree to take collective action, including military force, to respond to aggression against any member, based on the principle that an attack on one is an attack on all, often ins...`

### `mmlu-redux-computer_security-23` (row_uid=`source-row-00000016`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["the content of the paper 'Click Trajectories: End-to-End Analysis of the Spam Value Chain'"], "alternative_interpretations": [], "rationale": "The task requires knowledge of the specific paper's findings, which are not provided in the task statement. Without the paper content, the answer cannot be determined."}, "gold": "D", "choices": ["Spammers run the...`

### `mmlu-redux-college_chemistry-88` (row_uid=`source-row-00000017`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.995185, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.995.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-virology-37` (row_uid=`source-row-00000019`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.62716, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.941.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "vali...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.70)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.8, "rationale": "A is the leading infectious cause of death globally; but the question may be ambiguous regarding non-communicable diseases."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Diarrheal diseases are not th...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": ["ischemic heart disease (cardiovascular diseases) if considering all causes; if considering infectious diseases, lower respiratory infections; if considering viral causes, may be COVID-19 or HIV/AIDS"], "confidence": 0.6, "needs_expert": false, "assumption_risk"...`

### `mmlu-redux-virology-81` (row_uid=`source-row-00000022`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["A", "C"], "confidence": 0.644444, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'multiple_correct_answers', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.967.", "evidence_votes": ["multiple_correct_answers", "multiple_correct_answers", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_eviden...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says multiple_correct_answers but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Papillomaviruses cause cancer primarily through the expression of viral oncoproteins E6 and E7, which inactivate the tumor suppressor proteins p53 and Rb, respectively. This leads to dysregulation of cell cycle control, inhibition of apoptosis, and accumula...`

### `mmlu-redux-virology-96` (row_uid=`source-row-00000028`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": ["C"], "confidence": 0.632099, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.948.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"soluti...`

### `mmlu-redux-world_religions-0` (row_uid=`source-row-00000035`)

- `temporal_scope_missing` / `task_specification` / `task_integrity_rule` / `review` / review (confidence=0.82)
  - Time-sensitive wording lacks an explicit reference date or version.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Add an explicit as-of date or replace relative time wording with a stable reference.
  - Evidence: `{"matched_phrase": "current Dalai Lama", "task_excerpt": "When was the current Dalai Lama born?"}`

### `mmlu-redux-college_chemistry-92` (row_uid=`source-row-00000038`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "Garbled notation, not a valid magnetic moment value."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Value 0.717e-26 J/T does not match the known magnetic moment of 205Tl."}, {"label": "C", "l...`

### `mmlu-redux-professional_psychology-20` (row_uid=`source-row-00000039`)

- `source_reference_missing` / `context_attachment` / `task_integrity_rule` / `review` / unknown (confidence=0.80)
  - The task depends on an unnamed study/report and provides no source context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Identify the study/report, publication date, or source artifact.
  - Evidence: `{"matched_phrase": "the research", "task_excerpt": "There are specific research designs and strategies used to gain the desired information. From your knowledge about the research designs and strategies, how does the CORRELATIONAL RESEARCH work?"}`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.93)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9333333333333333, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Correlational research measures association without manipulation.", "evidence_type": "definition", "support": "Standard definition from research methodology in psychology."...`

### `mmlu-redux-college_chemistry-95` (row_uid=`source-row-00000040`)

- `llm_audit_failure` / `evaluator` / `llm_gold_audit` / `review` / unknown (confidence=1.00)
  - llm_gold_audit failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_gold_audit", "error": "blind_solver: LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 1159, 'reasoning_chars': 16886}"}`

### `mmlu-redux-human_sexuality-9` (row_uid=`source-row-00000046`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.70)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.7, "needs_expert": true, "assumptions_used": [], "missing_information": ["The specific theoretical framework or author for the dimensions of intimacy is not specified."], "alternative_interpretations": [{"interpretation": "The three dimensions are affective, cognitive, and physical (common in psychological intimacy research).", "answer": "affective, cognitive, and physical"}, {"interpretation": "The three dimensions a...`

### `mmlu-redux-high_school_statistics-81` (row_uid=`source-row-00000047`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.99)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.99, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.990.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solve...`

### `mmlu-redux-global_facts-8` (row_uid=`source-row-00000049`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.98)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.981481, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.981.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none"...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.95)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Too low; actual is about 38 million."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Too low; actual is about 38 million."}, {"label": "C", "literal_truth": "false", "best_answer_status": "best", "clarit...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["approximately 38 million"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "As of 20...`

### `mmlu-redux-prehistory-72` (row_uid=`source-row-00000051`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.95)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9500000000000001, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Anatomically modern Homo sapiens first appear in the fossil record around 300,000 years ago.", "evidence_type": "external_source", "support": "Fossils from Jebel Irhoud, Mo...`

### `mmlu-redux-business_ethics-0` (row_uid=`source-row-00000052`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.54)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.537037, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.806.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "va...`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The numbered statements or options (1,2,3,4) that the task refers to are not provided."], "alternative_interpretations": [], "rationale": "The task is a statement about the Anglo-American model but the choices are numeric lists. Without the referenced items, the answer cannot be determined. Missing context makes the task unsolvable."}, "gold": "A", "choi...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.95)
  - Option set auditor reported bad_options_clarity with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 0.0, "rationale": "Choice is a set of numbers without any statements to refer to."}, {"label": "B", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 0.0, "rationale": "Choice is a set of numbers without any statements to refer to."}, {"label": "C...`

### `mmlu-redux-jurisprudence-51` (row_uid=`source-row-00000053`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Not the standard radical feminist criticism."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Radical feminists argue liberal feminism seeks equality with men, thus making women into men."}, {"label": "C...`

### `mmlu-redux-machine_learning-65` (row_uid=`source-row-00000058`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "corrupted", "equivalence_group": null, "confidence": 0.9, "rationale": "Name misspelled (Frietas vs Freitas), but clearly refers to Nando de Freitas, who is less associated with existential risks than Russell."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Yann LeCu...`

### `mmlu-redux-nutrition-62` (row_uid=`source-row-00000059`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["A", "B"], "confidence": 0.630864, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.946.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solu...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Serum ferritin and transferrin receptors are more reliable because they reflect iron stores and cellular iron demand, respectively, providing earlier and more specific detection of iron deficiency than hemoglobin, which is a la...`

### `mmlu-redux-high_school_computer_science-3` (row_uid=`source-row-00000060`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["Description of the upgraded system and its design features"], "alternative_interpretations": [], "rationale": "The task asks for the most likely data privacy concern of an 'upgraded system' but provides no context about the system's design, functionality, or the nature of the upgrade. Without this information, the intended answer cannot be determined."},...`

### `mmlu-redux-public_relations-40` (row_uid=`source-row-00000061`)

- `source_reference_missing` / `context_attachment` / `task_integrity_rule` / `review` / unknown (confidence=0.80)
  - The task depends on an unnamed study/report and provides no source context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Identify the study/report, publication date, or source artifact.
  - Evidence: `{"matched_phrase": "recent research", "task_excerpt": "In recent research, the 14,000 stories that could be accessed on Google News' front page in a day pertained to how many actual news events?"}`

### `mmlu-redux-virology-95` (row_uid=`source-row-00000064`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.70)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.698148, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.698.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "so...`

### `mmlu-redux-conceptual_physics-96` (row_uid=`source-row-00000065`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The task statement is incomplete; it ends with 'According to general relativity,' and does not specify what is being asked about the concept."], "alternative_interpretations": [{"interpretation": "Assuming the question is 'Which of the following is true according to general relativity?'", "answer": "All of these"}, {"interpretation": "Assuming the quest...`

### `mmlu-redux-virology-33` (row_uid=`source-row-00000066`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.96)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.957407, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.957.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.70)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.7, "needs_expert": true, "assumptions_used": ["The statistics describe the scheduled test scores (144 students) and the three students are excluded", "The term 'least biased estimator' refers to robustness to outliers due to different form"], "missing_information": ["Whether the three students are included in the given statistics", "The scores of the three students on the different form", "The target population for es...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['B'] conflicts with option best_answers=['A']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["median"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": [], "claims": [{"claim": "The median is a ro...`

### `mmlu-redux-abstract_algebra-1` (row_uid=`source-row-00000069`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-college_chemistry-77` (row_uid=`source-row-00000070`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.99)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.992222, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer']; agreement=2/2; mean_stage_confidence=0.992.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 2, "blind_solution": {"solution_status": "solved", "valid_answers": ["C"], "equivalen...`
- `llm_audit_failure` / `evaluator` / `llm_gold_audit` / `review` / unknown (confidence=1.00)
  - llm_gold_audit failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_gold_audit", "error": "structured gold evidence stages failed: defender"}`
- `llm_audit_failure` / `evaluator` / `llm_question_clarity` / `review` / unknown (confidence=1.00)
  - llm_question_clarity failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_question_clarity", "error": "LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 0, 'reasoning_chars': 19435}"}`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=multiple, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Correct formula but not a numeric answer."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Incorrect time."}, {"label": "C", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "...`

### `mmlu-redux-professional_psychology-0` (row_uid=`source-row-00000071`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.95)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.95, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.950.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "v...`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": true, "assumptions_used": ["The research area is standard clinical psychology"], "missing_information": ["Which specific research area the question refers to"], "alternative_interpretations": [{"interpretation": "General population risk of schizophrenia", "answer": "0.01"}, {"interpretation": "Lifetime risk for sibling of schizophrenic patient (commonly ~10%)", "answer": "None of the given choices match"}, {"...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.95)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "General population risk (1%) but sibling risk is ~10%."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Sibling risk for schizophrenia is about 10%, not 42%."}, {"label": "C", "literal_truth": "...`

### `mmlu-redux-econometrics-41` (row_uid=`source-row-00000072`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.65)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.648148, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.648.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none"...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.90)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "ii true, iv false, so combination false"}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "i true, iii false, so combination false"}, {"label": "C", "literal_truth": "false", "best_answer_status":...`

### `mmlu-redux-moral_scenarios-90` (row_uid=`source-row-00000073`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.57)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.57037, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.856.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "v...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.70)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "S1 proposal is not wrong, so 'Wrong, Wrong' is false."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "S1 is not wrong, and S2 is likely wrong per gold, so 'Wrong, Not wrong' false."}, {"label": "...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['C']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": ["It is ambiguous whether either scenario is clearly morally wrong; Scenario 1 is not wrong, Scenario 2 is debatable."], "confidence": 0.0, "needs_expert":...`

### `mmlu-redux-college_medicine-11` (row_uid=`source-row-00000078`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.58)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.577778, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'uncertain', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.867.", "evidence_votes": ["no_correct_answer", "uncertain", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none",...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": false, "assumptions_used": ["Aufbau principle without relativistic effects"], "missing_information": ["The question does not specify whether to use the predicted or actual ground state electron configuration of gold."], "alternative_interpretations": [{"interpretation": "Using predicted Aufbau configuration (5d9 6s2) yields 29 d electrons (3d10 + 4d10 + 5d9).", "answer": "29"}, {"interpretation": "U...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.95)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "9 is not the number of d electrons in gold."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "23 is not the number of d electrons in gold."}, {"label": "C", "literal_truth": "false", "best_answer...`

### `mmlu-redux-public_relations-80` (row_uid=`source-row-00000079`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.85)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.85, "needs_expert": false, "assumptions_used": [], "missing_information": ["identity of the 2008 survey", "definition of 'world's largest companies'"], "alternative_interpretations": [{"interpretation": "Different surveys (e.g., KPMG, UN Global Compact) report different percentages", "answer": "varies"}, {"interpretation": "If referring to a specific survey not named, answer may be one of the choices", "answer": "unknown"}], "r...`

### `mmlu-redux-high_school_chemistry-92` (row_uid=`source-row-00000080`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.633333, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.950.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "va...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['B'] conflicts with option best_answers=['C']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Sulfuric acid (H2SO4) has more oxygen atoms than sulfurous acid (H2SO3), which stabilizes its conjugate base through resonance and inductive electron withdr...`

### `mmlu-redux-prehistory-61` (row_uid=`source-row-00000081`)

- `source_reference_missing` / `context_attachment` / `task_integrity_rule` / `review` / unknown (confidence=0.80)
  - The task depends on an unnamed study/report and provides no source context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Identify the study/report, publication date, or source artifact.
  - Evidence: `{"matched_phrase": "the study", "task_excerpt": "Palynology is the study of _________, which allows scientists to reconstruct ______."}`

### `mmlu-redux-logical_fallacies-41` (row_uid=`source-row-00000084`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.95)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "The minor premise denies a disjunct, not accepts one."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "The minor premise must reject one disjunct, i.e., reject all but one choice."}, {"label": "C", "li...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['B', 'C']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["deny one of the disjuncts"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "In ...`

### `mmlu-redux-business_ethics-35` (row_uid=`source-row-00000089`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.62)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.619753, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.930.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "val...`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The list of items (numbered 1,2,3,4) that the statement refers to is not provided. Without this, the meaning of the choices is undefined."], "alternative_interpretations": [], "rationale": "The task statement is a bare claim with no question and no corresponding numbered list. Choices are number combinations but the meaning of each number is missing, mak...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=uncertain.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "unclear", "equivalence_group": null, "confidence": 0.9, "rationale": "Missing numbered statements make option uninterpretable."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "unclear", "equivalence_group": null, "confidence": 0.9, "rationale": "Gold but no context to verify literal truth."}, {"label": "C", "literal_truth": "uncerta...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": true, "assumption_risk": "answer_changing", "required_assumptions": ["the intended question is missing, only a statement is provided"], "claims": [{"claim": "The task consists of a single...`

### `mmlu-redux-public_relations-34` (row_uid=`source-row-00000098`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.59)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.585185, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.878.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['B'] conflicts with option best_answers=['C']", "option defect says multiple_correct_answers but cardinality is exactly_one", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["1989"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", ...`

### `mmlu-redux-professional_law-60` (row_uid=`source-row-00000101`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["C", "D"], "confidence": 0.633333, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.950.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solut...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.95)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "False: a contract implied in law (quasi-contract) typically requires unjust enrichment, not present here."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "False: unawareness of the offer does no...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["not recover the reward"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The governing law is the common law of contracts where knowledge of the offer is required for acc...`

### `mmlu-redux-global_facts-89` (row_uid=`source-row-00000107`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.51)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.509877, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'uncertain', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.765.", "evidence_votes": ["no_correct_answer", "uncertain", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none",...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["20%"], "confidence": 0.7, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "As of 2018, about 20% of people from Tunisia say that increasing diversity makes their country a bett...`

### `mmlu-redux-professional_law-87` (row_uid=`source-row-00000108`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.99)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.990556, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.991.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-marketing-17` (row_uid=`source-row-00000111`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.60)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.6, "needs_expert": false, "assumptions_used": ["The question refers to current marketing trends."], "missing_information": ["No specific trend data or source is provided to distinguish between mobile and social media search dominance."], "alternative_interpretations": [{"interpretation": "Mobile devices are increasingly used for online searches, surpassing desktop.", "answer": "Mobile."}, {"interpretation": "Social me...`

### `mmlu-redux-business_ethics-59` (row_uid=`source-row-00000113`)

- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=1.00)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The task does not contain a question; only a statement is provided, but no query to answer."], "alternative_interpretations": [], "rationale": "The task presents only a statement about fiduciary responsibility without any question. The choices are numeric lists, but there is no clear question to connect them to, making the task unsolvable."}, "gold": "...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "Option is a list of numbers with no referent."}, {"label": "B", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "Option is a list of numbers with no referent."}, {"label": "C", "literal_truth": "invalid", "be...`

### `mmlu-redux-virology-6` (row_uid=`source-row-00000116`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.57)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.57037, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.856.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "v...`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The specific viral family referred to as 'the family' is not stated in the task."], "alternative_interpretations": [{"interpretation": "If the family is Parvoviridae, then 'Serious pneumonia' might be the exception.", "answer": "Serious pneumonia"}, {"interpretation": "If the family is Paramyxoviridae, then 'Aplastic crisis in anaemia patients' might be ...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=multiple, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Aplastic crisis is caused by Parvovirus B19, so not the exception."}, {"label": "B", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Fifth disease is caused by Parvovirus B19, so not the exception."}, {"label": "C", "litera...`

### `mmlu-redux-high_school_microeconomics-95` (row_uid=`source-row-00000117`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Incorrect: describes upward sloping supply curve, not backward bending."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Incorrect: substitution effect dominates only at lower wages."}, {"label": "C", "...`

### `mmlu-redux-high_school_statistics-10` (row_uid=`source-row-00000119`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.99)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.994815, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.995.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-logical_fallacies-37` (row_uid=`source-row-00000123`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.99)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.994815, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.995.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-college_chemistry-18` (row_uid=`source-row-00000124`)

- `llm_audit_failure` / `evaluator` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - llm_option_set failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_option_set", "error": "LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 0, 'reasoning_chars': 18796}"}`

### `mmlu-redux-virology-15` (row_uid=`source-row-00000125`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The task does not specify what to do with the choices (e.g., select the true statement)."], "alternative_interpretations": [{"interpretation": "Intended as 'Which of the following is true about viruses?'", "answer": "Grown in animals in the laboratory?"}, {"interpretation": "Intended as 'Select all that are true'", "answer": "Multiple choices could be co...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.80)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=exactly_one, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.7, "rationale": "Viruses are not universally considered a form of life; abundance is high but not definitely 'most abundant'."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Bacteria were discovered before viruses."},...`

### `mmlu-redux-management-50` (row_uid=`source-row-00000130`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.98)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9777777777777779, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Emotional intelligence involves perceiving, using, understanding, and managing emotions.", "evidence_type": "definition", "support": "Standard definition from psychology an...`

### `mmlu-redux-high_school_physics-14` (row_uid=`source-row-00000131`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "By Newton's third law, force on heavier is -F, not -1/2 F."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 1.0, "rationale": "Ambiguous 'the person'; either way, force is not -2F."}, {"label": "C", "literal_truth...`

### `mmlu-redux-virology-90` (row_uid=`source-row-00000133`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.95)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9500000000000001, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Herpes infections are managed with antiviral drugs.", "evidence_type": "external_source", "support": "Standard medical treatment for herpes simplex and varicella-zoster vir...`

### `mmlu-redux-global_facts-54` (row_uid=`source-row-00000135`)

- `presentation_corruption` / `expected_output` / `task_integrity_rule` / `review` / unknown (confidence=0.92)
  - Visible encoding or formatting corruption was detected.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Restore the original text/choice formatting and prevent lossy conversion.
  - Evidence: `{"signals": ["encoding_corruption"], "text_excerpt": "The conjecture that inequality first increases with development, then decreases with further development (known as the �inverted U hypothesis�) has, as of 2020, been\nstrongly supported by most studies supported mainly by cross-section, not time-series studies supported mainly by time-series, not cross-section studies generally repudiated by empirical studies"}`

### `mmlu-redux-international_law-98` (row_uid=`source-row-00000136`)

- `missing_context` / `context_attachment` / `static_rule` / `major` / unknown (confidence=0.85)
  - Task references passage, but no matching context artifact was found.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the referenced passage or remove the reference.
  - Evidence: `{"reference_type": "passage", "task_excerpt": "What is the meaning of \"armed attack\" in Article 51 UN Charter?"}`

### `mmlu-redux-college_medicine-1` (row_uid=`source-row-00000137`)

- `missing_context` / `context_attachment` / `static_rule` / `major` / unknown (confidence=0.85)
  - Task references passage, but no matching context artifact was found.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the referenced passage or remove the reference.
  - Evidence: `{"reference_type": "passage", "task_excerpt": "Sauna use, sometimes referred to as \"sauna bathing,\" is characterized by short-term passive exposure to extreme heat. This exposure elicits mild hyperthermia – an increase in the body's core temperature – that induces a thermoregulatory res"}`

### `mmlu-redux-virology-86` (row_uid=`source-row-00000138`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.67)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.666667, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.667.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "so...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.90)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.7, "rationale": "Pigs are often cited as mixing vessels for pandemic influenza, but the ultimate origin is wild birds. Interpretation depends on whether 'arisen from' means immediate source or reservoir."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, ...`

### `mmlu-redux-marketing-15` (row_uid=`source-row-00000141`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.58)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.577778, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.867.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["adoption rate"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The term 'rate at which a market adopts an innovation' refers to the adoption rate in diffusion of innovat...`

### `mmlu-redux-econometrics-40` (row_uid=`source-row-00000142`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.55)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.546914, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.820.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.70)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.7, "needs_expert": false, "assumptions_used": ["Assuming β_{it} is a constant slope coefficient for a regressor not shown"], "missing_information": ["The regressor associated with β_{it} is not specified", "The notation β_{it} is unconventional and could be interpreted as a varying coefficient"], "alternative_interpretations": [{"interpretation": "β_{it} is a constant coefficient β for a regressor (common textbook con...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.70)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "unclear", "equivalence_group": null, "confidence": 0.8, "rationale": "Equation includes μ_i, typical of entity fixed effects, but β_{it} is nonstandard and ambiguous."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "No time-specific intercepts present."}, {"label": ...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['C'] conflicts with option best_answers=['A']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["random effects model"], "confidence": 0.7, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The term β_{it} is interprete...`

### `mmlu-redux-virology-28` (row_uid=`source-row-00000143`)

- `source_reference_missing` / `context_attachment` / `task_integrity_rule` / `review` / unknown (confidence=0.80)
  - The task depends on an unnamed study/report and provides no source context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Identify the study/report, publication date, or source artifact.
  - Evidence: `{"matched_phrase": "the study", "task_excerpt": "A new drug with in vitro activity against HIV is tested on a population of patients with Western-blot confirmed HIV infections. Out of the 200 individuals in the patient population, 100 are chosen by lottery to receive the drug. The drug, which is tasteless, is administered in a cup of orange juice;"}`
- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `major` / review (confidence=1.00)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "v...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Case-control study is observational and retrospective; this is a randomized controlled trial."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Case report describes a single patient; this is a group stu...`

### `mmlu-redux-high_school_macroeconomics-46` (row_uid=`source-row-00000144`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.58)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.577778, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.867.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Borrowers benefit from unexpected inflation as they repay with less valuable money."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Savers with fixed-rate assets lose purchasing power, so they are harme...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Lenders, savers, and people on fixed nominal incomes are harmed by unexpectedly high inflation."], "confidence": 0.95, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["Standard macroeconomic definitions of who is harmed by unexpe...`

### `mmlu-redux-logical_fallacies-22` (row_uid=`source-row-00000156`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.64321, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.965.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.80)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Ad nauseam is repetition, not appeal to belief."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Appeal to tradition is different from appeal to belief."}, {"label": "C", "literal_truth": "false", "best...`

### `mmlu-redux-philosophy-44` (row_uid=`source-row-00000157`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.60)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.598765, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.898.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['B'] conflicts with option best_answers=['A']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["The only way to escape moral arguments is to become a fanatic."], "confidence": 0.9, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Hare discusses fanaticism as a way to escape moral arguments"...`

### `mmlu-redux-human_aging-53` (row_uid=`source-row-00000161`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The specific content of the chapter's Senior View where May Lee gives her reason for respecting elders."], "alternative_interpretations": [], "rationale": "The task references a specific chapter and individual but provides no excerpt or summary, making the intended answer unknowable without the missing context."}, "gold": "B", "choices": ["They are much ...`

### `mmlu-redux-moral_disputes-44` (row_uid=`source-row-00000164`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The task does not specify Little's argument or provide any context about the author's position on abortion. The answer depends on knowledge of a specific philosopher's view, which is not given."], "alternative_interpretations": [{"interpretation": "Choice A: fetus gains rights over time", "answer": "A"}, {"interpretation": "Choice B: fetus gains capacit...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['A'] conflicts with option best_answers=['C']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": ["the moral status of the fetus develops gradually over the course of pregnancy, so different stages warrant different moral considerations"], "confidence": 0.3, "needs_expert": true, "assumption_risk": "answer_changing", "required_assumptions":...`

### `mmlu-redux-virology-92` (row_uid=`source-row-00000166`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Pigs are intermediate hosts, not the original reservoir."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Bats (genus Pteropus) are the natural reservoir."}, {"label": "C", "literal_truth": "false", "best_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Malaysia (Sungai Nipah)"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Nipah virus originated in Malaysia, specifically in Sungai Nipah.", "evidence_type": "external_source", "support": "Ni...`

### `mmlu-redux-logical_fallacies-70` (row_uid=`source-row-00000168`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.95)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Describes complex question fallacy, not extension."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Correct definition: straw man fallacy, often called fallacy of extension."}, {"label": "C", "literal_t...`

### `mmlu-redux-electrical_engineering-34` (row_uid=`source-row-00000169`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Incorrect; resistance becomes 8R, not R."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Incorrect; resistance becomes 8R, not 2R."}, {"label": "C", "literal_truth": "false", "best_answer_status"...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["8R"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Resistance is proportional to length and inversely proportional to cross-sectional area.", "evidence_type": "definition", "support": "R = ρ...`

### `mmlu-redux-nutrition-89` (row_uid=`source-row-00000173`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The task does not specify what is being asked about the colonic microbiome (e.g., which statement is true, false, or supported)."], "alternative_interpretations": [{"interpretation": "The task is to select the correct statement about the colonic microbiome.", "answer": "D"}, {"interpretation": "The task is to select the false statement about the colonic ...`

### `mmlu-redux-virology-73` (row_uid=`source-row-00000180`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.97)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.966667, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.967.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-security_studies-5` (row_uid=`source-row-00000181`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The acronym 'HM' is not defined. It likely stands for 'Historical Materialism' in security studies, but this is not stated."], "alternative_interpretations": [{"interpretation": "HM stands for 'Historical Materialism'", "answer": "Option B (HM has some aspects in common with realism, liberalism, and social constructivism, but it offers something distinc...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=multiple, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "unclear", "equivalence_group": null, "confidence": 0.7, "rationale": "Vague phrase 'discernable realities' makes truth value uncertain in theoretical context."}, {"label": "B", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Correctly describes HM's focus on class conflict and comm...`

### `mmlu-redux-high_school_european_history-98` (row_uid=`source-row-00000182`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.56)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": ["Paul Broca"], "confidence": 0.564198, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.846.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['PAUL BROCA'] conflicts with option best_answers=['D']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Paul Broca"], "confidence": 0.9, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The question expects the name ...`

### `mmlu-redux-conceptual_physics-94` (row_uid=`source-row-00000183`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.94)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.938888888888889, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Spectral lines are characteristic patterns unique to each element.", "evidence_type": "definition", "support": "Each element has a unique set of spectral lines due to its di...`

### `mmlu-redux-virology-23` (row_uid=`source-row-00000184`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.70)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.7, "needs_expert": false, "assumptions_used": [], "missing_information": ["Definition of 'most effective' (e.g., efficacy, adherence, population-level impact)", "Sexual orientation or risk group context (e.g., MSM vs heterosexual)", "Frequency thresholds for 'frequent' vs 'infrequent'"], "alternative_interpretations": [{"interpretation": "Assume 'most effective' means highest efficacy in clinical trials for high-risk ...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['C'] conflicts with option best_answers=['A']", "option defect says multiple_correct_answers but cardinality is exactly_one"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": ["HIV-negative individuals at high risk of acquiring HIV, particularly men who have sex with men (MSM) and serodiscordant couples"], "confidence": 0.4, "needs_expert":...`

### `mmlu-redux-human_sexuality-13` (row_uid=`source-row-00000190`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The specific psychological theory or framework to apply."], "alternative_interpretations": [{"interpretation": "Psychoanalytic theory might support choice A (childhood sexual arousal pattern).", "answer": "A"}, {"interpretation": "Theory of self-doubt might support choice B.", "answer": "B"}, {"interpretation": "Existential or psychodynamic theory might...`

### `mmlu-redux-business_ethics-54` (row_uid=`source-row-00000191`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The numbered options (1, 2, 3, 4) are not defined.", "The specific code being enforced is not described."], "alternative_interpretations": [], "rationale": "The task 'How the code is enforced' lacks any context or definitions for the numbered choices, making it impossible to determine the intended answer."}, "gold": "B", "choices": ["1,2,3", "1,2,4", "1,...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.95)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=uncertain.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 0.2, "rationale": "Missing enumerated items; option is uninterpretable."}, {"label": "B", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 0.2, "rationale": "Missing enumerated items; option is uninterpretable."}, {"label": "C", "literal_truth": ...`

### `mmlu-redux-virology-80` (row_uid=`source-row-00000192`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Filoviruses are not ball-like."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Filoviruses have filamentous morphology."}, {"label": "C", "literal_truth": "false", "best_answer_status": "weaker", "clarity":...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Filoviruses have a filamentous (thread-like) morphology, often appearing as long, curved, or branched particles. They are enveloped with a helical nucleocapsid."], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "cl...`

### `mmlu-redux-marketing-3` (row_uid=`source-row-00000195`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": true, "assumptions_used": [], "missing_information": ["The task does not specify what the four main tasks of marketing communications are."], "alternative_interpretations": [{"interpretation": "Assuming the standard four tasks (inform, persuade, remind, differentiate), then Participate is not part.", "answer": "Participate"}, {"interpretation": "If the four tasks are different (e.g., inform, persuade, remind,...`

### `mmlu-redux-college_chemistry-89` (row_uid=`source-row-00000197`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.97)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.970833, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer']; agreement=2/2; mean_stage_confidence=0.971.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 2, "blind_solution": {"solution_status": "solved", "valid_answers": ["B"], "equivalen...`
- `llm_audit_failure` / `evaluator` / `llm_gold_audit` / `review` / unknown (confidence=1.00)
  - llm_gold_audit failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_gold_audit", "error": "structured gold evidence stages failed: defender"}`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['B'] conflicts with option best_answers=['D']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["9"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "A single nitronyl nitroxide rad...`

### `mmlu-redux-logical_fallacies-92` (row_uid=`source-row-00000198`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.67)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.666667, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=1.000.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.95)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.95, "needs_expert": true, "assumptions_used": ["Assume 'ad crumenam' is a known logical fallacy"], "missing_information": ["Which broader fallacy category 'ad crumenam' belongs to is not provided"], "alternative_interpretations": [{"interpretation": "Ad crumenam is a fallacy of relevance, not covered by any option", "answer": "None of the above"}, {"interpretation": "It might be considered a type of false sign", "answ...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.70)
  - Option set auditor reported bad_options_clarity with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Ad crumenam is an appeal to wealth, not a false analogy."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Ad crumenam is not a hasty generalization."}, {"label": "C", "literal_truth": "uncertain",...`

### `mmlu-redux-logical_fallacies-64` (row_uid=`source-row-00000199`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Describes straw man fallacy, not appeal to emotions."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Describes tu quoque fallacy, not appeal to emotions."}, {"label": "C", "literal_truth": "uncertain", "...`

### `mmlu-redux-sociology-18` (row_uid=`source-row-00000200`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.62)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.619753, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.930.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", ...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['B'] conflicts with option best_answers=['D']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Herberg suggested that religion in America functions as a source of social identity and that the three major faiths (Protestant, Catholic, and Jew) form a \...`

### `mmlu-redux-human_sexuality-8` (row_uid=`source-row-00000201`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Literally true; a reason for similarity-attraction."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Literally true; a reason for similarity-attraction."}, {"label": "C", "literal_truth": "true", "best_answer_s...`

### `mmlu-redux-high_school_psychology-51` (row_uid=`source-row-00000202`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": true, "assumptions_used": [], "missing_information": ["The statements labeled I, II, and III are not provided in the task."], "alternative_interpretations": [], "rationale": "The task asks to select which statements are disadvantages, but the actual statements I, II, III are missing from the context. Without them, the question is unsolvable."}, "gold": "D", "choices": ["I only", "II only", "III only", "I and ...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "Option refers to unspecified statement I"}, {"label": "B", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "Option refers to unspecified statement II"}, {"label": "C", "literal_truth": "invalid", "best_answer...`

### `mmlu-redux-high_school_us_history-32` (row_uid=`source-row-00000204`)

- `missing_context` / `context_attachment` / `static_rule` / `major` / unknown (confidence=0.85)
  - Task references figure, but no matching context artifact was found.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the referenced figure or remove the reference.
  - Evidence: `{"reference_type": "figure", "task_excerpt": "This question refers to the following information.\n\"With 78 percent of the Union electorate casting ballots, Lincoln was reelected in an Electoral College landslide, 212 to McClellan's 21. The 55% popular vote for the president was the thir"}`

### `mmlu-redux-high_school_psychology-91` (row_uid=`source-row-00000205`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The definitions of I, II, and III (which scans they refer to) are missing."], "alternative_interpretations": [], "rationale": "The question lists choices as 'I only', 'II only', etc., but never defines what I, II, III represent. Without that context, the task is unsolvable."}, "gold": "C", "choices": ["I only", "II only", "III only", "II and III only"], ...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "I, II, III undefined; cannot evaluate."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "I, II, III undefined; cannot evaluate."}, {"label": "C", "literal_truth": "uncertain", "best_answe...`

### `mmlu-redux-computer_security-46` (row_uid=`source-row-00000207`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.66)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.664198, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.996.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", ...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Classic CIA property, not the answer"}, {"label": "B", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Classic CIA property, not the answer"}, {"label": "C", "literal_truth": "false", "best_answer_status": "best", "clarity"...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": ["Authentication"], "confidence": 0.9, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The three classic security properties are Confidentiality, Integrity, and Availability (CIA triad).", "Authentication is not considered a cl...`

### `mmlu-redux-public_relations-56` (row_uid=`source-row-00000209`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Content analysis of existing data is a form of secondary research."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Surveys are primary research, collecting new data."}, {"label": "C", "literal_truth": "...`

### `mmlu-redux-marketing-86` (row_uid=`source-row-00000213`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The actual question that the task statement and choices are meant to answer is not provided. The given text 'Economic—marketing should encourage long-term economic development as opposed to short-term economic development.' does not form a coherent question."], "alternative_interpretations": [{"interpretation": "The task might be asking 'Which three pill...`

### `mmlu-redux-international_law-56` (row_uid=`source-row-00000216`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.61)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.608642, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.913.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`

### `mmlu-redux-global_facts-34` (row_uid=`source-row-00000220`)

- `presentation_corruption` / `expected_output` / `task_integrity_rule` / `review` / unknown (confidence=0.92)
  - Visible encoding or formatting corruption was detected.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Restore the original text/choice formatting and prevent lossy conversion.
  - Evidence: `{"signals": ["spreadsheet_date_conversion"], "text_excerpt": "The global HIV/AIDS death rate is highest for which of these age groups?\nUnder 5 14-May 15-49 over 50"}`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Under 5 age group has lower HIV/AIDS death rate than 15-49."}, {"label": "B", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "Option '14-May' is likely a corrupted representation of '5-14' or a date, making it ...`

### `mmlu-redux-high_school_physics-67` (row_uid=`source-row-00000222`)

- `llm_audit_failure` / `evaluator` / `llm_gold_audit` / `review` / unknown (confidence=1.00)
  - llm_gold_audit failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_gold_audit", "error": "option_applicability: LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 223, 'reasoning_chars': 18887}"}`
- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.9, "needs_expert": false, "assumptions_used": [], "missing_information": ["refractive index of lens material"], "alternative_interpretations": [{"interpretation": "Assume refractive index n=1.5 (typical glass)", "answer": "Real, inverted, height = 4 cm (not in choices)"}, {"interpretation": "Assume focal length f = R/2 = 10 cm (e.g., n=2 or simplified formula)", "answer": "Real, inverted, height = 1 cm"}], "rationale": "The l...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.95)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "If f=20 cm (standard lens formula), image is real inverted height 4 cm, not 1 cm. Option A only correct if incorrect f=R/2 used."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Virtual image only...`

### `mmlu-redux-business_ethics-64` (row_uid=`source-row-00000223`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The full question statement is missing; only 'Demand reduction.' is provided. No context about what items 1,2,3,4 refer to."], "alternative_interpretations": [], "rationale": "The task consists solely of the phrase 'Demand reduction.' with multiple-choice options listing numbers. Without any accompanying context or definitions for items 1-4, the intende...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=uncertain.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "uncertain", "clarity": "unclear", "equivalence_group": null, "confidence": 0.9, "rationale": "Cannot determine truth without full question context."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "uncertain", "clarity": "unclear", "equivalence_group": null, "confidence": 0.9, "rationale": "Cannot determine truth without full question context."}, {"label": "C", "literal_tr...`

### `mmlu-redux-global_facts-74` (row_uid=`source-row-00000225`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.60)
  - Option set auditor reported no_correct_answer with literal_cardinality=uncertain, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.6, "rationale": "Main claim (Africa has greatest population growth) is true, but secondary clause 'lowest economic growth' is debatable."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Main claim (Asia) is fa...`

### `mmlu-redux-nutrition-73` (row_uid=`source-row-00000228`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.95)
  - Independent option checks found multiple choices that satisfy the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"option_evidence": {"solution_status": "multiple", "valid_answers": ["A", "B", "C"], "equivalent_answers": [], "independently_acceptable_answers": ["A", "B", "C"], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9500000000000001, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Nutritional epidemiology focuses on diet-disease relationships.", "evidence_type": "definition", "support": "Standard definition from epidemio...`

### `mmlu-redux-high_school_world_history-39` (row_uid=`source-row-00000233`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["B", "D"], "confidence": 0.62963, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.944.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_soluti...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": false, "assumptions_used": ["The passage lists three fundamentals: industry, serving husband (including purity), and ancestor worship."], "missing_information": ["The question does not specify which theme is 'more common' or 'central'; both ancestor worship and female purity are present in the passage and were common in patriarchal ancient societies."], "alternative_interpretations": [{"interpretati...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Women's duty to serve their husbands and maintain the household"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The passage emphasizes women's domestic ...`

### `mmlu-redux-logical_fallacies-13` (row_uid=`source-row-00000235`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.65)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["C", "D"], "confidence": 0.645679, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.969.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solu...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.95, "needs_expert": false, "assumptions_used": ["ignoratio elenchi and irrelevant conclusion are synonymous fallacies"], "missing_information": [], "alternative_interpretations": [{"interpretation": "The fallacy is named 'irrelevant conclusion'", "answer": "irrelevant conclusion"}, {"interpretation": "The fallacy is named 'ignoratio elenchi'", "answer": "ignoratio elenchi"}], "rationale": "The task describes a fallacy...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Straw person is a different fallacy."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Genetic fallacy is a different fallacy."}, {"label": "C", "literal_truth": "true", "best_answer_status": "best...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["red herring"], "confidence": 0.9, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The fallacy of using irrelevant information to support a claim is called red herring.", "evid...`

### `mmlu-redux-astronomy-74` (row_uid=`source-row-00000239`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 1.0, "rationale": "Mass calculation gives 2.2e16 kg; A is 5 orders too low."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 1.0, "rationale": "Off by 2 orders; also ambiguous notation."}, {"label": "C", "literal_truth": "false", ...`

### `mmlu-redux-high_school_macroeconomics-61` (row_uid=`source-row-00000244`)

- `incomplete_task_instruction` / `task_specification` / `task_integrity_rule` / `review` / review (confidence=0.90)
  - The task appears to contain a missing blank or truncated instruction.
  - Evidence: `unclassified` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Restore the missing blank, command, or original task instruction.
  - Evidence: `{"signals": ["missing_term_length_blank", "missing_member_count_blank"], "task_excerpt": "The FED's Board of Governors has members each serving -year terms."}`

### `mmlu-redux-logical_fallacies-3` (row_uid=`source-row-00000245`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.95)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.95, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.950.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["red herring"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The argument commits a red herring fallacy.", "evidence_type": "task_text", "support": "The ...`

### `mmlu-redux-abstract_algebra-24` (row_uid=`source-row-00000246`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.67)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.665432, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.998.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Both statements are true: every maximal ideal is prime, and R/I is a field iff I is maximal."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Claims both false, but both are true."}, {"label": "C", "lite...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Both statements are true."], "confidence": 1.0, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["Rings are assumed to be commutative with identity."], "claims": [{"claim": "Statement 1: In a commutative ring with identity, every ...`

### `mmlu-redux-business_ethics-2` (row_uid=`source-row-00000248`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.51)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.509877, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'uncertain', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.765.", "evidence_votes": ["no_correct_answer", "uncertain", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none",...`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The meaning of numbers 1-4 (e.g., a list of statements or options)"], "alternative_interpretations": [], "rationale": "The task states 'Insider trading undermines the fiduciary relationship.' but the choices are sets of numbers with no explanation of what the numbers refer to. Without context defining 1-4, the question is unanswerable."}, "gold": "B", "c...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=uncertain.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "Option refers to undefined numbers; meaning impossible to determine."}, {"label": "B", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "Option refers to undefined numbers; meaning impossible to determine."}, ...`

### `mmlu-redux-logical_fallacies-94` (row_uid=`source-row-00000249`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.61)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.608642, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.913.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["loaded question fallacy (complex question)"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The question 'So, how long have you been beating your wife?' i...`

### `mmlu-redux-college_mathematics-15` (row_uid=`source-row-00000250`)

- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=1.00)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The fifth condition is not provided; only four conditions are listed but the problem states there are five."], "alternative_interpretations": [], "rationale": "The task states there are five conditions but only four are supplied, making it impossible to determine which is equivalent to none of the other four. The missing condition is a critical defect....`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "This condition is weaker than invertibility; it does not imply B, C, or D, while B, C, D are equivalent."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": "group1", "confidence": 1.0, "rationale": "Equivalent to C and D, but not to A."}, ...`

### `mmlu-redux-public_relations-54` (row_uid=`source-row-00000252`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.95)
  - Option set auditor reported no_correct_answer with literal_cardinality=multiple, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Interpersonal communication is widely recognized as most effective for attitude change due to personal influence."}, {"label": "B", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Media can influence but is less effective tha...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['A']", "option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Public relations"], "confidence": 0.8, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The question expects the answer 'Public relations' a...`

### `mmlu-redux-virology-31` (row_uid=`source-row-00000253`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.99)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.990741, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.991.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-logical_fallacies-11` (row_uid=`source-row-00000254`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.70)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.7, "needs_expert": false, "assumptions_used": [], "missing_information": [], "alternative_interpretations": [{"interpretation": "Denying the Antecedent: The reasoning follows if-then logic: if intelligent then succeed, many not intelligent, therefore not succeed (so don't belong).", "answer": "Denying the Antecedent"}, {"interpretation": "Ad Hominem: The speaker attacks the intelligence of college attendees rather tha...`

### `mmlu-redux-professional_psychology-47` (row_uid=`source-row-00000258`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.53)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.5277777777777778, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "At birth, the least developed part of the brain is the frontal lobe.", "evidence_type": "external_source", "support": "Neurodevelopmental studies indicate that the frontal ...`

### `mmlu-redux-international_law-62` (row_uid=`source-row-00000262`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": true, "assumptions_used": [], "missing_information": ["The content or elements of the Osman test are not provided in the task statement."], "alternative_interpretations": [], "rationale": "The task asks which statement is not part of the Osman test, but the test itself is not defined or referenced in the provided text. The answer depends on external legal knowledge not supplied in the task."}, "gold": "A", "...`

### `mmlu-redux-virology-91` (row_uid=`source-row-00000264`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "NGS is commonly used to identify novel viruses."}, {"label": "B", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "NGS is widely used to detect drug-resistant mutants."}, {"label": "C", "literal_truth": "true", "best...`

### `mmlu-redux-professional_law-7` (row_uid=`source-row-00000270`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.61)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.61358, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.920.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "vali...`

### `mmlu-redux-astronomy-10` (row_uid=`source-row-00000272`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.66)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.657778, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.987.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "val...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Pluto has five moons: one large (Charon) and four small. Option A says one medium and two small, which is outdated and incorrect."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Pluto definitely has ...`

### `mmlu-redux-miscellaneous-61` (row_uid=`source-row-00000274`)

- `missing_condition` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.95)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.95, "needs_expert": true, "assumptions_used": [], "missing_information": ["Number of Americans", "Average ice wasted per person per year", "Energy content of ice (latent heat of fusion)", "Frequency of ice waste"], "alternative_interpretations": [{"interpretation": "Assuming 300M Americans, 100g ice wasted per drink, 1 drink per day -> ~3.66e15 J", "answer": "6*10^14 J"}, {"interpretation": "Assuming 300M Americans, 10g ice w...`

### `mmlu-redux-conceptual_physics-37` (row_uid=`source-row-00000275`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.95)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.95, "needs_expert": true, "assumptions_used": ["standard physics definitions of DC and AC"], "missing_information": ["whether 'steadily' is considered a necessary part of the definition of DC"], "alternative_interpretations": [{"interpretation": "DC charges flow steadily in one direction", "answer": "steadily in one direction"}, {"interpretation": "DC charges flow in one direction (not necessarily steadily)", "answer"...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says multiple_correct_answers but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["in one direction"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["conventional current direction is used"], "claims": [{"claim": "In DC circuits, charges flow consistently in one direction.", "evidenc...`

### `mmlu-redux-human_sexuality-7` (row_uid=`source-row-00000277`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.95)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.95, "needs_expert": true, "assumptions_used": [], "missing_information": ["The phrase 'certain people' is vague: does it refer to official doctrine, predominant view, or any individual adherent?"], "alternative_interpretations": [{"interpretation": "Which religion has some adherents who hold that abortion is murder?", "answer": "all of the above"}, {"interpretation": "Which religion's official or widespread teaching i...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=multiple, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Some Orthodox Jews hold that abortion is murder, so the statement is factually true, but it is a partial answer."}, {"label": "B", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Fundamentalist Protestants commonly hold tha...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['B', 'C'] conflicts with option best_answers=['D']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Roman Catholicism"], "confidence": 0.8, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The question expects the religion most commonly associated with the view that abortion is murder."], "claims": [{"cla...`

### `mmlu-redux-professional_medicine-0` (row_uid=`source-row-00000278`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.70)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.7, "needs_expert": false, "assumptions_used": ["Classic presentation of hot tub folliculitis due to Pseudomonas aeruginosa"], "missing_information": ["Photograph of rash not provided, which is critical to confirm morphology and rule out other conditions"], "alternative_interpretations": [{"interpretation": "If rash is folliculitis, answer is hair follicle", "answer": "Hair follicle"}, {"interpretation": "If rash is something li...`

### `mmlu-redux-virology-27` (row_uid=`source-row-00000280`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": true, "assumptions_used": [], "missing_information": ["The total population of the city is not clearly stated."], "alternative_interpretations": [{"interpretation": "Total population is 250,000, and deaths from disease are 400. Prevalence is interpreted as mortality rate, giving 400/250,000.", "answer": "400/250,000"}, {"interpretation": "Number of cases is 250,000, and deaths from disease are 400. ...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Represents disease death rate, not prevalence."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Unclear derivation, not prevalence."}, {"label": "C", "literal_truth": "false", "best_answer_status"...`

### `mmlu-redux-virology-8` (row_uid=`source-row-00000282`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["Context about Professor Shoptaw and their recommended intervention strategies"], "alternative_interpretations": [], "rationale": "The task asks for intervention strategies according to Professor Shoptaw but provides no context about who this is or what they advocate. Without this information, the question is unsolvable and the correct answer cannot be d...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.50)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.7, "rationale": "Gold answer; literal truth uncertain without source knowledge."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.6, "rationale": "Plausible but not the gold; may not match Shoptaw's strategies."}, {"label": "C", "lit...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "uncertain", "derived_answers": [], "confidence": 0.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": ["The task text is insufficient; no context or choices provided."], "claims": [{"claim": "The question asks for three key interve...`

### `mmlu-redux-nutrition-13` (row_uid=`source-row-00000284`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The intended relational operator in choice A is unclear; the '?' symbol could be a typo for '≥', '≤', or something else, leading to different answers."], "alternative_interpretations": [{"interpretation": "If '?' is '≥', then fasting blood glucose ≥ 140 mg/dl also meets a diagnostic threshold (older criteria), making both A and D possibly corr...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "unclear", "equivalence_group": null, "confidence": 0.9, "rationale": "Symbol '?' unclear; if '≥' it is true but not standard threshold."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Random glucose >160 mg/dL is below diagnostic threshold of ≥200 mg/dL."}, {"lab...`

### `mmlu-redux-human_sexuality-15` (row_uid=`source-row-00000291`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `major` / review (confidence=0.97)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.972222, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.972.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.90)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "1 cm is too high; typical length is ~0.5-0.6 cm."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "2 cm is much too large for 28 days."}, {"label": "C", "literal_truth": "false", "best_answer_statu...`

### `mmlu-redux-international_law-84` (row_uid=`source-row-00000295`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=1.00)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Cultural relativism is the principle of understanding beliefs and practices within their own cultural context.", "evidence_type": "definition", "support": "Standard definition from anthro...`

### `mmlu-redux-abstract_algebra-96` (row_uid=`source-row-00000296`)

- `llm_audit_failure` / `evaluator` / `llm_question_clarity` / `review` / unknown (confidence=1.00)
  - llm_question_clarity failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_question_clarity", "error": "LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 0, 'reasoning_chars': 17146}"}`

### `mmlu-redux-logical_fallacies-38` (row_uid=`source-row-00000297`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-business_ethics-80` (row_uid=`source-row-00000300`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The task lacks any scenario, list of items or statements, or description of what the numbers 1,2,3,4 correspond to. The phrase 'The need to head off negative publicity' is provided without context, making it impossible to determine which choices are correct."], "alternative_interpretations": [], "rationale": "The task consists only of a generic phrase wi...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.60)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=uncertain.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.2, "rationale": "Stem incomplete, cannot evaluate truth of option."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.2, "rationale": "Stem incomplete, cannot evaluate truth of option."}, {"label": "C", "literal_truth": "unc...`

### `mmlu-redux-professional_law-29` (row_uid=`source-row-00000303`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.92)
  - Independent option checks found multiple choices that satisfy the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"option_evidence": {"solution_status": "multiple", "valid_answers": ["C", "D"], "equivalent_answers": ["C", "D"], "independently_acceptable_answers": ["C"], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9222222222222223, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The rancher's drainage system on parcel B after sale constitutes a trespass unless an easement exists.", "evidence_type": "task_text", "support": "Th...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['C', 'D'] conflicts with option best_answers=['B']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["the farmer"], "confidence": 0.9, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The rancher's drainage system on parcel B after sale constitutes a trespass unless an easement exists.", "ev...`

### `mmlu-redux-computer_security-8` (row_uid=`source-row-00000312`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.61)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.606173, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.909.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Application layer"], "confidence": 0.9, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Brute-force attacks on access credentials target authentication mechanisms at the Appli...`

### `mmlu-redux-college_chemistry-80` (row_uid=`source-row-00000314`)

- `llm_audit_failure` / `evaluator` / `llm_gold_audit` / `review` / unknown (confidence=1.00)
  - llm_gold_audit failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_gold_audit", "error": "blind_solver: LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 0, 'reasoning_chars': 14375}"}`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.95)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.95, "needs_expert": true, "assumptions_used": [], "missing_information": ["Definition of magnetic moment (projection vs magnitude convention)"], "alternative_interpretations": [{"interpretation": "Magnetic moment as projection (μ = g I μ_N)", "answer": "none matches exactly; possibly 2H or 6Li with rounding, but no clear choice"}, {"interpretation": "Magnetic moment as magnitude (μ = g sqrt(I(I+1)) μ_N)", "answer": "1...`
- `llm_audit_failure` / `evaluator` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - llm_option_set failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_option_set", "error": "LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 0, 'reasoning_chars': 15280}"}`

### `mmlu-redux-jurisprudence-18` (row_uid=`source-row-00000316`)

- `missing_condition` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.90)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.9, "needs_expert": true, "assumptions_used": ["Standard Hohfeldian scheme includes all four pairs as correlatives."], "missing_information": ["The question implies a contradiction exists, but all given pairs are correct correlatives, making the task unsolvable without a 'none' option."], "alternative_interpretations": [{"interpretation": "All four pairs are correlatives, so no answer contradicts.", "answer": "None of the abov...`

### `mmlu-redux-high_school_macroeconomics-63` (row_uid=`source-row-00000318`)

- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.9, "needs_expert": false, "assumptions_used": [], "missing_information": ["what 'each' refers to (e.g., each quarter, each week, each month)"], "alternative_interpretations": [{"interpretation": "GDP is calculated for each quarter by the Bureau of Economic Analysis", "answer": "quarter; The Bureau of Economic Analysis"}, {"interpretation": "GDP is calculated for each week by the Bureau of Economic Analysis", "answer": "week; ...`

### `mmlu-redux-high_school_macroeconomics-80` (row_uid=`source-row-00000321`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.62)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.619753, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.930.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "va...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Barter is not included in GDP."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Household production is not in GDP."}, {"label": "C", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "...`

### `mmlu-redux-high_school_microeconomics-1` (row_uid=`source-row-00000323`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.641975, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.963.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", ...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.95)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "In capitalist market economy, resources are allocated by markets, not central bank."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Private property is a foundational principle of capitalism."}, {"label": "...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The multiple-choice options are not provided in the input, making the question unanswerable.", "evidence_type": "task_text", "support": "Onl...`

### `mmlu-redux-sociology-83` (row_uid=`source-row-00000328`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The task does not include a clear question or prompt to connect the phrase 'World-affirming religions:' to the provided choices. It is unclear what exactly is being asked (e.g., definition, example, characteristic)."], "alternative_interpretations": [{"interpretation": "Assuming the task asks 'Which of the following best describes world-affirming religi...`

### `mmlu-redux-virology-16` (row_uid=`source-row-00000329`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.62)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": ["B"], "confidence": 0.622222, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.933.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solut...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.80)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Working in a category IV lab is a risk factor but not typically the biggest; funerals and home nursing are more common."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Attending funerals with contact to bodi...`

### `mmlu-redux-high_school_biology-96` (row_uid=`source-row-00000330`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-high_school_european_history-43` (row_uid=`source-row-00000331`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Not supported by passage; historically questionable."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.7, "rationale": "Overstated; he ruled effectively overall."}, {"label": "C", "literal_truth": "uncertain", "bes...`

### `mmlu-redux-management-1` (row_uid=`source-row-00000332`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": true, "assumptions_used": [], "missing_information": ["The specific management framework or typology of plans being referenced"], "alternative_interpretations": [{"interpretation": "Standard management classification does not include ad hoc as a formal plan type", "answer": "Ad hoc"}, {"interpretation": "All listed could be considered types of plans under some definitions", "answer": "Uncertain"}], "rationale...`

### `mmlu-redux-high_school_european_history-20` (row_uid=`source-row-00000337`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.97)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9666666666666666, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The Carlsbad Resolutions aimed to suppress liberal and nationalist movements.", "evidence_type": "external_source", "support": "Historical knowledge: Carlsbad Resolutions i...`

### `mmlu-redux-philosophy-80` (row_uid=`source-row-00000338`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["Which philosopher named Wolf is being referred to? (e.g., Susan Wolf, Christian Wolff, etc.)", "What is the specific claim about morality?"], "alternative_interpretations": [], "rationale": "The task statement only provides 'Wolf claims that morality:' without specifying which philosopher or any context. Multiple philosophers named Wolf have different vi...`

### `mmlu-redux-virology-3` (row_uid=`source-row-00000339`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.80)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.8, "needs_expert": false, "assumptions_used": [], "missing_information": ["Geographic context (e.g., US Latinos vs. Latin America)", "Time frame or data source"], "alternative_interpretations": [{"interpretation": "Assuming US data, men who have sex with men are the major risk group among Latinos", "answer": "Homosexual males"}, {"interpretation": "Assuming global data, heterosexual transmission may be the major risk ...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Heterosexual males are not the major risk group; MSM is larger."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Homosexual males (MSM) are the major risk group for HIV among Latinos."}, {"label": "C", "lite...`

### `mmlu-redux-security_studies-1` (row_uid=`source-row-00000342`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": true, "assumptions_used": ["HM is an undefined acronym"], "missing_information": ["Definition of 'HM'"], "alternative_interpretations": [{"interpretation": "HM as Human Security (common in security studies)", "answer": "Choice 3 likely correct as human security was marginalized during Cold War and later integrated"}, {"interpretation": "HM as Historical Materialism", "answer": "Different choice might be corre...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['C']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": true, "assumption_risk": "answer_changing", "required_assumptions": ["The acronym 'HM' is not defined in the task; its meaning must be assumed (e.g., Heavy Missiles, Hard Mobile, Humanitarian Mine). The ans...`

### `mmlu-redux-professional_law-81` (row_uid=`source-row-00000343`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.52)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.520988, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.781.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`

### `mmlu-redux-virology-84` (row_uid=`source-row-00000346`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["A", "C"], "confidence": 0.637037, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'multiple_correct_answers', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.956.", "evidence_votes": ["none", "multiple_correct_answers", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solut...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.99)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Combination therapy does not completely suppress replication."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Drugs do penetrate cells."}, {"label": "C", "literal_truth": "true", "best_answer_status": "...`

### `mmlu-redux-college_medicine-3` (row_uid=`source-row-00000347`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.640741, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.641.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['B'] conflicts with option best_answers=['D']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["The modification changes codon AAC (asparagine) to ACC (threonine), a missense mutation that likely impairs the protein's function in potassium transport."]...`

### `mmlu-redux-business_ethics-51` (row_uid=`source-row-00000348`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.92)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9222222222222223, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Deliberately obscuring the true cost of an item is known as cost obfuscation in business ethics.", "evidence_type": "definition", "support": "Standard business ethics termi...`

### `mmlu-redux-high_school_statistics-0` (row_uid=`source-row-00000350`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=1.00)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 1.0, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The samples are independent and identically distributed; the population has finite variance; the sample size is sufficiently large (typically n ≥ 30)."], "claims": [{"claim": "The central limit theorem d...`

### `mmlu-redux-miscellaneous-37` (row_uid=`source-row-00000353`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["Actual statistic for cups of coffee consumed in the US in the past week as of 2013"], "alternative_interpretations": [], "rationale": "The task asks for a specific real-world statistic without providing any data or source. The answer cannot be determined from the given information alone, constituting missing context."}, "gold": "C", "choices": ["300 mil...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.70)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.8, "rationale": "300 million per week is far below typical estimates of 400 million per day (2.8 billion per week)."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.6, "rationale": "1 billion per week is low; typical estimates are...`

### `mmlu-redux-professional_accounting-26` (row_uid=`source-row-00000354`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.95)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Incorrect; 40% would result from dividing 10% by 0.25, not 4."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Incorrect; this is the ROA, not the profit margin."}, {"label": "C", "literal_truth":...`

### `mmlu-redux-econometrics-66` (row_uid=`source-row-00000355`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.66)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.655556, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.983.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "...`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["Details of question 21 (e.g., test statistic, critical value, p-value, significance level, sample data)"], "alternative_interpretations": [], "rationale": "The task references 'question 21' without providing its details, making it impossible to determine the conclusion for the 2-sided alternative. The answer depends on unknown test statistics or p-values...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.85)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.6, "rationale": "Without context from Q21, cannot determine if H0 is rejected; D is more appropriate."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.6, "rationale": "Same uncertainty as A."}, {"label": "C", "literal_truth": "fal...`

### `mmlu-redux-college_chemistry-93` (row_uid=`source-row-00000358`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-public_relations-36` (row_uid=`source-row-00000362`)

- `duplicate_choices` / `oracle_ground_truth` / `static_rule` / `review` / review (confidence=0.75)
  - Two or more choices normalize to the same text.
  - Evidence: `deterministic_rule` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Deduplicate choices unless duplicates are intentional distractors that do not affect the gold answer.
  - Evidence: `{"duplicates": [[2, 3, "manipulative"]], "choices": ["proactive", "reactive", "manipulative", "manipulative"]}`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.95)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Proactive is opposite of reactive; does not fit 'occur only after negative'."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Reactive correctly describes PR that occurs only after negative events."}, {"...`

### `mmlu-redux-high_school_biology-2` (row_uid=`source-row-00000363`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `major` / review (confidence=1.00)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.998148, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.998.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none...`
- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The correct answer option (island forms and mainland forms share a common ancestor) is missing from the choices."], "alternative_interpretations": [], "rationale": "The question is clearly worded, but the answer choices do not include the correct biological explanation (common ancestry). The presence of a '0' choice and lack of a correct option render...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "Option is a placeholder '0', not a meaningful answer."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "The observation shows different organisms, not same."}, {"label": "C", "literal_truth": "false...`

### `mmlu-redux-public_relations-3` (row_uid=`source-row-00000370`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.99)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.990741, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.991.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-logical_fallacies-93` (row_uid=`source-row-00000372`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.92)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.924074, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.924.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none"...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.95)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "a priori is not a fallacy."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Complex proposition is not a standard fallacy name for this description; usually complex question."}, {"label": "C", "...`

### `mmlu-redux-college_chemistry-1` (row_uid=`source-row-00000374`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `major` / review (confidence=0.98)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.981481, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.981.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.95)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Calculated g from given fields and frequency is approximately 2.107, not 2.002."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "g=1.950 is far from calculated value 2.107."}, {"label": "C", "literal_tr...`

### `mmlu-redux-high_school_chemistry-19` (row_uid=`source-row-00000376`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.95, "needs_expert": false, "assumptions_used": ["ideal gas behavior", "thermodynamic first law"], "missing_information": [], "alternative_interpretations": [{"interpretation": "E=0 is correct because internal energy depends only on temperature.", "answer": "E = 0"}, {"interpretation": "q=-w is correct because ΔE=0 implies q=-w.", "answer": "q = -w"}], "rationale": "Both 'E = 0' and 'q = -w' are true for an ideal gas u...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "For isothermal expansion, heat q is not zero."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Work w is done by the gas, so w is not zero."}, {"label": "C", "literal_truth": "false", "best_answer...`

### `mmlu-redux-high_school_biology-94` (row_uid=`source-row-00000377`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.65)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.646914, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.970.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", ...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Platyhelminthes are acoelomate, no true coelom."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Porifera (sponges) lack true coelom; they are parazoans without true tissues."}, {"label": "C", "li...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": ["Annelida", "Arthropoda", "Mollusca", "Echinodermata", "Chordata"], "confidence": 0.2, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "True coelom is a body cavity completely lined with mesoderm.", "evidence_ty...`

### `mmlu-redux-business_ethics-31` (row_uid=`source-row-00000378`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The task does not specify what purposes (1, 2, 3) refer to; no context or list of purposes is provided."], "alternative_interpretations": [], "rationale": "The statement is a sentence fragment lacking any context about what 'purposes' are meant. Without knowing what options 1, 2, and 3 represent, it is impossible to determine which combination is correct...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=uncertain.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "invalid", "clarity": "unclear", "equivalence_group": null, "confidence": 0.9, "rationale": "Missing context prevents evaluation"}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "invalid", "clarity": "unclear", "equivalence_group": null, "confidence": 0.9, "rationale": "Missing context prevents evaluation"}, {"label": "C", "literal_truth": "uncertain", "best_answer_status":...`

### `mmlu-redux-formal_logic-54` (row_uid=`source-row-00000381`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.50)
  - Gold auditor reported multiple_correct_answers with gold_status=uncertain.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "uncertain", "defect_type": "multiple_correct_answers", "correct_answers": ["A", "B", "C", "D"], "confidence": 0.497222, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'multiple_correct_answers']; agreement=1/2; mean_stage_confidence=0.994.", "evidence_votes": ["none", "multiple_correct_answers"], "evidence_agreement": 0.5, "valid_evidence_stages": 2, "blind_solution": {"solution_status": "uncertain", "valid_answers": ["A", "...`
- `llm_audit_failure` / `evaluator` / `llm_gold_audit` / `review` / unknown (confidence=1.00)
  - llm_gold_audit failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_gold_audit", "error": "structured gold evidence stages failed: defender"}`
- `llm_audit_failure` / `evaluator` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - llm_option_set failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_option_set", "error": "LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 0, 'reasoning_chars': 19585}"}`

### `mmlu-redux-global_facts-13` (row_uid=`source-row-00000382`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.627778, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.628.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "so...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['C']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["$14,900"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["PPP-adjusted and inflation-controlled dat...`

### `mmlu-redux-global_facts-70` (row_uid=`source-row-00000385`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.90)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "False: many Sub-Saharan nations have grown."}, {"label": "B", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.8, "rationale": "Likely true: DRC's economy has declined since 1980."}, {"label": "C", "literal_truth": "true", "best_ans...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": ["The task is incomplete; the question is truncated and cannot be answered."], "claims": [{"claim": "The provided task is a fragm...`

### `mmlu-redux-college_chemistry-86` (row_uid=`source-row-00000387`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.630864, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.946.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", ...`

### `mmlu-redux-virology-7` (row_uid=`source-row-00000389`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": true, "assumptions_used": [], "missing_information": ["Background information about the Multicenter AIDS Cohort (MACS) study, such as its design, challenges, and what factors contributed to its success."], "alternative_interpretations": [{"interpretation": "If participant commitment is emphasized in MACS literature", "answer": "The commitment of the participants"}, {"interpretation": "If staff dedication is h...`

### `mmlu-redux-virology-14` (row_uid=`source-row-00000390`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.54)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.54321, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.815.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_ans...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=1.00)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["Definition of 'infected': chronic active infection or ever infected?"], "alternative_interpretations": [{"interpretation": "'Currently infected' means chronic HBV infection (HBsAg positive)", "answer": "350 million"}, {"interpretation": "'Currently infected' means ever infected (any serological evidence)", "answer": "2 billion"}], "rationale": ...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["approximately 254 million people"], "confidence": 0.9, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The question refers to chronic hepatitis B infection, which is the standard metric repor...`

### `mmlu-redux-professional_accounting-4` (row_uid=`source-row-00000392`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.98)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.97963, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.980.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none"...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.80)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.8, "needs_expert": false, "assumptions_used": ["Gordon Growth Model applies", "expected return is discount rate"], "missing_information": ["whether the $3 dividend is the most recent (D0) or the next expected (D1)"], "alternative_interpretations": [{"interpretation": "The $3 is the next dividend (D1)", "answer": "8%"}, {"interpretation": "The $3 is the last paid dividend (D0)", "answer": "≈7.69%, not exactly matching ...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "0% gives price 25, not 75."}, {"label": "B", "literal_truth": "false", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "8% gives price 81, not 75, but is closest to exact 7.69%."}, {"label": "C", "literal_truth": "false", "best_answer_status": "i...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["7.69%"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The Gordon Growth Model (dividend discount m...`

### `mmlu-redux-high_school_psychology-35` (row_uid=`source-row-00000393`)

- `source_reference_missing` / `context_attachment` / `task_integrity_rule` / `review` / unknown (confidence=0.80)
  - The task depends on an unnamed study/report and provides no source context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Identify the study/report, publication date, or source artifact.
  - Evidence: `{"matched_phrase": "recent comparison", "task_excerpt": "A recent comparison of the intelligence scores of Asian Americans and African Americans on the Stanford-Binet showed that"}`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The content of statements I, II, and III is not provided."], "alternative_interpretations": [], "rationale": "The task lists choices as 'I only', 'II only', etc., but does not specify what I, II, and III refer to. Without these statements, the question cannot be answered."}, "gold": "D", "choices": ["I only", "II only", "III only", "I, II, and III"], "ll...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=uncertain.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "Option refers to Statement I which is not provided; question stem incomplete."}, {"label": "B", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "Option refers to Statement II which is not provided; question s...`

### `mmlu-redux-college_chemistry-82` (row_uid=`source-row-00000394`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.48)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.484722, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'wrong_gold_answer']; agreement=1/2; mean_stage_confidence=0.969.", "evidence_votes": ["no_correct_answer", "wrong_gold_answer"], "evidence_agreement": 0.5, "valid_evidence_stages": 2, "blind_solution": {"solution_status": "none", "valid_answers": [], "equivalent_ans...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.99)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9888888888888889, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["Polarization is defined as the equilibrium magnetic dipole moment per particle, i.e., μ tanh(μB/kT)"], "claims": [{"claim": "Equilibrium polarization for a spin-1/2 particle is μ tanh(μB/k...`
- `llm_audit_failure` / `evaluator` / `llm_gold_audit` / `review` / unknown (confidence=1.00)
  - llm_gold_audit failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_gold_audit", "error": "structured gold evidence stages failed: defender"}`
- `llm_audit_failure` / `evaluator` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - llm_option_set failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_option_set", "error": "LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 0, 'reasoning_chars': 16738}"}`

### `mmlu-redux-conceptual_physics-73` (row_uid=`source-row-00000396`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": false, "assumptions_used": ["Standard physics knowledge that constructive interference yields amplitude equal to sum, not greater"], "missing_information": [], "alternative_interpretations": [{"interpretation": "\"More than the sum\" is taken literally as incorrect for interference, so only \"cancel completely\" is correct.", "answer": "cancel completely"}, {"interpretation": "\"More than the sum\" ...`

### `mmlu-redux-virology-76` (row_uid=`source-row-00000401`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.66)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.661728, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.993.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Humans are not natural reservoirs for either virus."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Primates are incidental hosts, not natural reservoirs."}, {"label": "C", "literal_truth": "fals...`

### `mmlu-redux-machine_learning-29` (row_uid=`source-row-00000404`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.94)
  - Independent option checks found multiple choices that satisfy the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"option_evidence": {"solution_status": "multiple", "valid_answers": ["B", "D"], "equivalent_answers": ["D"], "independently_acceptable_answers": ["B"], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9444444444444444, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "MLE can overfit with small samples.", "evidence_type": "definition", "support": "Maximum likelihood estimation maximizes fit to observed data, leading to ...`

### `mmlu-redux-human_aging-98` (row_uid=`source-row-00000405`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.80)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.8, "needs_expert": true, "assumptions_used": [], "missing_information": ["The population and geographic region are unspecified", "The time period or study source is not provided", "The specific condition or characteristic is not defined"], "alternative_interpretations": [{"interpretation": "Population in Oregon or other legal jurisdictions; most have clinical depression", "answer": "Clinical depression"}, {"interpretation": "Po...`

### `mmlu-redux-virology-34` (row_uid=`source-row-00000406`)

- `source_reference_missing` / `context_attachment` / `task_integrity_rule` / `review` / unknown (confidence=0.80)
  - The task depends on an unnamed study/report and provides no source context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Identify the study/report, publication date, or source artifact.
  - Evidence: `{"matched_phrase": "a study", "task_excerpt": "In a study, a group of people are exposed to an environmental toxin but are not treated observed over time on a standard set of measures to ascertain the potential effects of the toxin. This type of study design is called"}`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "No intervention, so not a clinical trial."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "No mention of blinding; it's a design feature not a study type."}, {"label": "C", "literal_truth": "true"...`

### `mmlu-redux-formal_logic-80` (row_uid=`source-row-00000411`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Correctly translates 'Abdul is Egyptian and Cleopatra is Egyptian'."}, {"label": "B", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "unclear", "equivalence_group": null, "confidence": 1.0, "rationale": "Ill-formed: 'c' is a constant used as a proposition."}, {"label": "C", "literal_truth...`

### `mmlu-redux-high_school_chemistry-26` (row_uid=`source-row-00000414`)

- `llm_audit_failure` / `evaluator` / `llm_gold_audit` / `review` / unknown (confidence=1.00)
  - llm_gold_audit failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_gold_audit", "error": "blind_solver: LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 86, 'reasoning_chars': 23284}"}`

### `mmlu-redux-logical_fallacies-59` (row_uid=`source-row-00000416`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.59)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.587654, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.881.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "val...`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": true, "assumptions_used": [], "missing_information": ["Definition or standard classification of 'laudatory personality' as a logical fallacy"], "alternative_interpretations": [{"interpretation": "If laudatory personality refers to praise-based argument, it might be a subtype of ad hominem, but that is not among choices.", "answer": null}], "rationale": "The term 'laudatory personality' is not a standard falla...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.70)
  - Option set auditor reported bad_options_clarity with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 0.8, "rationale": "No known relation; question unclear."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 0.8, "rationale": "No known relation; question unclear."}, {"label": "C", "literal_truth": "false", "best_answer_status": "ir...`

### `mmlu-redux-human_aging-34` (row_uid=`source-row-00000417`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["Definition of 'grieving individuals'", "Source or study for the statistic", "Timeframe or population"], "alternative_interpretations": [{"interpretation": "Interpretation depends on unstated source", "answer": "Varies"}], "rationale": "The task asks for a percentage of grieving individuals needing professional help without providing any context (e.g., s...`

### `mmlu-redux-professional_accounting-97` (row_uid=`source-row-00000419`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=1.00)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Skinner contributed $5,000 cash", "evidence_type": "task_text", "support": "Explicitly stated in task."}, {"claim": "Skinner contributed land with adjusted basis of $12,000", "evidence_ty...`

### `mmlu-redux-high_school_us_history-27` (row_uid=`source-row-00000422`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": false, "assumptions_used": [], "missing_information": ["Connection between the provided quote and the problems in Federalist #15"], "alternative_interpretations": [{"interpretation": "Ignore the quote and answer based on historical knowledge of Federalist #15", "answer": "adopting a new constitution in order to create a more national government."}, {"interpretation": "Use the quote to infer problems about rac...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Not proposed in Federalist #15; Hamilton focused on domestic governance."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Correctly identifies Hamilton's proposal for a new constitution to strengthen nationa...`

### `mmlu-redux-econometrics-58` (row_uid=`source-row-00000423`)

- `missing_condition` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.70)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.7, "needs_expert": false, "assumptions_used": ["Standard econometric results for OLS with lagged dependent variables assume no serial correlation of errors unless specified."], "missing_information": ["The condition of the error term (whether it is serially correlated or not) is not specified."], "alternative_interpretations": [{"interpretation": "Assuming no autocorrelation in errors: standard OLS result", "answer": "Biased ...`

### `mmlu-redux-anatomy-70` (row_uid=`source-row-00000425`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.95)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9500000000000001, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "During an inferior alveolar nerve block, the needle ideally passes lateral to the medial pterygoid muscle and medial to the ramus of the mandible.", "evidence_type": "exter...`

### `mmlu-redux-philosophy-96` (row_uid=`source-row-00000426`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.97)
  - Independent option checks found multiple choices that satisfy the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"option_evidence": {"solution_status": "multiple", "valid_answers": ["B", "D"], "equivalent_answers": [], "independently_acceptable_answers": ["B", "D"], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9722222222222222, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Cleanthes uses the watchmaker analogy to argue for design in nature.", "evidence_type": "external_source", "support": "In Hume's Dialogues, Cleanthes ar...`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["Context of the philosophical dialogue, including the specific analogy used by Cleanthes and Philo's response"], "alternative_interpretations": [], "rationale": "The task asks for Philo's opinion of Cleanthes' analogy without providing any context from the dialogue. The intended answer is a specific fact from the text, making it unsolvable without extern...`

### `mmlu-redux-global_facts-67` (row_uid=`source-row-00000428`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.81)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.811111, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.811.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none"...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["2400 US dollars (2011 PPP)"], "confidence": 0.6, "needs_expert": true, "assumption_risk": "conventional", "required_assumptions": ["GDP per capita in 1850 in 2011 PPP dollars is approximately $2,400 based on Maddison Project es...`

### `mmlu-redux-virology-87` (row_uid=`source-row-00000430`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.94)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.935185, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.935.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-professional_psychology-6` (row_uid=`source-row-00000432`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.95)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "corrupted", "equivalence_group": null, "confidence": 0.95, "rationale": "Contains typo 'char' and narrows ethnic identity to non-Western, which is inaccurate."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Limits ethnic identity to minority communities, excluding m...`

### `mmlu-redux-high_school_statistics-29` (row_uid=`source-row-00000433`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The two possible wordings of the questionnaire are not provided in the task statement."], "alternative_interpretations": [], "rationale": "The task statement is truncated; it only says 'Two possible wordings... are as follows:' but the actual wordings are missing. Without them, the question cannot be answered."}, "gold": "D", "choices": ["The first showe...`

### `mmlu-redux-prehistory-7` (row_uid=`source-row-00000435`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.57)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.574074, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.861.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Neolithic Revolution", "10,000"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The revolution referred to is the Neolithic (Agricultural) Revolution, not the Green Revo...`

### `mmlu-redux-virology-41` (row_uid=`source-row-00000441`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.61)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["B", "D"], "confidence": 0.607407, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.911.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solu...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.95)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "NGS can aid vaccine development but it's not the primary use; it's a secondary benefit."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Identifying genetic variation is a core and primary application of NGS...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Identifying and characterizing viral pathogens, including novel viruses, and tracking mutations/viral evolution."], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"...`

### `mmlu-redux-virology-74` (row_uid=`source-row-00000450`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-professional_law-45` (row_uid=`source-row-00000452`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.93)
  - Independent option checks found multiple choices that satisfy the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"option_evidence": {"solution_status": "multiple", "valid_answers": ["C", "D"], "equivalent_answers": [], "independently_acceptable_answers": ["C", "D"], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9277777777777777, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["standard US evidence rules apply"], "claims": [{"claim": "The teller's testimony is based on her personal observation of the check.", "evidence_type": "task_text", "sup...`

### `mmlu-redux-virology-99` (row_uid=`source-row-00000453`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["A", "B", "D"], "confidence": 0.641975, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'multiple_correct_answers', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.963.", "evidence_votes": ["multiple_correct_answers", "multiple_correct_answers", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_e...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "True: single drugs often fail to suppress HIV fully."}, {"label": "B", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "True: mutations can negate one drug's effect."}, {"label": "C", "literal_truth": "false", "best_...`

### `mmlu-redux-professional_accounting-36` (row_uid=`source-row-00000457`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.644444, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.967.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["$241,842"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "NPV is calculated as present value of future cash flows minus initial investment.", "evidence_ty...`

### `mmlu-redux-business_ethics-21` (row_uid=`source-row-00000461`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.45)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.451852, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.678.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "val...`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The actual question or prompt is missing. The task only states 'Cultural homogenization.' without any further context or instruction."], "alternative_interpretations": [], "rationale": "The task only states 'Cultural homogenization.' with no further question or context. The choices are lists of numbers, but without a prompt, the intended answer is unknow...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "uncertain", "derived_answers": ["Cultural homogenization is the process by which local or regional cultures become increasingly similar due to globalization, media, and multinational corporate influence, often leading to the loss of cultural diversity."], "...`

### `mmlu-redux-formal_logic-17` (row_uid=`source-row-00000463`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=1.00)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "~B means Izzy does not play Minecraft", "evidence_type": "definition", "support": "Given key assigns B to Izzy plays Minecraft, so ~B is negation."}, {"claim": "• is conjunction", "eviden...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Translates to ~(B & E) ⊃ D, not (~B & E) ⊃ D."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "unclear", "equivalence_group": null, "confidence": 0.9, "rationale": "Ambiguous phrasing but intended as (~B & E) ⊃ D, matching the formula."}, {"label": "C", "literal_truth": ...`

### `mmlu-redux-public_relations-4` (row_uid=`source-row-00000464`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.61)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.60716, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.911.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "vali...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['C']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["outcomes stage"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Macnamara's pyramid...`

### `mmlu-redux-human_aging-70` (row_uid=`source-row-00000471`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.62)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.617284, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.926.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", ...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.90)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Young survivors are at higher risk."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Lack of prior depression is protective."}, {"label": "C", "literal_truth": "uncertain", "best_answer_status": "weaker", ...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["have a history of depression"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The question refers to bereavement and depression risk factors."], "claims": [{"claim": "A ...`

### `mmlu-redux-elementary_mathematics-64` (row_uid=`source-row-00000478`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Missing 'nine hundred'; represents 179,012."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 1.0, "rationale": "Nonstandard phrasing 'seventy-nine nine hundred'; unclear."}, {"label": "C", "literal_truth": "false"...`

### `mmlu-redux-econometrics-94` (row_uid=`source-row-00000481`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["Equation 16 is not provided, so the roles of coefficients a, b, c, d are unknown."], "alternative_interpretations": [{"interpretation": "Assuming bi-directional feedback means both sets of coefficients are significant", "answer": "A or B depending on definition"}, {"interpretation": "Assuming standard textbook interpretation", "answer": "Uncertain withou...`

### `mmlu-redux-electrical_engineering-95` (row_uid=`source-row-00000483`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.99)
  - Independent option checks found multiple choices that satisfy the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"option_evidence": {"solution_status": "multiple", "valid_answers": ["A", "B", "C", "D"], "equivalent_answers": [], "independently_acceptable_answers": ["A", "B", "C", "D"], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9944444444444444, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Oscillators use positive feedback to sustain oscillations.", "evidence_type": "definition", "support": "Standard oscillator theory: ...`

### `mmlu-redux-high_school_geography-89` (row_uid=`source-row-00000486`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": false, "assumptions_used": [], "missing_information": ["Definition of 'most rapidly growing' (percentage vs absolute growth)", "Time frame for 'today'"], "alternative_interpretations": [{"interpretation": "Highest percentage growth rate", "answer": "Islam"}, {"interpretation": "Largest absolute increase in adherents", "answer": "Christianity"}], "rationale": "The phrase 'most rapidly growing' is amb...`

### `mmlu-redux-virology-25` (row_uid=`source-row-00000493`)

- `source_reference_missing` / `context_attachment` / `task_integrity_rule` / `review` / unknown (confidence=0.80)
  - The task depends on an unnamed study/report and provides no source context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Identify the study/report, publication date, or source artifact.
  - Evidence: `{"matched_phrase": "the study", "task_excerpt": "500 women aged 40 – 54 who present for routine check-ups are asked about their meat consumption the women turn out to be vegetarian. During the ensuing 5 years, 5 vegetarians and 43 non-vegetarians develop colorectal cancer. Which of the following best describes the study design?"}`
- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.97)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.966667, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.967.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-nutrition-91` (row_uid=`source-row-00000495`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.96)
  - Independent option checks found multiple choices that satisfy the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"option_evidence": {"solution_status": "multiple", "valid_answers": ["A", "B", "C", "D"], "equivalent_answers": [], "independently_acceptable_answers": ["A", "B", "C", "D"], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9611111111111111, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Rickets of prematurity is associated with vitamin D deficiency", "evidence_type": "external_source", "support": "Standard medical kn...`

### `mmlu-redux-college_biology-90` (row_uid=`source-row-00000498`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.638272, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.957.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", ...`

### `mmlu-redux-international_law-73` (row_uid=`source-row-00000502`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.58)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.581481, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'uncertain', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.872.", "evidence_votes": ["wrong_gold_answer", "uncertain", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "sol...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['B'] conflicts with option best_answers=['C']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["The European Court of Human Rights held that there was no violation of Article 6(1) (right to a fair trial) of the European Convention on Human Rights, find...`

### `mmlu-redux-formal_logic-28` (row_uid=`source-row-00000503`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `major` / review (confidence=1.00)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "v...`
- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The choices lack a predicate for 'has a major' (e.g., Mx), which is essential to translate the sentence."], "alternative_interpretations": [], "rationale": "The sentence 'No senior graduates without a major' requires a predicate for 'major' but none of the choices include one. This makes the task unsolvable as none of the options correctly capture the...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Translates to 'All seniors do not graduate', ignoring the 'without a major' condition."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Translates to 'Not all seniors graduate', which is not equiv...`

### `mmlu-redux-virology-39` (row_uid=`source-row-00000504`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.59)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["A", "B", "C", "D"], "confidence": 0.590123, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.885.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "b...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": true, "assumptions_used": [], "missing_information": ["Which populations PreP is proven effective for in reducing HIV incidence"], "alternative_interpretations": [{"interpretation": "PreP is effective for women and drug users but not pregnant women", "answer": "a. and b. above"}, {"interpretation": "PreP is effective for women only", "answer": "Women"}, {"interpretation": "PreP is effective for drug...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.95)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "PreP is effective for women at high risk."}, {"label": "B", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "PreP is effective for drug users."}, {"label": "C", "literal_truth": "true", "best_answer_status": "accep...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["high-risk populations, particularly men who have sex with men, serodiscordant couples, and people who inject drugs"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [...`

### `mmlu-redux-astronomy-0` (row_uid=`source-row-00000505`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The question does not provide any background about the Mars Exploration Rover Spirit's mission status, location, or mechanical condition. The intended answer depends on factual knowledge about Spirit's actual tilt reason, which is not given in the task."], "alternative_interpretations": [{"interpretation": "Each choice could be a plausible explanation f...`

### `mmlu-redux-global_facts-14` (row_uid=`source-row-00000507`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The actual percentage of children in Vietnam (age 8) who reported physical punishment by teachers in the past week in 2009 is not provided in the task."], "alternative_interpretations": [], "rationale": "The task asks for a specific statistic but provides no data or source. Without the contextual information, the answer cannot be determined from the giv...`

### `mmlu-redux-virology-89` (row_uid=`source-row-00000512`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.95)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Administered within 4 days is generally not recommended; antivirals are most effective within 48 hours."}, {"label": "B", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Common guideline for therapeutic antiviral u...`

### `mmlu-redux-logical_fallacies-52` (row_uid=`source-row-00000514`)

- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The task does not include an explicit question or instruction; it only provides a quote and answer choices. The intended task (e.g., 'Identify the logical fallacy') is missing."], "alternative_interpretations": [], "rationale": "The task presents a quote and multiple-choice options but lacks any question or directive. Without knowing what to do with t...`

### `mmlu-redux-management-10` (row_uid=`source-row-00000515`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.47)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.47284, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.709.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "vali...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": false, "assumptions_used": [], "missing_information": ["Theoretical framework or context (e.g., Porter's generic strategies, marketing mix)"], "alternative_interpretations": [{"interpretation": "Advertising as a form of differentiation strategy (common in Porter's framework)", "answer": "Differentiation"}, {"interpretation": "Advertising as a component of a focusing strategy (targeting a niche)", "a...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": ["promotion"], "confidence": 0.8, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["advertising is considered part of the promotional mix in marketing"], "claims": [{"claim": "Advertising is a...`

### `mmlu-redux-professional_psychology-81` (row_uid=`source-row-00000516`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.56)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.562963, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.844.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['A'] conflicts with option best_answers=['C']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["violating the ethical prohibition against romantic or sexual relationships with students"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "n...`

### `mmlu-redux-college_chemistry-78` (row_uid=`source-row-00000517`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-global_facts-48` (row_uid=`source-row-00000518`)

- `presentation_corruption` / `expected_output` / `task_integrity_rule` / `review` / unknown (confidence=0.92)
  - Visible encoding or formatting corruption was detected.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Restore the original text/choice formatting and prevent lossy conversion.
  - Evidence: `{"signals": ["encoding_corruption"], "text_excerpt": "As of 2015, about what percentage of the world�s land area is forested?\n15% 30% 45% 60%"}`

### `mmlu-redux-global_facts-1` (row_uid=`source-row-00000519`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": false, "assumptions_used": [], "missing_information": ["No specific data source or time period is provided for the approval ratings.", "Unclear which direction of difference is asked (South minus rest or rest minus South).", "Unclear whether 'peak' refers to maximum absolute difference or maximum approval overall."], "alternative_interpretations": [{"interpretation": "Difference as absolute value at peak, aro...`

### `mmlu-redux-human_sexuality-99` (row_uid=`source-row-00000525`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `major` / review (confidence=0.98)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.977778, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.978.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.95)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "High levels of prostaglandin cause cramps, not low."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Increased oxygen supply is not a known cause."}, {"label": "C", "literal_truth": "false", "best_ans...`

### `mmlu-redux-high_school_macroeconomics-16` (row_uid=`source-row-00000526`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.59)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.590123, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.885.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `llm_audit_failure` / `evaluator` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - llm_option_set failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_option_set", "error": "LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 250, 'reasoning_chars': 21806}"}`

### `mmlu-redux-human_sexuality-16` (row_uid=`source-row-00000528`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": true, "assumptions_used": [], "missing_information": ["No empirical basis or theoretical framework is provided to determine what persons with liberal attitudes about premarital sex are likely to do regarding extramarital sex or swinging."], "alternative_interpretations": [{"interpretation": "Interpret the question as asking for a statistical correlation based on common social science findings.", "answer": "Un...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.70)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.7, "rationale": "Plausible correlation but not universally true."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.8, "rationale": "Not necessarily implied by liberal premarital attitudes."}, {"label": "C", "literal_truth": "false", "bes...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": false, "assumption_risk": "answer_changing", "required_assumptions": ["The answer choices are not provided, making any specific answer speculative."], "claims": [{"claim": "The question is ambiguous without the list of answe...`

### `mmlu-redux-high_school_european_history-76` (row_uid=`source-row-00000529`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.58)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.581481, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.872.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["philosophical optimism"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The phrase 'concatenation of universal events' is used by Pangloss to describe the...`

### `mmlu-redux-formal_logic-60` (row_uid=`source-row-00000534`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.67)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["B", "C"], "confidence": 0.666667, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=1.000.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solu...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Translates as (~A ∧ ~B) ⊃ C, not equivalent to given formula."}, {"label": "B", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": "eq1", "confidence": 1.0, "rationale": "Translates as ~(A ∧ B) ⊃ C, equivalent to (~A ∨ ~B) ⊃ C."}, {"label": "C", "literal_t...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["If either Marina does not read a Percy Jackson book or Izzy does not play Minecraft, then Emily stops working."], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"cla...`

### `mmlu-redux-virology-97` (row_uid=`source-row-00000537`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": false, "assumptions_used": ["Both MERS and SARS are considered emergent coronaviruses", "Both caused thousands of deaths globally"], "missing_information": ["Specific criterion to distinguish between MERS and SARS (e.g., which is more recently emergent or higher death toll)"], "alternative_interpretations": [{"interpretation": "SARS (2003 outbreak) is the emergent virus that caused thousands of deat...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.70)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=uncertain, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.7, "rationale": "MERS emerged in 2012 causing outbreaks with significant deaths, though actual count is under 1000."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.7, "rationale": "SARS emerged in 2002 causing global outb...`

### `mmlu-redux-college_physics-72` (row_uid=`source-row-00000539`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.99)
  - Independent option checks found multiple choices that satisfy the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"option_evidence": {"solution_status": "multiple", "valid_answers": ["B", "D"], "equivalent_answers": ["B"], "independently_acceptable_answers": ["D"], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9888888888888889, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Boron is a group III element with three valence electrons.", "evidence_type": "definition", "support": "Boron is in group 13 of the periodic table, thus h...`

### `mmlu-redux-virology-5` (row_uid=`source-row-00000540`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.95, "needs_expert": false, "assumptions_used": ["The third choice is incomplete and likely meant to include 'Native Americans'."], "missing_information": ["The third option is truncated; it ends with 'and' without completing the comparison."], "alternative_interpretations": [{"interpretation": "Assuming the third option is 'Higher than in all other ethnic groups except African-Americans and Native Americans'", "answer...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Incorrect: African-Americans have higher prevalence."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Correct: Latinos have higher prevalence than whites/Asians but lower than African-Americans."}, {"lab...`

### `mmlu-redux-college_chemistry-81` (row_uid=`source-row-00000541`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.625926, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.626.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['C'] conflicts with option best_answers=['B']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["T1 is longer than T2 because T1 relaxation involves energy transfer to the lattice, a slower process compared to the spin-spin interactions and magnetic field inhomogeneities that cause T2 relaxation."], "confidence": 0.9, "needs_expert": false, ...`

### `mmlu-redux-high_school_world_history-87` (row_uid=`source-row-00000544`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.95)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.95, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.950.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solve...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Persian persecution would not inspire followers; historically false."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "No evidence for Buddhism's apocalyptic message swaying Persian converts."}, {"labe...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["The presence of Buddhist communities within Sassanid Persia is best explained by the extensive trade networks, particularly the Silk Road, which facilitated cultural and religious exchanges between India, Central Asia, and Persia, as well as the earlier influence ...`

### `mmlu-redux-college_chemistry-0` (row_uid=`source-row-00000546`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.62716, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.941.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "vali...`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.70)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.7, "needs_expert": false, "assumptions_used": [], "missing_information": ["The physical context for 'allowed energy levels' (e.g., nuclear Zeeman splitting, shell model energy levels)", "The nuclear spin of 55Mn if Zeeman splitting is intended"], "alternative_interpretations": [{"interpretation": "Number of nuclear spin states in a magnetic field (Zeeman splitting)", "answer": "6 (2I+1 for I=5/2)"}, {"interpretation": "Number o...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Not literally true; 55Mn has 6 allowed energy levels."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Not literally true; 55Mn has 6 allowed energy levels."}, {"label": "C", "literal_truth": "fal...`

### `mmlu-redux-human_aging-15` (row_uid=`source-row-00000547`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The specific research findings or interviewee statements that describe the nature of memory."], "alternative_interpretations": [], "rationale": "The task lacks any context or source material about the research and interviewees, making it impossible to determine which choice is correct. The question cannot be answered without the referenced information."}...`

### `mmlu-redux-electrical_engineering-30` (row_uid=`source-row-00000552`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.98)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.977778, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.978.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-professional_accounting-62` (row_uid=`source-row-00000554`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.630864, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.946.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "va...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The task is incomplete; no question or choices provided.", "evidence_type": "task_text", "support": "Th...`

### `mmlu-redux-high_school_european_history-67` (row_uid=`source-row-00000555`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.634568, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.952.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "val...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.70)
  - Option set auditor reported bad_options_clarity with literal_cardinality=none, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Not mentioned in excerpt."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.6, "rationale": "Excerpt praises Napoleon's knowledge of politics, but does not explicitly mention domestic reforms."}, {"label": "C", "lite...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": ["Napoleon's intellectual genius and profound thoughts on morals, politics, and religion"], "confidence": 0.6, "needs_expert": false, "assumption_risk": "answer_changing", "required_assumptions": ["The question expects a featu...`

### `mmlu-redux-virology-43` (row_uid=`source-row-00000556`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.60)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.6, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.900.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "valid_an...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.80)
  - Option set auditor reported no_correct_answer with literal_cardinality=uncertain, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.3, "rationale": "Sexual transmission of arenaviruses is not well-documented; uncertain if it occurs."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.3, "rationale": "Blood transmission is possible but not primary; uncertain as a ...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Arenaviruses are spread through contact with infected rodents or their excreta (urine, feces, saliva), and via aerosolized particles."], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Arenavir...`

### `mmlu-redux-college_chemistry-84` (row_uid=`source-row-00000558`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.641975, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.963.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", ...`

### `mmlu-redux-college_chemistry-91` (row_uid=`source-row-00000562`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-logical_fallacies-71` (row_uid=`source-row-00000567`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=1.00)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The described fallacy is the ad hominem fallacy.", "evidence_type": "definition", "support": "Ad hominem is a fallacy that attacks the person making an argument rather than the argument i...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.85)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 0.9, "rationale": "Not a standard fallacy name; does not match description."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Guilt by association is a standard fallacy but does not fit."}, {"label": "C", "literal...`

### `mmlu-redux-virology-82` (row_uid=`source-row-00000568`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `major` / review (confidence=0.96)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.955556, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.956.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none...`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": true, "assumptions_used": [], "missing_information": ["The specific time reference for 'at present' is not provided", "The date of dataset creation is needed to determine the known number of human polyomaviruses at that time"], "alternative_interpretations": [{"interpretation": "Assuming the present refers to the time when the dataset was created (around 2020-2021), the number of known human polyomaviruses is...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.95)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "No known human polyomavirus count is 100."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "There are more than 1 human polyomavirus."}, {"label": "C", "literal_truth": "false", "best_answer_status...`

### `mmlu-redux-logical_fallacies-97` (row_uid=`source-row-00000569`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.98)
  - Independent option checks found multiple choices that satisfy the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"option_evidence": {"solution_status": "multiple", "valid_answers": ["B", "D"], "equivalent_answers": ["D"], "independently_acceptable_answers": ["B"], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9777777777777779, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The argument assumes its conclusion in the premise.", "evidence_type": "task_text", "support": "The statement concludes that he is a Communist based on hi...`

### `mmlu-redux-logical_fallacies-42` (row_uid=`source-row-00000572`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.50)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.5, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.500.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "v...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["loaded question"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Complex question fallacy is also known as loaded question.", "evidence_type": "definitio...`

### `mmlu-redux-global_facts-18` (row_uid=`source-row-00000575`)

- `presentation_corruption` / `expected_output` / `task_integrity_rule` / `review` / unknown (confidence=0.92)
  - Visible encoding or formatting corruption was detected.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Restore the original text/choice formatting and prevent lossy conversion.
  - Evidence: `{"signals": ["encoding_corruption"], "text_excerpt": "Consider the following statements: (1) In every country, people think other individuals in their country are less happy than they actually are. (2) In the United States, women�s happiness has increased both absolutely and relative to men. Which of these statements is True/False?\nTrue, True True, False False, True False, False"}`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.60)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.3, "rationale": "Uncertain truth values for both statements; likely not correct."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.5, "rationale": "Gold answer; but statement 1 may be false."}, {"label": "C", "literal_truth": "uncert...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['B']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "uncertain", "derived_answers": ["Statement 1 is likely false (universal claim about all countries is unsupported); Statement 2 is likely false (women's relative happiness in US has not increased relative to men)"], "confidence": 0.3, "needs_expert": true, "assumption_risk": "...`

### `mmlu-redux-high_school_macroeconomics-25` (row_uid=`source-row-00000577`)

- `duplicate_choices` / `oracle_ground_truth` / `static_rule` / `review` / review (confidence=0.75)
  - Two or more choices normalize to the same text.
  - Evidence: `deterministic_rule` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Deduplicate choices unless duplicates are intentional distractors that do not affect the gold answer.
  - Evidence: `{"duplicates": [[0, 3, "Increase     Increase"]], "choices": ["Increase     Increase", "No change     No change", "Increase     No change", "Increase     Increase"]}`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.62)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["A", "D"], "confidence": 0.616049, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.924.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solut...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": false, "assumptions_used": [], "missing_information": ["The choices list contains duplicate entries for 'Increase     Increase', making it unclear which one is the intended correct answer."], "alternative_interpretations": [{"interpretation": "The first 'Increase     Increase' option is intended as correct.", "answer": "Increase     Increase (first)"}, {"interpretation": "The last 'Increase     Incr...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": "1", "confidence": 1.0, "rationale": "Literally true; identical to gold."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Incorrect; both consumption and AD increase."}, {"label": "C", "literal_truth": "false", "best_answer_status": "irreleva...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Consumption function shifts upward; aggregate demand increases (rightward shift)."], "confidence": 0.95, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["Standard macroeconomic wealth effect: ...`

### `mmlu-redux-security_studies-3` (row_uid=`source-row-00000579`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": false, "assumptions_used": ["TNC is assumed to refer to transnational crime based on choices."], "missing_information": ["The acronym TNC is not defined in the task statement."], "alternative_interpretations": [{"interpretation": "TNC as transnational corporation", "answer": "None of the provided choices would apply."}], "rationale": "The task does not define the acronym 'TNC', which could stand for 'transnat...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.95)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 0.9, "rationale": "Contradictory wording and not a standard definition."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Correctly highlights profit-driven crime and subversion of legal economy as new aspects of TNC."}, ...`

### `mmlu-redux-sociology-0` (row_uid=`source-row-00000583`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.60)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "unclear", "equivalence_group": null, "confidence": 0.6, "rationale": "Vague claim about drug use patterns; literal truth uncertain without expert knowledge."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Ecstasy is not the most commonly used recreational drug; cannab...`

### `mmlu-redux-professional_psychology-75` (row_uid=`source-row-00000587`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-professional_accounting-33` (row_uid=`source-row-00000588`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": true, "assumptions_used": [], "missing_information": ["Which balance sheets are being considered for separate reporting? The phrase 'Strut's Plane's consolidated balance sheet balance sheet' is garbled and does not clearly enumerate the balance sheets."], "alternative_interpretations": [{"interpretation": "The question asks whether the payable should be reported separately on Strut's balance sheet a...`

### `mmlu-redux-virology-88` (row_uid=`source-row-00000591`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-formal_logic-55` (row_uid=`source-row-00000598`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.67)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["C", "D"], "confidence": 0.666667, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=1.000.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solu...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Argument is invalid, so 'Valid' is false."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "With E, F, G true, premise2 is false, so not a counterexample."}, {"label": "C", "literal_truth": "true",...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Invalid. Counterexample: E = true, F = true, G = false."], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The conclusion ~(E ≡ F) is false when E and F hav...`

### `mmlu-redux-high_school_chemistry-31` (row_uid=`source-row-00000599`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.56)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.562963, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.844.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["a solution that obeys Raoult's law exactly over all temperature and pressure ranges, with zero enthalpy of mixing and zero volume change upon mixing"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "requi...`

### `mmlu-redux-abstract_algebra-87` (row_uid=`source-row-00000601`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.67)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.666667, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.667.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-college_medicine-9` (row_uid=`source-row-00000602`)

- `missing_context` / `context_attachment` / `static_rule` / `major` / unknown (confidence=0.85)
  - Task references passage, but no matching context artifact was found.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the referenced passage or remove the reference.
  - Evidence: `{"reference_type": "passage", "task_excerpt": "Sauna use, sometimes referred to as \"sauna bathing,\" is characterized by short-term passive exposure to extreme heat. This exposure elicits mild hyperthermia – an increase in the body's core temperature – that induces a thermoregulatory res"}`

### `mmlu-redux-high_school_european_history-71` (row_uid=`source-row-00000606`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.61)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.612346, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.919.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", ...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=multiple, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Directly related to Enlightenment ideas of rights and toleration from Locke and Rousseau."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Possible indirect influence but not the most direct."}, {"label"...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["the Enlightenment and the French Revolution's secular reforms"], "confidence": 0.7, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["Paine was influenced by Enlightenment ideas and the French Revolution"], "claims": [{"claim": "P...`

### `mmlu-redux-professional_accounting-39` (row_uid=`source-row-00000612`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.60)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.597531, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.896.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["13.245%"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Portfolio variance = w_A^2 σ_A^2 + w_B^2 σ_B^2 + 2 w_A w_B ρ σ_A σ_B", "evidence_type": "definiti...`

### `mmlu-redux-college_chemistry-19` (row_uid=`source-row-00000615`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-college_chemistry-79` (row_uid=`source-row-00000619`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.97)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.968519, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.969.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-professional_medicine-67` (row_uid=`source-row-00000621`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.61)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.61358, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.920.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "vali...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['A']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Obtain consent from a parent or legal guardian for evaluation of the minor patient."], "confidence": 0.85, "needs_expert": false, "assumption_risk": "conven...`

### `mmlu-redux-high_school_biology-0` (row_uid=`source-row-00000624`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 0.9, "rationale": "False statement; water moves from high to low potential. Wording is redundant and ambiguous."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "False; pressure potential also contributes."}, {"lab...`

### `mmlu-redux-security_studies-54` (row_uid=`source-row-00000625`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.57)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.57037, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.856.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_ans...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Biological factors such as physical strength differences, reproductive health needs, and caregiving roles can have pragmatic implications for post-conflict gender security. These include increased vulnerability of women to viol...`

### `mmlu-redux-miscellaneous-84` (row_uid=`source-row-00000626`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The specific children's game being referred to."], "alternative_interpretations": [{"interpretation": "Rover might be a character in an unspecified game; color could be any of the options depending on the game.", "answer": "No single answer determinable."}], "rationale": "The question does not name the children's game, so 'Rover' could refer to different...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "unclear", "equivalence_group": null, "confidence": 0.7, "rationale": "Option 'Green' might be correct in some games, but without context it's uncertain."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "unclear", "equivalence_group": null, "confidence": 0.7, "rationale": "Option 'black' might be correct in some games, but without c...`

### `mmlu-redux-computer_security-81` (row_uid=`source-row-00000627`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=1.00)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": ["Wireshark"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status":...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": false, "assumptions_used": [], "missing_information": ["The specific type of network analysis (e.g., scanning vs intrusion detection) is not specified."], "alternative_interpretations": [{"interpretation": "Network analysis for intrusion detection/protocol monitoring", "answer": "Snort"}, {"interpretation": "Network analysis for port scanning", "answer": "SuperScan"}], "rationale": "The phrase 'netw...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Snort is an IDS, not primarily a network analysis tool for multiprotocol networks."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "SuperScan is a port scanner, not a network analysis tool."}, {"label"...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['WIRESHARK'] conflicts with option best_answers=['D']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Wireshark"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Wireshark is a p...`

### `mmlu-redux-college_chemistry-97` (row_uid=`source-row-00000640`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.59)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.589383, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.884.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['C'] conflicts with option best_answers=['B']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["5"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["J << a implies negligible exchange splitting, s...`

### `mmlu-redux-virology-11` (row_uid=`source-row-00000641`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.80)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.8, "needs_expert": false, "assumptions_used": ["Adapted standard diffusion of innovations theory", "'Adapters' interpreted as 'adopters'"], "missing_information": ["Definition of community change segments", "Clarification of 'middle adapters' and 'late adapters'"], "alternative_interpretations": [{"interpretation": "Standard diffusion of innovations: early adopters are crucial for change", "answer": "Early adapters"},...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.8, "rationale": "Innovators are not typically the segment on which effective community change depends; early adopters are more influential."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "unclear", "equivalence_group": null, "confidence": 0.9, "rationale": "Early adopters are the key segmen...`

### `mmlu-redux-security_studies-78` (row_uid=`source-row-00000643`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Valid reason: Western ideologies seen as imperialism."}, {"label": "B", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Valid reason: liberalism enforces values not universally shared."}, {"label": "C", "literal_truth": "fa...`

### `mmlu-redux-human_aging-62` (row_uid=`source-row-00000649`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["Time period or data source for the top 10 causes of death in the U.S."], "alternative_interpretations": [{"interpretation": "Using current CDC data (2024)", "answer": "AIDS"}, {"interpretation": "Using historical data (e.g., 1995)", "answer": "Kidney diseases (assuming AIDS was in top 10 then)"}], "rationale": "The task lacks a time reference. Top cause...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.70)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=uncertain.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Kidney disease is consistently among top 10 causes in US, so it is not the correct answer."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "AIDS is not among top 10 causes of death in US; it is the intended ...`

### `mmlu-redux-college_biology-55` (row_uid=`source-row-00000650`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.94)
  - Independent option checks found multiple choices that satisfy the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"option_evidence": {"solution_status": "multiple", "valid_answers": ["A", "C"], "equivalent_answers": ["A"], "independently_acceptable_answers": ["C"], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9444444444444444, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Exposure to conspecific song is necessary for normal song development in birds.", "evidence_type": "task_text", "support": "Young male reared in isolation...`

### `mmlu-redux-human_sexuality-3` (row_uid=`source-row-00000659`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": true, "assumptions_used": [], "missing_information": ["Historical context or evidence about Alexander the Great's sexuality is not provided."], "alternative_interpretations": [{"interpretation": "Common historical view that Alexander had relationships with both men and women", "answer": "bisexual"}, {"interpretation": "Some accounts focus only on his marriages and children", "answer": "heterosexual"}], "rati...`

### `mmlu-redux-machine_learning-32` (row_uid=`source-row-00000662`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "True statement about semantic segmentation vs classification."}, {"label": "B", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "unclear", "equivalence_group": null, "confidence": 1.0, "rationale": "IoU 96% is a true positive, though wording 'at true positive' is odd."}, {"label": "C", "lite...`

### `mmlu-redux-human_sexuality-5` (row_uid=`source-row-00000666`)

- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.9, "needs_expert": false, "assumptions_used": [], "missing_information": ["Specific measurement (length, circumference)", "State (flaccid or erect)", "Statistical measure (mean, median)"], "alternative_interpretations": [{"interpretation": "Erect length", "answer": "5 inches"}, {"interpretation": "Flaccid length", "answer": "4 inches"}, {"interpretation": "Erect circumference", "answer": "4-5 inches (but not matching choices ...`

### `mmlu-redux-moral_disputes-7` (row_uid=`source-row-00000667`)

- `missing_context` / `context_attachment` / `static_rule` / `major` / unknown (confidence=0.85)
  - Task references passage, but no matching context artifact was found.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the referenced passage or remove the reference.
  - Evidence: `{"reference_type": "passage", "task_excerpt": "Ashford's article is meant to address a particular paralysis in the face of"}`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The content or main thesis of Ashford's article referenced in the question."], "alternative_interpretations": [], "rationale": "The question references 'Ashford's article' without providing any content or context about it. The intended answer depends entirely on knowledge of that specific article, which is not supplied. This makes the task unsolvable fo...`

### `mmlu-redux-astronomy-33` (row_uid=`source-row-00000669`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 1.0, "rationale": "9.3 x 1013 likely means 9.3e13 m, which is not one million times Earth-Sun distance."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 1.0, "rationale": "9.3 x 1010 likely means 9.3e10 m, far too small."}, {"labe...`

### `mmlu-redux-college_chemistry-90` (row_uid=`source-row-00000672`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.99)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.994815, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.995.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-college_medicine-99` (row_uid=`source-row-00000676`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.97)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.966667, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.967.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Anal stage fixation leads to messiness; inability to keep house clean matches anal-expulsive personality."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Phallic stage involves Oedipus complex, no...`

### `mmlu-redux-sociology-21` (row_uid=`source-row-00000679`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.644444, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.967.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["The mode of production refers to the combination of the forces of production (means of production and labor power) and the relations of production (the social relationships and property relations) that characterize a particular...`

### `mmlu-redux-international_law-36` (row_uid=`source-row-00000680`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Baselines determine the inner limit of internal waters, so this statement is literally true."}, {"label": "B", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Baselines are the starting point for measuring all marit...`

### `mmlu-redux-high_school_physics-31` (row_uid=`source-row-00000682`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-public_relations-90` (row_uid=`source-row-00000684`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": true, "assumptions_used": [], "missing_information": ["Definition of attitude communication in the given framework", "Source or theory being referenced"], "alternative_interpretations": [{"interpretation": "Communicated attitude becomes an opinion", "answer": "An opinion"}, {"interpretation": "Communicated attitude becomes a belief", "answer": "A belief"}, {"interpretation": "Communicated attitude becomes a b...`

### `mmlu-redux-virology-65` (row_uid=`source-row-00000686`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.60)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.601975, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.903.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Antibody producing cells (B cells) are stimulated by antigen binding to their B cell receptor and by co-stimulatory signals from helper T cells."], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", "required...`

### `mmlu-redux-global_facts-4` (row_uid=`source-row-00000688`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.99)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9888888888888889, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "As of 2017, approximately 6.7 billion people had some access to electricity.", "evidence_type": "external_source", "support": "World Bank data indicates 89% global access r...`

### `mmlu-redux-virology-78` (row_uid=`source-row-00000689`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.96)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.959259, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.959.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Accurate feature of coronavirus structure."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Incorrect; coronaviruses are not icosahedral."}, {"label": "C", "literal_truth": "false", "best_answer_status":...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Coronaviruses are enveloped, positive-sense single-stranded RNA viruses. The virion is roughly spherical (80-120 nm) with a lipid envelope derived from the host cell membrane. The surface features large, club-shaped spike glycoproteins (S) that give a crown-like a...`

### `mmlu-redux-high_school_statistics-67` (row_uid=`source-row-00000690`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 1.0, "rationale": "Incomplete statement; independence does not follow from union probability."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "P(A ∪ B)=1 does not imply mutual exclusivity; events may overlap."}, {...`

### `mmlu-redux-formal_logic-53` (row_uid=`source-row-00000692`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.67)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["A", "B"], "confidence": 0.666667, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=1.000.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solut...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": "1", "confidence": 1.0, "rationale": "Logically equivalent to B, correct symbolization of conjunction and negation."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": "1", "confidence": 1.0, "rationale": "Gold standard, explicit parentheses, correct symbolization."}, {"label": "C", "litera...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["(F ∧ L) ∧ ¬C"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["Atomic propositions: F = Brittany likes fish, L = Brittany likes lizards, C = Brittany likes cats.", "'but' ...`

### `mmlu-redux-moral_scenarios-66` (row_uid=`source-row-00000693`)

- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.9, "needs_expert": false, "assumptions_used": [], "missing_information": ["Whether the children receive food from other sources (e.g., school, other parent) or are solely dependent on the character for nutrition."], "alternative_interpretations": [{"interpretation": "The character is the sole provider and only gives food once a week, leading to neglect.", "answer": "Not wrong, Wrong"}, {"interpretation": "The character gives ...`

### `mmlu-redux-college_chemistry-94` (row_uid=`source-row-00000696`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.998148, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.998.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-professional_law-85` (row_uid=`source-row-00000697`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.60)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["C", "D"], "confidence": 0.596296, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.894.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solut...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['C', 'D'] conflicts with option best_answers=['B']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["The handyman's best defense is lack of privity: the neighbor was not a party to the contract and is not an intended third-party beneficiary, so cannot ...`

### `mmlu-redux-virology-93` (row_uid=`source-row-00000700`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.66)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["B", "C", "D"], "confidence": 0.664198, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'multiple_correct_answers', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.996.", "evidence_votes": ["multiple_correct_answers", "multiple_correct_answers", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_e...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Sewage control and hygiene are insufficient for eradication; vaccination is required."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Killed polio vaccine alone is not sufficient; live vaccine is primary...`

### `mmlu-redux-high_school_world_history-83` (row_uid=`source-row-00000701`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Jim Crow is a US segregation system, not South Africa."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Spheres of influence is a geopolitical concept, not a discriminatory system."}, {"label": "C...`

### `mmlu-redux-jurisprudence-28` (row_uid=`source-row-00000703`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.93)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9277777777777777, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Lyotard defines postmodern as incredulity toward meta-narratives.", "evidence_type": "task_text", "support": "The dictum explicitly states this definition."}, {"claim": "Me...`

### `mmlu-redux-elementary_mathematics-78` (row_uid=`source-row-00000704`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-logical_fallacies-20` (row_uid=`source-row-00000705`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `major` / review (confidence=0.99)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.985185, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.985.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Poisoning the well is unrelated; it involves discrediting an opponent."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "'Solid slope' is likely a typo for 'slippery slope', which doesn't match...`

### `mmlu-redux-moral_scenarios-93` (row_uid=`source-row-00000708`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": false, "assumptions_used": ["Holding head above water is interpreted as a life-saving action, not harm", "Packing a knife for a school trip may be seen as unsafe but not clearly morally wrong absent context"], "missing_information": ["Intention behind packing the knife (practical use vs. weapon)", "School policy or ordinary norms about knives on trips"], "alternative_interpretations": [{"interpretat...`

### `mmlu-redux-international_law-59` (row_uid=`source-row-00000709`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.95)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Correct definition but less precise than B."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Standard definition of collective rights."}, {"label": "C", "literal_truth": "true", "best_answer_status": "ir...`

### `mmlu-redux-professional_accounting-35` (row_uid=`source-row-00000713`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.640741, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.961.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": true, "assumptions_used": [], "missing_information": ["Which asset's fair value is the most clearly evident? Is any cash boot involved to equalize the exchange?"], "alternative_interpretations": [{"interpretation": "Use fair value of land given up ($50,000) as measurement basis", "answer": "30,000"}, {"interpretation": "Use fair value of machinery received ($55,000) as measurement basis", "answer": ...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['C']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["35000"], "confidence": 0.9, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The fair value of the machinery is used as t...`

### `mmlu-redux-machine_learning-34` (row_uid=`source-row-00000714`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["B", "D"], "confidence": 0.638272, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.957.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solut...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Support vectors are closest to the boundary, not farthest."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Support vectors are the only points with non-zero weights needed for prediction."}, {"label": "...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Support vectors are the data points that lie closest to the decision hyperplane in a Support Vector Machine (SVM). They are the critical elements that define the margin and the hyperplane's position and orientation."], "confide...`

### `mmlu-redux-professional_law-72` (row_uid=`source-row-00000717`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": true, "assumptions_used": [], "missing_information": ["jurisdiction or applicable legal rule regarding contribution after settlement without judgment"], "alternative_interpretations": [{"interpretation": "Jurisdiction allows contribution after settlement without judgment", "answer": "A: prevail, because one who settles without judgment can recover contribution."}, {"interpretation": "Jurisdiction re...`

### `mmlu-redux-moral_disputes-18` (row_uid=`source-row-00000718`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["Thomson's conclusion is not provided in the task"], "alternative_interpretations": [{"interpretation": "Assuming Thomson concluded abortion is always permissible", "answer": "abortion is always morally permissible."}, {"interpretation": "Assuming Thomson concluded abortion is never permissible", "answer": "abortion is never morally permissible."}], "rati...`

### `mmlu-redux-security_studies-63` (row_uid=`source-row-00000720`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["Criteria for determining which statement is the odd one out"], "alternative_interpretations": [{"interpretation": "Odd one out based on normative vs. descriptive nature: 'right to survive' is normative, others are descriptive.", "answer": "Societal groups have a right to survive."}, {"interpretation": "Odd one out based on ontological claim: 'have their ...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['A'] conflicts with option best_answers=['C']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": ["The task requires the list of statements to identify the odd one out; none were provided."], "claims": [{"claim": "The task statement is incomplet...`

### `mmlu-redux-virology-40` (row_uid=`source-row-00000721`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.998148, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.998.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-college_medicine-4` (row_uid=`source-row-00000723`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.95, "needs_expert": false, "assumptions_used": ["Assuming the given formula C2H4 represents the reactant, despite being called 'ethane'."], "missing_information": [], "alternative_interpretations": [{"interpretation": "Using the given formula C2H4 (ethylene) and balancing: C2H4 + 3O2 -> 2CO2 + 2H2O, 84g C2H4=3 mol, yields 6 mol CO2 = 264g", "answer": "264g"}, {"interpretation": "Using correct ethane formula C2H6: 2C2H...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "78g is incorrect; calculation yields 264g."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "528g is incorrect."}, {"label": "C", "literal_truth": "true", "best_answer_status": "best", "clarity": "...`

### `mmlu-redux-high_school_psychology-94` (row_uid=`source-row-00000724`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.628395, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.943.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "va...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.70)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Classical conditioning, not operant."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.8, "rationale": "No clear consequence-behavior link."}, {"label": "C", "literal_truth": "true", "best_answer_status": "acceptab...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "uncertain", "derived_answers": ["A child receives a sticker for completing a chore and subsequently continues to do chores."], "confidence": 0.5, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["Operant conditioning is def...`

### `mmlu-redux-college_chemistry-99` (row_uid=`source-row-00000725`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.98)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.981481, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.981.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none"...`
- `missing_condition` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.95)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.95, "needs_expert": true, "assumptions_used": [], "missing_information": ["Exact microwave frequencies for L-band and W-band"], "alternative_interpretations": [{"interpretation": "Assuming conventional L-band (1 GHz) and W-band (95 GHz)", "answer": "Different from given choices"}, {"interpretation": "Assuming other common values for L-band (e.g., 1.1 GHz) and W-band (94 GHz)", "answer": "Different from given choices"}], "rati...`
- `llm_audit_failure` / `evaluator` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - llm_option_set failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_option_set", "error": "LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 0, 'reasoning_chars': 14974}"}`

### `mmlu-redux-moral_scenarios-87` (row_uid=`source-row-00000731`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.62)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.622222, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.933.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": false, "assumptions_used": ["Ordinary US moral standards as of 2020 are uniform across interpreters", "The phrase 'do something' can be interpreted as including or excluding omissions"], "missing_information": [], "alternative_interpretations": [{"interpretation": "'Do something' includes omissions; both scenarios involve morally wrong actions", "answer": "Wrong, Wrong"}, {"interpretation": "'Do som...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['C'] conflicts with option best_answers=['A']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Scenario 2"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "In Scenario 1, the main...`

### `mmlu-redux-high_school_european_history-63` (row_uid=`source-row-00000733`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "The passage criticizes Louis XIV, so the duke is not sympathetic."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "The duke's memoir portrays Louis's suppression of nobility, showing bias against the kin...`

### `mmlu-redux-business_ethics-17` (row_uid=`source-row-00000735`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The full question or context that specifies what 'they' refers to and what the choice numbers correspond to."], "alternative_interpretations": [], "rationale": "The task statement is a fragment; it does not specify the subject or what the numbers mean. Without the full question, the answer is indeterminate."}, "gold": "B", "choices": ["3,4", "1,3", "2,3"...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.95)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=uncertain.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 0.95, "rationale": "Option is a pair of numbers with no referent; meaning is indeterminate."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 0.95, "rationale": "Same as A; gold designation cannot be verified."}, {"label": ...`

### `mmlu-redux-virology-77` (row_uid=`source-row-00000736`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": true, "assumptions_used": [], "missing_information": ["The disease being treated (e.g., hepatitis B or C) is not specified, which determines the appropriate drug regimen."], "alternative_interpretations": [], "rationale": "The task states 'Chemotherapy' without specifying the disease. The listed drugs are antivirals for hepatitis, but without context, the typical regimen is ambiguous. Missing the disease con...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Interferon and ribavirin is no longer typical for HCV; not used for HBV."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Lamivudine and ribavirin is not a typical regimen for any common viral infection."...`

### `mmlu-redux-abstract_algebra-16` (row_uid=`source-row-00000737`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "False; S is both symmetric and anti-symmetric, not symmetric only."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "False; S is both symmetric and anti-symmetric, not anti-symmetric only."}, {"label": "...`

### `mmlu-redux-marketing-51` (row_uid=`source-row-00000738`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.98)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.983333, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=0.983.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["secondary data"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Second-hand data collected for someone else's purposes is known as secondary data.", "evid...`

### `mmlu-redux-philosophy-6` (row_uid=`source-row-00000739`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.56)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.561728, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.843.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["Context about Stevenson's ethical theory and the specific objection regarding objective a priori goodness."], "alternative_interpretations": [], "rationale": "The task references a specific philosopher's response to an objection but provides no context about Stevenson's theory or the nature of the objection. Without this information, the question cannot...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['A'] conflicts with option best_answers=['C']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Stevenson responds by denying the existence of objective a priori goodness; he argues that 'good' is a term with emotive meaning used to express approval an...`

### `mmlu-redux-high_school_biology-1` (row_uid=`source-row-00000740`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["Details from question 15 about the squirrel population"], "alternative_interpretations": [], "rationale": "The task references 'question 15' for details on the squirrel population, but no context is provided. Without these details, it is impossible to determine which condition is required for Hardy-Weinberg equilibrium, making the task unsolvable."}, "go...`

### `mmlu-redux-virology-38` (row_uid=`source-row-00000743`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.57)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.571605, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'uncertain', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.857.", "evidence_votes": ["no_correct_answer", "uncertain", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none",...`
- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.80)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.8, "needs_expert": false, "assumptions_used": ["The intended reference point for timing is tuberculosis treatment."], "missing_information": ["The question does not specify what the start of antiretroviral treatment is relative to (e.g., tuberculosis treatment)."], "alternative_interpretations": [{"interpretation": "Options refer to timing relative to the start of antiretroviral drugs themselves (circular, nonsensical).", "an...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=none, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale": "Self-referential phrase 'before antiretroviral drugs are started' makes no sense as the question asks about starting antiretroviral treatment."}, {"label": "B", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "corrupted", "equivalence_group": null, "confidence": 1.0, "rationale":...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["within 2 weeks of starting tuberculosis treatment"], "confidence": 0.9, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": [], "claims": [{"claim": "Antiretroviral therapy should be initiated earl...`

### `mmlu-redux-global_facts-95` (row_uid=`source-row-00000746`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.61)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.612346, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.919.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "val...`

### `mmlu-redux-virology-9` (row_uid=`source-row-00000748`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The question does not provide any context, reference, or data to determine which of the listed options is the cause of delay in HIV testing among the Latino population. It is unclear if the answer is based on a specific study, common knowledge, or other source."], "alternative_interpretations": [{"interpretation": "The cause might be stigma only", "answ...`

### `mmlu-redux-logical_fallacies-53` (row_uid=`source-row-00000750`)

- `missing_context` / `context_attachment` / `static_rule` / `major` / unknown (confidence=0.85)
  - Task references passage, but no matching context artifact was found.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the referenced passage or remove the reference.
  - Evidence: `{"reference_type": "passage", "task_excerpt": "E.F. Schumacher, famous economist, in an article in the Atlantic (April 1979): Fifteen months [after I had advised that rural India should have a technology intermediate between the hoe and the tractor,] an all-India conference on intermedi"}`

### `mmlu-redux-moral_scenarios-92` (row_uid=`source-row-00000751`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.60)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.6, "needs_expert": false, "assumptions_used": ["Selling exotic wild animals is generally considered morally wrong in the US (illegal/unethical).", "Cloaking a discovery could be interpreted as hiding it, which might or might not be wrong depending on context (e.g., intellectual property, safety)."], "missing_information": ["What does 'cloak my new discovery' mean? Is it hiding a discovery from an employer or the publi...`

### `mmlu-redux-nutrition-37` (row_uid=`source-row-00000754`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": false, "assumptions_used": ["The task is a multiple-choice question requiring selection of the correct statement about ulcerative colitis."], "missing_information": ["The full question is missing; the task only provides the phrase 'Ulcerative Colitis' without an interrogative or instruction."], "alternative_interpretations": [{"interpretation": "Interpret as 'Which of the following is true about ulcerative c...`

### `mmlu-redux-human_sexuality-4` (row_uid=`source-row-00000759`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.89)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.8944444444444445, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The context is Western societies (e.g., United States) where trends are well-documented."], "claims": [{"claim": "Attitudes toward premarital sex have become more liberal over the past sev...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "False; attitudes have changed."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "False; opposite of trends."}, {"label": "C", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity"...`

### `mmlu-redux-human_aging-11` (row_uid=`source-row-00000760`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.64)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.638272, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.957.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.70)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.7, "needs_expert": true, "assumptions_used": ["Standard psychological definitions of coping strategies are assumed"], "missing_information": ["Definitions of each coping strategy (Immunization, Accommodation, Avoidance, Assimilation) in the context of human aging"], "alternative_interpretations": [{"interpretation": "Avoidance - she avoids the truth about lateness by shifting focus.", "answer": "Avoidance"}, {"interpr...`

### `mmlu-redux-high_school_european_history-36` (row_uid=`source-row-00000763`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.58)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.575309, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.863.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.70)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.7, "needs_expert": true, "assumptions_used": ["That the letter is representative of the monarchy's nature", "That the Queen's fatigue implies something about the monarchy"], "missing_information": ["Explicit statement of the monarchy's political role", "Context about the political system at the time"], "alternative_interpretations": [{"interpretation": "Queen's reliance on Lord Melbourne suggests political power lies ...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["The monarchy was expected to maintain an active social and ceremonial presence, and also involved in political affairs."], "confidence": 0.9, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": [],...`

### `mmlu-redux-high_school_european_history-10` (row_uid=`source-row-00000764`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "True that Sicily ceased to be independent, but not the event described as 'fully snapped'."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "unclear", "equivalence_group": null, "confidence": 0.7, "rationale": "Passage says 'entered liberated Rome', not 'liberated Rome'; ...`

### `mmlu-redux-college_medicine-5` (row_uid=`source-row-00000766`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.632099, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.948.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["The addition of HCl causes more Mg(OH)2 to dissolve, the pH decreases slightly but remains basic (around 10.13), and the concentration of Mg2+ increases."], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", ...`

### `mmlu-redux-conceptual_physics-86` (row_uid=`source-row-00000769`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-moral_disputes-54` (row_uid=`source-row-00000774`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.47)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.465432, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'uncertain', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.698.", "evidence_votes": ["wrong_gold_answer", "uncertain", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "sol...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Altman likely associates viewpoint discrimination with free speech, not privacy."}, {"label": "B", "literal_truth": "true", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Viewpoint-biased restrictions directly threaten free speech, troubl...`

### `mmlu-redux-high_school_geography-76` (row_uid=`source-row-00000777`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.95)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Biology plays a role in gender relationships, so it is not the factor that does NOT play a role."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Advancements in technological development play a r...`

### `mmlu-redux-business_ethics-1` (row_uid=`source-row-00000778`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The statements corresponding to numbers 1, 2, and 3 are not provided in the task."], "alternative_interpretations": [], "rationale": "The task references numbered statements (1,2,3) but does not provide them, making it impossible to determine which combination is correct. Without this context, the question is unsolvable."}, "gold": "B", "choices": ["2,3"...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.95)
  - Option set auditor reported bad_options_clarity with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "unclear", "equivalence_group": null, "confidence": 0.95, "rationale": "Option refers to unspecified numbered statements; cannot evaluate."}, {"label": "B", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "unclear", "equivalence_group": null, "confidence": 0.95, "rationale": "Gold option but missing context makes it uninterpretable."}, {"label": "C", ...`

### `mmlu-redux-virology-29` (row_uid=`source-row-00000780`)

- `source_reference_missing` / `context_attachment` / `task_integrity_rule` / `review` / unknown (confidence=0.80)
  - The task depends on an unnamed study/report and provides no source context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Identify the study/report, publication date, or source artifact.
  - Evidence: `{"matched_phrase": "A study", "task_excerpt": "A study is conducted to assess the relationship between race and end-stage renal disease pathologists independently study specimens from 1,000 kidney biopsies. The first group of pathologists is aware of the race of the patient from whom the biopsy came, while the second group is blinded as to the p"}`
- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `major` / review (confidence=1.00)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "v...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "The bias is information bias due to non-blinding, not confounding."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Nonresponse bias refers to non-response in surveys, not applicable."}, {"label": "C"...`

### `mmlu-redux-high_school_european_history-70` (row_uid=`source-row-00000781`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.98)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9777777777777779, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The group's main interest was natural philosophy or experimental philosophy.", "evidence_type": "task_text", "support": "The passage states they were 'inquisitive into natu...`

### `mmlu-redux-abstract_algebra-0` (row_uid=`source-row-00000782`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": true, "assumptions_used": ["The inequality 'dim(V) < dim(W) < 1' is impossible; assuming a typo might have been intended."], "missing_information": ["The intended meaning of the inequality in Statement 1 is unclear; it is mathematically impossible."], "alternative_interpretations": [{"interpretation": "The condition is impossible (premise false), so Statement 1 is vacuously true", "answer": "True, T...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "unclear", "equivalence_group": null, "confidence": 0.8, "rationale": "Statement 1 ambiguous due to 'dim(W) < 1'; if interpreted vacuously true, then A is correct."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Statement 2 is true, so 'False, False' is wrong."}, {"...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['A']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": ["Statement 1 is vacuously true if interpreted logically, but its premise is impossible (dim(W) < 1 implies dim(W)=0, then dim(V) < 0), making it meaningless in standard linear algebra. Statement 2 is true for finite-dimensional vector spaces. W...`

### `mmlu-redux-professional_medicine-37` (row_uid=`source-row-00000783`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.61)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.608642, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.913.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_a...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Epinephrine (sympathomimetic)"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Patient has anaphylaxis with respiratory involvement.", "evidence_type": "...`

### `mmlu-redux-human_sexuality-0` (row_uid=`source-row-00000785`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.58)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.577778, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.867.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['A']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["of the same sex", "of the opposite sex"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["Standard de...`

### `mmlu-redux-high_school_macroeconomics-19` (row_uid=`source-row-00000786`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Negative current account does not guarantee trade deficit; includes other components."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Negative current account implies capital account surplus, not...`

### `mmlu-redux-international_law-52` (row_uid=`source-row-00000791`)

- `missing_context` / `context_attachment` / `static_rule` / `major` / unknown (confidence=0.85)
  - Task references passage, but no matching context artifact was found.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the referenced passage or remove the reference.
  - Evidence: `{"reference_type": "passage", "task_excerpt": "Are there any limits to the application of article 103 of the UN Charter?"}`

### `mmlu-redux-security_studies-2` (row_uid=`source-row-00000793`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": true, "assumptions_used": [], "missing_information": ["The acronym 'HM' is not defined; it is unclear what paradigm is being referred to."], "alternative_interpretations": [{"interpretation": "HM could refer to a specific framework or theorist (e.g., Hannah Arendt, Hegemonic Masculinity, etc.), leading to different answers.", "answer": "Unknown without specification."}], "rationale": "The question references...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.60)
  - Option set auditor reported bad_options_clarity with literal_cardinality=multiple, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "unclear", "equivalence_group": null, "confidence": 0.5, "rationale": "HM undefined; statement plausible critical view."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "unclear", "equivalence_group": null, "confidence": 0.5, "rationale": "HM undefined; statement plausible critical view."}, {"label": "C", "literal_truth": "uncertain...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['A', 'C'] conflicts with option best_answers=['D']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Within the Historical Materialist paradigm, capitalism is defined as a mode of production characterized by private ownership of the means of production, wage labor, extraction of surplus value, and class conflict between the bourgeoisie and ...`

### `mmlu-redux-formal_logic-85` (row_uid=`source-row-00000795`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.90)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": "1", "confidence": 1.0, "rationale": "Standard predicate-logic translation of the sentence."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Uses variables instead of constants; not a closed formula."}, {"label": "C", "literal_truth": "true",...`

### `mmlu-redux-moral_scenarios-47` (row_uid=`source-row-00000796`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.57)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.565432, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.848.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.90)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "S1 not morally wrong; S2 not clearly wrong (ambiguous consent). Wrong, Wrong false."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "S1 not wrong, so Wrong, Not wrong false."}, {"label": "C", "lit...`

### `mmlu-redux-college_medicine-90` (row_uid=`source-row-00000799`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.630864, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.946.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_a...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["approximately 2 minutes"], "confidence": 0.9, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["the transition from anaerobic to aerobic dominance occurs around 2 minutes for maximal dynamic ex...`

### `mmlu-redux-abstract_algebra-21` (row_uid=`source-row-00000803`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": true, "assumptions_used": ["The question is incomplete; it likely asks which condition is sufficient for H to be a subgroup."], "missing_information": ["The question does not specify whether we are looking for a necessary condition, sufficient condition, or a complete characterization."], "alternative_interpretations": [{"interpretation": "Which single condition is sufficient to guarantee H is a subgroup? (An...`

### `mmlu-redux-human_aging-71` (row_uid=`source-row-00000805`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The content of the chapter's Senior View and Dr. Donham's specific statement about factors for long life are missing."], "alternative_interpretations": [], "rationale": "The question references a specific chapter and a statement by Dr. Donham, but no such context is provided. Without this information, the correct answer cannot be determined from the task...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.70)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.6, "rationale": "Cannot verify without source; typically not a key factor in longevity."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.6, "rationale": "Social support is important, but unknown if Dr. Donham highlighted it here."...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['B'] conflicts with option best_answers=['C']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["social interaction"], "confidence": 0.7, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The missing factor is a commonly cited longevity factor like social interaction, as per standard aging literature."], "cl...`

### `mmlu-redux-world_religions-78` (row_uid=`source-row-00000806`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.98)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.983333, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.983.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "so...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Samyak jnana translates to 'correct knowledge' in Jainism."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Correct practice is samyak charitra."}, {"label": "C", "literal_truth": "false", "best_answer_statu...`

### `mmlu-redux-high_school_physics-12` (row_uid=`source-row-00000810`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=1.00)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "For any cyclic process, the net change in internal energy is zero.", "evidence_type": "definition", "support": "First law of thermodynamics: ΔU_cycle = 0 because the system returns to its...`

### `mmlu-redux-global_facts-15` (row_uid=`source-row-00000816`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": true, "assumptions_used": [], "missing_information": ["Which president is being referred to?", "Which country?", "What is the time period?"], "alternative_interpretations": [{"interpretation": "Franklin D. Roosevelt (USA) before his third term election", "answer": "unknown"}, {"interpretation": "Another president who served three terms (e.g., in other countries)", "answer": "unknown"}], "rationale": "The ques...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.80)
  - Option set auditor reported no_correct_answer with literal_cardinality=uncertain, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.3, "rationale": "Question is ambiguous; cannot verify without context."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.3, "rationale": "Same as A."}, {"label": "C", "literal_truth": "uncertain", "best_answer_status": "best", "cla...`

### `mmlu-redux-anatomy-73` (row_uid=`source-row-00000819`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.67)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.666667, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.667.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-philosophy-45` (row_uid=`source-row-00000821`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": true, "assumptions_used": ["Test-taker is expected to know Parfit's, Taurek's, and Lewis's philosophical views on the sum of pain."], "missing_information": ["The specific passage or argument from Parfit discussing Taurek and Lewis's assumptions."], "alternative_interpretations": [], "rationale": "The question relies on external knowledge of a specific philosophical discussion not provided in the task, making...`

### `mmlu-redux-professional_law-84` (row_uid=`source-row-00000825`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.62)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["A", "B"], "confidence": 0.624938, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.937.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solut...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["succeed in his negligence claim"], "confidence": 0.9, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["Standard negligence principles apply", "Intoxicated person cannot validly consent to bein...`

### `mmlu-redux-college_medicine-0` (row_uid=`source-row-00000827`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.67)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.666667, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=1.000.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution...`
- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The task does not specify whether the user should verify the given match, choose a correct match from the options, or complete all matches.", "The task mentions five stages but only four options are provided, and one pairing is already given."], "alternative_interpretations": [{"interpretation": "The task is to determine which of the four choices is a...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Metaphase involves alignment at equatorial plate, not nuclear membrane formation; that is telophase."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Cytokinesis is cytoplasm division, not sister ...`

### `mmlu-redux-anatomy-71` (row_uid=`source-row-00000829`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Foramen ovale pierces sphenoid but answer omits rotundum and spinosum, making statement incomplete and false."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Includes ovale and rotundum but misses spin...`

### `mmlu-redux-human_aging-39` (row_uid=`source-row-00000834`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The content of the chapter's Senior View or Dr. Shealy's advice is not provided."], "alternative_interpretations": [], "rationale": "The task references specific chapter content (\"Senior View\" and \"Dr. Shealy\") but provides no excerpt, making the intended answer undeterminable from the task alone."}, "gold": "A", "choices": ["Stay in school", "Eat th...`

### `mmlu-redux-global_facts-7` (row_uid=`source-row-00000835`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.62)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.623457, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.935.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "va...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['B'] conflicts with option best_answers=['A']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["approximately 68% of Americans"], "confidence": 0.7, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["the Gallup poll fro...`

### `mmlu-redux-college_chemistry-87` (row_uid=`source-row-00000836`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.998148, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.998.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-high_school_computer_science-67` (row_uid=`source-row-00000837`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Missing elements from the set."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 1.0, "rationale": "Duplicate element in set representation, not a valid output."}, {"label": "C", "literal_truth": "true", "best_answ...`

### `mmlu-redux-high_school_microeconomics-47` (row_uid=`source-row-00000841`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["the content of number 1 question/context"], "alternative_interpretations": [], "rationale": "The task refers to 'the answer in number 1' but provides no prior context or question, making it impossible to determine the correct basis."}, "gold": "B", "choices": ["P or wage rate of labor > MRP of labor and with one additional unit of labor, wage rate < MRP....`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=none, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "unclear", "equivalence_group": null, "confidence": 0.8, "rationale": "Condition is contradictory; not standard microeconomics."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "unclear", "equivalence_group": null, "confidence": 0.7, "rationale": "Gold answer; typo 'WI' makes literal truth uncertain, but intended meaning is correct."}...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [], "rationale": "The task asks 'The basis for the answer in number 1 is' but provides no context or preceding ques...`

### `mmlu-redux-jurisprudence-23` (row_uid=`source-row-00000845`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.95)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Depression of 1930s not a major factor in natural law revival; usually not cited."}, {"label": "B", "literal_truth": "true", "best_answer_status": "acceptable", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Rise of fascism prompted rejection of legal positivism and reviva...`

### `mmlu-redux-philosophy-1` (row_uid=`source-row-00000853`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": true, "assumptions_used": [], "missing_information": ["The specific passage or argument by Parfit that the question refers to."], "alternative_interpretations": [{"interpretation": "The question refers to Parfit's non-identity problem, where an outcome can be worse for no one but still worse overall.", "answer": "b"}, {"interpretation": "The question refers to Parfit's views on personal identity, where he mig...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['A', 'B'] conflicts with option best_answers=['C']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": true, "assumption_risk": "none", "required_assumptions": ["The task is missing the specific claim or options that Parfit is supposed to have made."], "claims": [{"claim": "The task 'Parfit claims that:...`

### `mmlu-redux-high_school_psychology-49` (row_uid=`source-row-00000856`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.80)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.8, "needs_expert": true, "assumptions_used": [], "missing_information": ["The specific psychological theory or study being referenced", "What 'typical' means in this context (e.g., in-group bias vs. internalized racism)"], "alternative_interpretations": [{"interpretation": "Typical in-group bias leads to favoring one's own group", "answer": "black teenagers are superior to white teenagers"}, {"interpretation": "Typical internal...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.70)
  - Option set auditor reported bad_options_clarity with literal_cardinality=none, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.5, "rationale": "Unlikely belief for typical black teenager; ingroup bias favors own group."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.5, "rationale": "Unlikely belief."}, {"label": "C", "literal_truth": "uncertain", "best_a...`

### `mmlu-redux-high_school_physics-20` (row_uid=`source-row-00000857`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.62)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["D"], "confidence": 0.620988, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.931.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['A']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["-0.5e and -0.5e"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["The two spheres are identical in ...`

### `mmlu-redux-high_school_biology-88` (row_uid=`source-row-00000859`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=1.00)
  - Independent option checks found multiple choices that satisfy the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"option_evidence": {"solution_status": "multiple", "valid_answers": ["A", "C", "D"], "equivalent_answers": [], "independently_acceptable_answers": ["A", "C", "D"], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Higher proportion of fixed loci implies lower genetic diversity", "evidence_type": "definition", "support": "In population genetics, a fixed locus has only o...`

### `mmlu-redux-machine_learning-8` (row_uid=`source-row-00000862`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-virology-12` (row_uid=`source-row-00000863`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.70)
  - Option set auditor reported bad_options_clarity with literal_cardinality=multiple, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Vaccines are a primary and widely used preventive measure for many diseases."}, {"label": "B", "literal_truth": "true", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Antivirals can prevent disease (e.g., PrEP) but are not the most often used preven...`

### `mmlu-redux-machine_learning-0` (row_uid=`source-row-00000866`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.58)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.577778, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.867.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`

### `mmlu-redux-professional_law-11` (row_uid=`source-row-00000868`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.95)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Violates physician-patient privilege? No, because statement was not confidential due to technician's presence."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Overhearing alone does not make it admis...`

### `mmlu-redux-college_mathematics-57` (row_uid=`source-row-00000869`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `review` / unknown (confidence=0.95)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.95, "needs_expert": true, "assumptions_used": ["The space is assumed to be a metric space for completeness to be defined"], "missing_information": ["Type of space (metric, topological, etc.) is not specified"], "alternative_interpretations": [{"interpretation": "Assuming metric space", "answer": "Every compact space is complete"}, {"interpretation": "Assuming general topological space (completeness undefined)", "answer": "Neith...`

### `mmlu-redux-virology-13` (row_uid=`source-row-00000870`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=multiple, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Patient-centered is not the focus of public health ethics."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Population-centered is the core definition of public health ethics."}, {"label": "C", "literal_tru...`

### `mmlu-redux-college_chemistry-96` (row_uid=`source-row-00000875`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `major` / review (confidence=1.00)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'no_correct_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "v...`
- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["nuclear magneton value", "g-factor of 13C"], "alternative_interpretations": [], "rationale": "No constants provided to calculate magnetic moment. Standard formula requires nuclear magneton and g-factor, which are absent. Choices suggest a known value, but 'calculate' implies computation from given data."}, "gold": "C", "choices": ["6.1445 x 10^-27 J T...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Not matching known value (≈3.55e-27 J/T)"}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Close but still incorrect; off by ~11%"}, {"label": "C", "literal_truth": "false", "best_answer_status": "...`

### `mmlu-redux-virology-30` (row_uid=`source-row-00000879`)

- `source_reference_missing` / `context_attachment` / `task_integrity_rule` / `review` / unknown (confidence=0.80)
  - The task depends on an unnamed study/report and provides no source context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Identify the study/report, publication date, or source artifact.
  - Evidence: `{"matched_phrase": "a study", "task_excerpt": "Any systematic error in the design, conduct, or analysis of a study that results in a mistaken estimate of an exposure’s effect on the risk of disease is called:"}`
- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.998148, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.998.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-machine_learning-80` (row_uid=`source-row-00000881`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Discriminative approaches model conditional probability p(y|x,w)."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Joint distribution p(y,x) is generative, not discriminative."}, {"label": "C", "literal_...`

### `mmlu-redux-security_studies-40` (row_uid=`source-row-00000886`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.93)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9333333333333333, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Peace studies view technological change as having dual implications.", "evidence_type": "external_source", "support": "Standard peace studies literature acknowledges both p...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.80)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "False: technological developments do affect the majority and are of concern to peace studies."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.5, "rationale": "Uncertain: peace studies may not universally claim th...`

### `mmlu-redux-management-47` (row_uid=`source-row-00000890`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.95)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.948148, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.948.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['C'] conflicts with option best_answers=['D']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["international competition"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The term...`

### `mmlu-redux-human_sexuality-10` (row_uid=`source-row-00000892`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.60)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.6, "needs_expert": true, "assumptions_used": [], "missing_information": ["Whether the question expects a single answer or multiple selections", "Definition of 'generally consistent' in context of date rape characteristics"], "alternative_interpretations": [{"interpretation": "Select all that are typical; only 'sexually motivated' is generally accepted", "answer": "sexually motivated"}, {"interpretation": "Select all t...`

### `mmlu-redux-college_medicine-8` (row_uid=`source-row-00000895`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.57)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.565432, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'none', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.848.", "evidence_votes": ["wrong_gold_answer", "none", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved", "val...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['C'] conflicts with option best_answers=['A']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["mismatch repair"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Mismatch repair c...`

### `mmlu-redux-econometrics-80` (row_uid=`source-row-00000896`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=multiple, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "unclear", "equivalence_group": null, "confidence": 0.7, "rationale": "Misphrased: first stage includes, not excludes variables."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Well-known disadvantage: GETS may lack theoretical grounding."}, {"label": "C", "literal_truth": "...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['D'] conflicts with option best_answers=['B']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["It may result in overfitting due to data mining."], "confidence": 0.9, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "General-to-specific approach starts with a large model and simplifies via t...`

### `mmlu-redux-professional_law-10` (row_uid=`source-row-00000899`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.62)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["C", "D"], "confidence": 0.623457, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'multiple_correct_answers', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.935.", "evidence_votes": ["multiple_correct_answers", "multiple_correct_answers", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_eviden...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.90)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Lack of intent to defraud is irrelevant to an emotional distress claim; the conclusion does not follow."}, {"label": "B", "literal_truth": "uncertain", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.8, "rationale": "Factual premise true; legal sufficiency depends o...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["No"], "confidence": 0.7, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": ["Standard elements of intentional infliction of emotional distress apply."], "claims": [{"claim": "The bar-review compa...`

### `mmlu-redux-high_school_geography-73` (row_uid=`source-row-00000900`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["Definition of 'speakers' (native vs. total speakers)"], "alternative_interpretations": [{"interpretation": "'speakers' refers to native speakers", "answer": "Mandarin Chinese"}, {"interpretation": "'speakers' refers to total speakers including second language", "answer": "English"}], "rationale": "The question asks for the language with the la...`

### `mmlu-redux-logical_fallacies-95` (row_uid=`source-row-00000901`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=0.90)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 0.9, "needs_expert": false, "assumptions_used": ["The quote is presented as an example of a logical fallacy, but no argument is given."], "missing_information": ["The surrounding argument or point being made by the quote is not provided."], "alternative_interpretations": [{"interpretation": "The quote presents only two economic systems as alternatives, ignoring others, suggesting a false dilemma.", "answer": "False Dilemma"}, {"i...`

### `mmlu-redux-virology-94` (row_uid=`source-row-00000902`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Zoonotic viruses are not confined to animals; they can infect humans."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Zoonotic viruses cause disease in humans."}, {"label": "C", "literal_truth": "uncer...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["It means the virus is transmitted from animals to humans."], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "SARS is a zoonotic virus means it is transmitted from animals to humans.", "evidence...`

### `mmlu-redux-formal_logic-57` (row_uid=`source-row-00000911`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.67)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.666667, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'no_correct_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=1.000.", "evidence_votes": ["no_correct_answer", "no_correct_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution...`
- `llm_audit_failure` / `evaluator` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - llm_option_set failed to produce a usable result.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Retry the failed auditor call or inspect provider output.
  - Evidence: `{"auditor": "llm_option_set", "error": "LLM JSON response was truncated; refusing an identical blind retry: {'finish_reason': 'length', 'content_type': 'str', 'content_chars': 0, 'reasoning_chars': 18435}"}`

### `mmlu-redux-computer_security-24` (row_uid=`source-row-00000913`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The content of the paper 'SoK: SSL and HTTPS: Revisiting past challenges and evaluating certificates trust model enhancements' is not provided."], "alternative_interpretations": [], "rationale": "The task requires knowledge of a specific paper's conclusions, but the paper text is not included in the task. Without this context, the answer cannot be determ...`

### `mmlu-redux-public_relations-11` (row_uid=`source-row-00000916`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Situation analysis is research, not planning messages."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Strategy involves planning what to say and why per Cutlip."}, {"label": "C", "literal_truth": "false", ...`

### `mmlu-redux-college_chemistry-85` (row_uid=`source-row-00000920`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`

### `mmlu-redux-high_school_mathematics-92` (row_uid=`source-row-00000922`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=1.00)
  - Independent option checks found multiple choices that satisfy the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"option_evidence": {"solution_status": "multiple", "valid_answers": ["B", "C"], "equivalent_answers": ["C"], "independently_acceptable_answers": ["B"], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Alice rounds to nearest ten-thousand, result 10000", "evidence_type": "calculation", "support": "12345.6789 rounded to nearest ten-thousand: thousand digit 2 <5, round d...`

### `mmlu-redux-public_relations-50` (row_uid=`source-row-00000931`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["current number of practitioners in consultancies in UK", "number of practitioners 25 years ago"], "alternative_interpretations": [], "rationale": "The question provides no numerical data or reference to any source to determine growth. Without knowing the number of practitioners 25 years ago and now, the answer cannot be determined from the given informat...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": true, "assumption_risk": "answer_changing", "required_assumptions": ["The question requires external data on the number of practitioners in UK consultancies 25 years ago and now, which is...`

### `mmlu-redux-marketing-28` (row_uid=`source-row-00000932`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.61)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.611111, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.917.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["participation (active vs. passive) and connection (absorption vs. immersion)"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Pine and Gilmore's four real...`

### `mmlu-redux-computer_security-47` (row_uid=`source-row-00000933`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.98)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.983333, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.983.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "This correctly describes integer overflow as wraparound, matching standard definition."}, {"label": "B", "literal_truth": "false", "best_answer_status": "invalid", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Describes type confusion, not integer overflow."}, {"label": "C", "lit...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["An integer overflow occurs when the result of an arithmetic operation on an integer exceeds the maximum representable value for that integer's bit width, causing the value to wrap around to a smaller number or produce an error."], "confidence": 1.0, "needs_expert"...`

### `mmlu-redux-high_school_chemistry-60` (row_uid=`source-row-00000935`)

- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["The actual question or instruction to be answered by the choices is not provided. Only a chemical equation is given, and the choices are statements about the reaction, but it is unclear whether the test-taker should select the correct statement, the false statement, or something else."], "alternative_interpretations": [{"interpretation": "Assume quest...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.70)
  - Option set auditor reported bad_options_clarity with literal_cardinality=multiple, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": "1", "confidence": 0.9, "rationale": "Literal interpretation of equation; but likely not a false statement."}, {"label": "B", "literal_truth": "true", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": "1", "confidence": 0.9, "rationale": "Standard mole interpretation; equivalent to A."}, {"label": "C", "literal_truth":...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['A', 'B'] conflicts with option best_answers=['D']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": false, "assumption_risk": "answer_changing", "required_assumptions": ["The question is missing; only the chemic...`

### `mmlu-redux-computer_security-30` (row_uid=`source-row-00000936`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.50)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=uncertain.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "uncertain", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.3, "rationale": "Ambiguous whether 'Mishandling of undefined variables' is a transport layer vulnerability; could be general coding error."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Fingerprinting via tr...`

### `mmlu-redux-professional_accounting-89` (row_uid=`source-row-00000938`)

- `missing_condition` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.80)
  - Question clarity auditor reported missing_condition.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add the missing condition or source convention required to determine the answer.
  - Evidence: `{"llm_result": {"clarity_status": "missing_condition", "confidence": 0.8, "needs_expert": false, "assumptions_used": [], "missing_information": ["Explicit separation or labeling of the two characteristics: 'Data covering financial trends' and 'Fiscal years'."], "alternative_interpretations": [{"interpretation": "The two characteristics are 'Data covering financial trends' and 'Fiscal years', with the answer being a combination of Yes/No for each.", "answer": "Depends on the intended mapping."}, ...`

### `mmlu-redux-college_chemistry-83` (row_uid=`source-row-00000939`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.633333, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.633.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "so...`
- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.90)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.9, "needs_expert": false, "assumptions_used": [], "missing_information": ["McConnell constant Q (typically 22.5–23 G) not provided"], "alternative_interpretations": [{"interpretation": "Using Q=22.5 G gives ρ≈0.97", "answer": "0.95 (closest)"}, {"interpretation": "Using Q=23 G gives ρ≈0.95", "answer": "0.95"}, {"interpretation": "Using Q=25.8 G gives ρ≈0.85", "answer": "0.85"}], "rationale": "Spin density on carbon ca...`

### `mmlu-redux-professional_accounting-96` (row_uid=`source-row-00000941`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.62)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.622222, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['no_correct_answer', 'none', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.933.", "evidence_votes": ["no_correct_answer", "none", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "none", "valid_an...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["$372.37"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The present value of $3,000 annual inflows for 5 years at 10% is $11,372.37.", "evidence_type": "...`

### `mmlu-redux-virology-83` (row_uid=`source-row-00000943`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.998148, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.998.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-virology-98` (row_uid=`source-row-00000945`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Not all HPV clades contain oncogenic types."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Includes type 14, which is not oncogenic."}, {"label": "C", "literal_truth": "false", "best_answer_stat...`

### `mmlu-redux-formal_logic-33` (row_uid=`source-row-00000946`)

- `duplicate_choices` / `oracle_ground_truth` / `static_rule` / `review` / review (confidence=0.75)
  - Two or more choices normalize to the same text.
  - Evidence: `deterministic_rule` — The originating checker explicitly withheld automatic confirmation.
  - Repair: Deduplicate choices unless duplicates are intentional distractors that do not affect the gold answer.
  - Evidence: `{"duplicates": [[1, 2, "sC ≡ eJ"]], "choices": ["Cs ⊃ Ej", "Sc ≡ Ej", "sC ≡ eJ", "Sx ≡ Jy"]}`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says multiple_correct_answers but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["C ↔ J"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "The sentence expresses a biconditional.", "evidence_type": "task_text", "support": "The phrase 'if and only if' indicates logical...`

### `mmlu-redux-elementary_mathematics-25` (row_uid=`source-row-00000948`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=1.00)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 1.0, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=1.000.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "solved...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=1.00)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Correct solution to the equation."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Incorrect; would give g+24=1, not -47."}, {"label": "C", "literal_truth": "false", "best_answer_status": "weaker", "clarity"...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["-71"], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "-47 = g + 24 implies subtracting 24 from both sides yields g = -71", "evidence_type": "calculation", "support": "-47 - 24 = -71"}], "ratio...`

### `mmlu-redux-virology-75` (row_uid=`source-row-00000950`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.66)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.656296, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.656.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "B", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Yellow fever vaccine"], "confidence": 0.9, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Yellow fever vaccine is the most successful and widely used travel vaccine", "eviden...`

### `mmlu-redux-machine_learning-55` (row_uid=`source-row-00000952`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.90)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Statement is true: increasing λ never decreases training error in exact regularized least squares."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 0.95, "rationale": "Increasing λ typically increases training error, so it ca...`

### `mmlu-redux-virology-79` (row_uid=`source-row-00000955`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.58)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.582716, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.874.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", ...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.90)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Shotgun sequencing is a valid method for sequencing polyomavirus genomes."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Cultivation in human neural cells is not a standard method for detailing new pol...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["New polyomaviruses are detailed through molecular detection (PCR, sequencing), serological assays (antibody detection), and electron microscopy, along with genomic characterization and phylogenetic analysis."], "confidence": 0....`

### `mmlu-redux-management-17` (row_uid=`source-row-00000957`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=1.00)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 1.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Contingency planning is also known as business continuity planning.", "evidence_type": "definition", "support": "In management, contingency planning and business continuity planning are c...`

### `mmlu-redux-human_aging-94` (row_uid=`source-row-00000958`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The content of the chapter's Senior View featuring Mabel Davis"], "alternative_interpretations": [], "rationale": "The task references Mabel Davis from a specific chapter section but provides no passage or context, making it impossible to determine her agreement with any statement without the source material."}, "gold": "A", "choices": ["Time seems to sp...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": false, "assumption_risk": "none", "required_assumptions": ["The context of the chapter 'Senior View' and Mabel Davis's statements are not provided, so no answer can be derived."], "claims...`

### `mmlu-redux-astronomy-17` (row_uid=`source-row-00000960`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.93)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9277777777777779, "needs_expert": false, "assumption_risk": "conventional", "required_assumptions": [], "claims": [{"claim": "Life on Earth originated from non-living matter through abiogenesis.", "evidence_type": "external_source", "support": "Scientific consensus in biology and astronomy...`

### `mmlu-redux-human_sexuality-27` (row_uid=`source-row-00000962`)

- `multiple_correct_answers` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported multiple_correct_answers with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "multiple_correct_answers", "correct_answers": ["A", "B", "C"], "confidence": 0.634568, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['multiple_correct_answers', 'none', 'multiple_correct_answers']; agreement=2/3; mean_stage_confidence=0.952.", "evidence_votes": ["multiple_correct_answers", "none", "multiple_correct_answers"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['A', 'B', 'C'] conflicts with option best_answers=['D']", "option defect says multiple_correct_answers but cardinality is exactly_one", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "D", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["masturbation"], "confidence": 1.0, "needs_expert": false, "assumptio...`

### `mmlu-redux-high_school_computer_science-13` (row_uid=`source-row-00000974`)

- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Correctly combines, sorts, then removes duplicates; typo 'RemoveDup1icates' does not affect understanding."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Sorts each list separately then combines unsort...`

### `mmlu-redux-business_ethics-55` (row_uid=`source-row-00000975`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The specific theory referenced", "What 'complexity' means in this context", "What the numbers 1,2,3,4 represent"], "alternative_interpretations": [{"interpretation": "Without context, any choice could be correct depending on unknown criteria", "answer": "1,2,3,4 or 1,3,4 or 1,2,3 or 1,2,4"}], "rationale": "The task statement 'The complexity of the theory...`

### `mmlu-redux-miscellaneous-46` (row_uid=`source-row-00000978`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.63)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["B"], "confidence": 0.625926, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=2/3; mean_stage_confidence=0.939.", "evidence_votes": ["none", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `review` / review (confidence=0.95)
  - Option set auditor reported no_correct_answer with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Copper has a positive temperature coefficient of about 0.0039/°C, so its resistance is significantly affected by temperature."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Carbon has a negative temper...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["option defect says no_correct_answer but cardinality is exactly_one"], "affected_methods": ["llm_option_set"], "observations": {"_declared_gold": "A", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": false, "assumption_risk": "answer_changing", "required_assumptions": ["The question does not list the materials to choose from; without choices, the answer cannot be determined."], "claims": [{"claim": "The task provides no ...`

### `mmlu-redux-machine_learning-74` (row_uid=`source-row-00000979`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `review` / review (confidence=0.60)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.6, "needs_expert": false, "assumptions_used": ["If features are not standardized, coefficient magnitude is not directly interpretable.", "If features are standardized, high absolute coefficient indicates strong effect."], "missing_information": ["Whether the features are standardized or on comparable scales."], "alternative_interpretations": [{"interpretation": "Features not standardized; coefficient magnitude alone c...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['A'] conflicts with option best_answers=['C']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["The feature has a strong negative linear relationship with the target variable; as the feature increases, the predicted outcome decreases significantly."], "confidence": 0.95, "needs_expert": false, "assumption_risk": "none", "required_assumption...`

### `mmlu-redux-business_ethics-65` (row_uid=`source-row-00000981`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The task statement only says 'Predatory pricing.' without any context, question, or list of items corresponding to numbers 1-4. The actual question or descriptions for choices 1,2,3,4 are missing."], "alternative_interpretations": [], "rationale": "The task consists solely of the phrase 'Predatory pricing.' with an empty context object. The choices are n...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=1.00)
  - Option set auditor reported bad_options_clarity with literal_cardinality=uncertain, best_answer_cardinality=uncertain.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "unclear", "equivalence_group": null, "confidence": 1.0, "rationale": "No statements provided; option is uninterpretable."}, {"label": "B", "literal_truth": "invalid", "best_answer_status": "invalid", "clarity": "unclear", "equivalence_group": null, "confidence": 1.0, "rationale": "No statements provided; option is uninterpretable."}, {"label": "C", "literal_truth": "invalid...`

### `mmlu-redux-econometrics-55` (row_uid=`source-row-00000985`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The model specification, estimated coefficients, standard errors, or any data from question 21."], "alternative_interpretations": [], "rationale": "The task references a model from question 21, but no details of that model are provided. Without the estimated coefficients and standard errors, no confidence interval can be determined, making the task unsol...`

### `mmlu-redux-formal_logic-58` (row_uid=`source-row-00000990`)

- `ambiguous_goal` / `task_specification` / `llm_question_clarity` / `major` / review (confidence=0.95)
  - Question clarity auditor reported answer_changing_ambiguity.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Clarify the task goal and answer-changing assumptions.
  - Evidence: `{"llm_result": {"clarity_status": "answer_changing_ambiguity", "confidence": 0.95, "needs_expert": false, "assumptions_used": [], "missing_information": ["Which conditional is referred to by 'the conditional proposition' since it is a biconditional?"], "alternative_interpretations": [{"interpretation": "The proposition is treated as a single conditional (if P then Q) ignoring the 'only if' part, so antecedent is 'both the governor approves of it and the board of trustees recommends it'.", "answe...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Only an antecedent in one direction of the biconditional, not the whole."}, {"label": "B", "literal_truth": "false", "best_answer_status": "weaker", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Only part of the conjunction, not the full antecedent."}, {"label": "C", "literal_...`

### `mmlu-redux-business_ethics-16` (row_uid=`source-row-00000991`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.96)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["A"], "confidence": 0.955556, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.956.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['A'] conflicts with option best_answers=['C']", "gold auditor contradicts the declared gold while option auditor still marks it as best"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "solved", "derived_answers": ["Cryptocurrencies", "decentralized", "anonymous", "illegal activities"], "confidence": 0.95, "needs_expert": false, "assumption_risk": "conventional", "requi...`

### `mmlu-redux-high_school_physics-0` (row_uid=`source-row-00000992`)

- `wrong_gold_answer` / `oracle_ground_truth` / `llm_gold_audit` / `critical` / review (confidence=0.99)
  - Gold auditor reported wrong_gold_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Review and correct the gold answer or reference solution.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "wrong_gold_answer", "correct_answers": ["C"], "confidence": 0.994815, "needs_expert": false, "rationale": "Programmatic evidence aggregation: votes=['wrong_gold_answer', 'wrong_gold_answer', 'wrong_gold_answer']; agreement=3/3; mean_stage_confidence=0.995.", "evidence_votes": ["wrong_gold_answer", "wrong_gold_answer", "wrong_gold_answer"], "evidence_agreement": 1.0, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "s...`

### `mmlu-redux-marketing-13` (row_uid=`source-row-00000993`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_option_applicability` / `review` / review (confidence=0.99)
  - Independent option checks found no choice that satisfies the task.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"option_evidence": {"solution_status": "none", "valid_answers": [], "equivalent_answers": [], "independently_acceptable_answers": [], "missing_option_assessments": [], "uncertain_answers": [], "confidence": 0.9888888888888889, "needs_expert": false, "assumption_risk": "none", "required_assumptions": [], "claims": [{"claim": "Information collected for the first time specifically for a marketing research study is called primary data.", "evidence_type": "definition", "support": "Standard marketing...`
- `multiple_correct_answers` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=1.00)
  - Option set auditor reported multiple_correct_answers with literal_cardinality=multiple, best_answer_cardinality=multiple.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Broaden accepted alternatives or rewrite the item to have a unique correct answer.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Secondary research uses existing data, not collected for first time."}, {"label": "B", "literal_truth": "true", "best_answer_status": "best", "clarity": "clear", "equivalence_group": null, "confidence": 1.0, "rationale": "Primary research is defined as data collected for the first time for a specific study...`

### `mmlu-redux-nutrition-43` (row_uid=`source-row-00000994`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["Data on consumption quantities of foods in Wales and Scotland in 2020"], "alternative_interpretations": [], "rationale": "The question asks which foods are consumed in lower quantities in Wales and Scotland as of 2020, but provides no data or source. Without external knowledge, the answer cannot be determined, making the task unsolvable."}, "gold": "C", ...`
- `bad_options_clarity` / `expected_output` / `llm_option_set` / `review` / unknown (confidence=0.80)
  - Option set auditor reported bad_options_clarity with literal_cardinality=exactly_one, best_answer_cardinality=exactly_one.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred output_contract mapping row_status=unresolved
  - Repair: Rewrite unclear, overlapping, or uninterpretable answer choices.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Meat consumption is not typically lower in Wales and Scotland."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Confectionary consumption is not notably lower in these regions."}, {"label": "C", "...`
- `auditor_contradiction` / `evaluator` / `llm_evidence_fusion` / `review` / unknown (confidence=1.00)
  - LLM auditors produced mutually inconsistent conclusions.
  - Evidence: `model_judgment` — Operational failure describes audit coverage, not a benchmark defect.
  - Repair: Resolve the auditor disagreement before confirming a benchmark defect.
  - Evidence: `{"reasons": ["gold correct_answers=['A', 'B', 'D'] conflicts with option best_answers=['C']"], "affected_methods": ["llm_gold_audit", "llm_option_set"], "observations": {"_declared_gold": "C", "llm_blind_solver": {"solution_status": "ambiguous", "derived_answers": [], "confidence": 0.0, "needs_expert": true, "assumption_risk": "answer_changing", "required_assumptions": ["The question requires specific nutritional survey data for Wales and Scotland in 2020, which is not provided in the task descr...`

### `mmlu-redux-business_ethics-49` (row_uid=`source-row-00000997`)

- `missing_context` / `context_attachment` / `llm_question_clarity` / `major` / unknown (confidence=1.00)
  - Question clarity auditor reported missing_context.
  - Evidence: `adapter_inference` — Finding may be caused by incomplete/ambiguous automatic field mapping: inferred context mapping row_status=unresolved
  - Repair: Attach the missing context or remove context-dependent wording.
  - Evidence: `{"llm_result": {"clarity_status": "missing_context", "confidence": 1.0, "needs_expert": false, "assumptions_used": [], "missing_information": ["The task does not provide any question or list of items that the numbers refer to. Without context, it's impossible to determine which set of numbers is correct."], "alternative_interpretations": [], "rationale": "The task only states 'The Private Sector Social Enterprise Model' with no further context. The choices are sets of numbers, but without any en...`

### `mmlu-redux-global_facts-11` (row_uid=`source-row-00000998`)

- `no_correct_answer` / `oracle_ground_truth` / `llm_gold_audit` / `review` / review (confidence=0.61)
  - Gold auditor reported no_correct_answer with gold_status=contradicted.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"gold_status": "contradicted", "defect_type": "no_correct_answer", "correct_answers": [], "confidence": 0.612346, "needs_expert": true, "rationale": "Programmatic evidence aggregation: votes=['none', 'no_correct_answer', 'no_correct_answer']; agreement=2/3; mean_stage_confidence=0.919.", "evidence_votes": ["none", "no_correct_answer", "no_correct_answer"], "evidence_agreement": 0.6666666666666666, "valid_evidence_stages": 3, "blind_solution": {"solution_status": "uncertain", "val...`
- `no_correct_answer` / `oracle_ground_truth` / `llm_option_set` / `major` / review (confidence=0.90)
  - Option set auditor reported no_correct_answer with literal_cardinality=none, best_answer_cardinality=none.
  - Evidence: `model_judgment` — Semantic/model judgements can prioritize review but cannot self-confirm.
  - Repair: Add a correct answer, revise choices, or remove the item.
  - Evidence: `{"llm_result": {"option_statuses": [{"label": "A", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "Internet penetration in Brazil in 2017 was around 67%, so 18% is too low."}, {"label": "B", "literal_truth": "false", "best_answer_status": "irrelevant", "clarity": "clear", "equivalence_group": null, "confidence": 0.9, "rationale": "38% is also too low compared to actual ~67%."}, {"label": "C", "literal_t...`
