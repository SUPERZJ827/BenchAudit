# Blind benchmark-item adjudication instructions

You are independently evaluating benchmark item quality. You are not evaluating another
reviewer's claims, and you must not attempt to infer why an item was selected.

## Input

Read every JSONL row in `package.jsonl`. Every row has the same schema:

- `blind_id`
- `question`
- `choices`
- `declared_gold`
- `evaluator`

Do not search for the complete question text, the blind ID, benchmark errata, or prior discussions
of these exact items. You may consult authoritative general references only after first attempting
the problem independently; record every source you use.

## Required procedure for every row

1. Solve the item independently from the question and choices.
2. Determine whether the declared gold and item contract define a valid benchmark item.
3. Return exactly one JSON object, on one line, with this schema:

```json
{
  "blind_id": "copy exactly from input",
  "material_status": "clean | material_defect | presentation_only | needs_domain_expert | insufficient_evidence",
  "defect_family": "none | wrong_gold | no_correct_answer | multiple_correct_answers | missing_condition_or_context | materially_ambiguous_question | defective_options | evaluator_contract_error | other_material",
  "derived_answer_or_answer_set": "your independent result",
  "confidence": "low | medium | high",
  "item_internal_evidence": "specific evidence from the item",
  "external_source_used": false,
  "external_source_citation": null,
  "short_rationale": "concise reason for the verdict"
}
```

## Materiality rules

- `wrong_gold`: the item has a uniquely derivable answer that differs from `declared_gold`.
- `no_correct_answer`: none of the choices/declared answers satisfies the question.
- `multiple_correct_answers`: at least two answers are correct under the same reasonable reading.
- Missing context or ambiguity is material only when it can change the correct answer.
- `defective_options`: duplicated, mutually inclusive, incompatible-granularity, or otherwise invalid
  options make scoring materially unreliable.
- Pure wording preference, style, or harmless formatting is not a material defect.
- If specialized facts cannot be verified confidently, use `needs_domain_expert`; do not guess.
- If the supplied artifact cannot settle the question, use `insufficient_evidence`.
- `defect_family` must be `none` unless `material_status` is `material_defect`.

## Output integrity

- Produce exactly one output row for every input `blind_id` and no extras.
- Preserve `blind_id` byte-for-byte.
- Do not add source labels, guessed selection groups, or comments outside JSONL.
- Do not ask for or use any mapping between blind IDs and source IDs before submitting the complete
  output.

Your output will be committed and hash-locked before any selection metadata is revealed.

