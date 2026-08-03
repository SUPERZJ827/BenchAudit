# MMLU response-pattern baseline: post-result interpretation

This addendum binds the generated outputs without modifying the frozen
protocol, score definition, thresholds, metrics, or report.

## Bottom line

The simple response-consensus baseline does **not** beat BenchAudit on broad
explicit-defect detection at the preregistered threshold:

| Endpoint/system | P | R | F1 |
|---|---:|---:|---:|
| Strict explicit defects — BenchAudit | 0.695 | 0.580 | **0.632** |
| Strict explicit defects — response pattern, k≥8 | 0.685 | 0.405 | 0.509 |
| Strict explicit defects — response post-hoc oracle, k≥3 | 0.567 | 0.698 | 0.626 |

The in-sample oracle response threshold still falls slightly below BenchAudit,
but the difference is only 0.006 F1 and cannot support a meaningful superiority
claim—especially given the measured run-to-run variation of the LLM auditing
instrument. The oracle threshold is optimistic and is not the primary result.

## The important decomposition

For wrong-groundtruth alone, the preregistered systems effectively tie in F1:

| System | P | R | F1 |
|---|---:|---:|---:|
| BenchAudit | 0.517 | 0.868 | 0.6479 |
| Response pattern, k≥8 | 0.563 | 0.764 | 0.6480 |
| Response post-hoc oracle, k≥9 | 0.625 | 0.708 | 0.6637 |

Therefore a large part of wrong-gold detection can be explained by the much
simpler signal “many models choose the same non-gold option.” BenchAudit should
not claim an algorithmic advantage on wrong-gold F1 from this experiment.

The broader gold-related endpoint does separate the systems:

| System | P | R | F1 |
|---|---:|---:|---:|
| BenchAudit | 0.621 | 0.779 | **0.691** |
| Response pattern, k≥8 | 0.613 | 0.552 | 0.581 |

At k≥8, the frozen per-label recalls are descriptively:

| Redux label | BenchAudit recall | Response-pattern recall |
|---|---:|---:|
| wrong_groundtruth | 0.868 | 0.764 |
| no_correct_answer | 0.722 | 0.222 |
| multiple_correct_answers | 0.590 | 0.282 |
| bad_options_clarity | 0.400 | 0.120 |
| bad_question_clarity | 0.341 | 0.258 |

These per-label values are post-result descriptive breakdowns, not separately
preregistered hypothesis tests. They locate the plausible incremental value:
question/options structure and accepted-answer-set defects, rather than simple
wrong-gold disagreement.

## What this changes in the paper

Do not write “BenchAudit beats simple multi-model consensus” without a scope
qualifier. The defensible statement is:

> On the frozen MMLU-1000 development population, a preregistered 15-model
> response-consensus baseline matched BenchAudit's F1 for wrong-groundtruth
> detection but had substantially lower recall and F1 on the broader explicit-
> defect endpoint. BenchAudit's incremental value is concentrated in defect
> types not reducible to shared non-gold answer patterns.

This is still in-sample: BenchAudit was developed on the population, and the
response threshold curve was evaluated on it. Holdout evidence remains needed.

## Cost and determinism boundary

The analysis made zero new API calls. The baseline is not intrinsically free:
it consumes 15 previously generated model responses per item. Its replay is
deterministic conditional on those frozen response files; fresh generation of
the 15 answers was not tested for stability.

## Incomplete-label warning

The separate deterministic scan found seven exact duplicate-choice items, six
labelled Redux `ok`. Thus supervised FP counts are upper bounds on genuine
false positives. Neither system should be assumed wrong merely because it flags
an `ok` item; mechanically confirmed disagreements require separate accounting.

## Bound outputs

| Artifact | SHA-256 |
|---|---|
| Scores | `02baa5cd7e30c91d54d7434a8552049628b63dcbbaee7ba72a640db34f2cede0` |
| Metrics | `956f68bf604263f5c664f9b4bd10add7b2f488dc0ce8787e8e52662551da33ec` |
| Generated report | `8b136b622d77ded63058ebd79e1a0c7d244a2c4d877e095c6928a019454f2c71` |
| Stable receipt | `8c21a194f384eb49cc2e311f1b9eb9f37b5a0185068d9304ca065c89094dad95` |
