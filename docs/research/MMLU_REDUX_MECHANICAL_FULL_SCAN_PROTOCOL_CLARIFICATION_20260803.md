# MMLU-Redux mechanical full-scan protocol: pre-implementation clarification

> Frozen before implementation and before any 5,700-item rule result  
> Parent protocol commit: `f946970`  
> Parent protocol SHA-256: `b974fef9962653c99f4787c820258d45d7c2cc0f32225539e0216fcde4e08bc4`

## Clarification

Parent §1 says every row must contain a string `gold`, while §2.2 and required
test 5 define missing and non-string gold as R2 findings. Those statements are
inconsistent. The R2 definition is controlling.

For this scan:

- `id`, `question`, `choices`, `evaluator`, and `metadata` remain mandatory;
- a missing `gold` key, JSON null, or non-string `gold` value is processed by
  R2 and produces one deterministic `unresolvable_declared_gold` finding;
- such a value is not a schema failure and is not coerced to text;
- every other §1 schema condition remains fail-closed, including four string
  choices and the exact multiple-choice evaluator;
- the frozen 5,700-row input hash, rule definitions, counts, outputs, positive
  control, non-activation boundary, and stopping rules do not change.

This clarification removes an implementation ambiguity. It cannot turn an R2
non-hit into a hit by changing label normalization, and it does not add a new
rule or widen the source population.
