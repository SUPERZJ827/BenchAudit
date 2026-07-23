# MMLU-Redux subject-grouped robustness protocol

Frozen before label-based evaluation on 2026-07-23.

## Question

Does the fixed `BenchAudit + psychometric fusion` score generalize across MMLU
subjects materially better than the simpler `BenchAudit + error rate` score?

This is a **subject-grouped robustness diagnostic**, not a pristine unseen
holdout experiment. Aggregate MMLU-Redux labels and the full-data post-hoc
result were inspected in the preceding feasibility study. No claim of an
untouched test set or confirmatory statistical significance will be made.

## Inputs

- Frozen feature, score, and label artifacts from
  `reports/mmlu_psychometric_feasibility_20260722/`.
- Exactly 1,000 archived MMLU-Redux items and 15 archived model responses per
  item.
- No API calls and no new model execution.
- Items must be joined by `item_id`; source file row order must never be used.

The scoring phase may read `features.json` and `scores.json`. It must not read
`labels.json` or any `error_type` field. The evaluation phase may read the
already frozen score artifact and the labels.

## Fixed methods

No weights or thresholds may be fitted using labels.

1. `benchaudit_score`
2. `audit_error_rate_fusion`
3. `audit_majority_fusion`
4. `audit_psychometric_fusion`

Each fusion is the unweighted mean of the global, tie-aware percentile rank of
`benchaudit_score` and the corresponding component. The implementation must
reproduce the previously frozen `audit_psychometric_fusion` values to floating
point tolerance.

All four methods have an evidence ceiling of `review`; none may promote an item
to `confirmed`.

## Subject grouping

Create five deterministic folds without reading labels:

1. Count items per subject from `features.json`.
2. Sort subjects by decreasing item count, then by subject name.
3. Greedily assign each whole subject to the fold with the fewest items;
   break ties by fold index.

Subjects must never be split across folds. These folds are evaluation groups,
not training folds: the scores are fixed globally and no model is refitted.

## Label scopes

Primary:

- positive: the 181 objective MMLU-Redux defects;
- negative: `ok` items;
- exclude other subjective/non-objective error labels.

Secondary:

- positive: any non-`ok` label;
- negative: `ok`.

## Metrics

Report:

- full-data AP and precision at 20/50/100;
- pooled AP and precision at 20/50 within each subject fold;
- macro AP over eligible individual subjects;
- paired per-subject AP deltas;
- wins/ties/losses for complex versus simple fusion;
- a deterministic 10,000-resample subject bootstrap 95% confidence interval
  for the mean paired AP delta;
- a two-sided Wilcoxon signed-rank p-value as a descriptive diagnostic only.

A subject is eligible for paired primary analysis if it contains at least
three objective positives and at least five `ok` negatives. For the secondary
scope, replace “objective” with “any error”. Ties use absolute delta below
`1e-12`.

The principal comparison is:

`audit_psychometric_fusion - audit_error_rate_fusion`.

## Frozen decision rule

Recommend engineering the complex psychometric fusion only if all conditions
hold on the primary scope:

1. mean paired subject AP delta is at least `+0.010`;
2. the 95% subject-bootstrap lower bound is above zero;
3. wins exceed losses;
4. pooled fold AP delta is positive in at least four of five folds.

Otherwise recommend the simpler `BenchAudit + error rate` candidate front end.
The Wilcoxon p-value is reported but is not a gate because this diagnostic was
motivated by an already inspected full-data result.

## Integrity and reporting

- Record SHA-256 hashes of every input and output artifact.
- Refuse to score if the scoring inputs contain `error_type`.
- Refuse evaluation if feature, score, fold, and label ID sets differ.
- Re-run the complete experiment and require byte-identical folds, scores,
  metrics, and report.
- Report negative and mixed results; do not tune the decision rule after seeing
  them.

