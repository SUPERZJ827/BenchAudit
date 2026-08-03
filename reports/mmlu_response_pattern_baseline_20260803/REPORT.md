# MMLU-1000 offline response-pattern baseline

Outcome: **BASELINE_COMPLETE**

The response baseline flags an item when at least `k` of 15 recorded models emit the same valid non-gold option. Invalid/missing predictions abstain.

## Legacy endpoint (non-`ok`, including `expert`)

| System | Threshold | Candidates | P | R | F1 | Specificity | Incremental API cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| BenchAudit | review candidate | 292 | 0.705 | 0.557 | 0.622 | 0.863 | historical paid run |
| Response pattern (primary) | ≥8 | 207 | 0.696 | 0.389 | 0.499 | 0.900 | ¥0 incremental |
| Response pattern (strong) | ≥12 | 102 | 0.804 | 0.222 | 0.347 | 0.968 | ¥0 incremental |
| Response pattern (unanimous) | ≥15 | 41 | 0.854 | 0.095 | 0.170 | 0.990 | ¥0 incremental |
| Response pattern (post-hoc upper bound) | ≥3 | 435 | 0.586 | 0.689 | 0.634 | 0.714 | ¥0 incremental |

## Strict explicit-defect endpoint (`expert` excluded)

| System | Threshold | TP | FP | FN | TN | P | R | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BenchAudit | review candidate | 196 | 86 | 142 | 544 | 0.695 | 0.580 | 0.632 |
| Response pattern (primary) | ≥8 | 137 | 63 | 201 | 567 | 0.685 | 0.405 | 0.509 |
| Response pattern (strong) | ≥12 | 80 | 20 | 258 | 610 | 0.800 | 0.237 | 0.365 |
| Response pattern (unanimous) | ≥15 | 35 | 6 | 303 | 624 | 0.854 | 0.104 | 0.185 |
| Response pattern (post-hoc upper bound) | ≥3 | 236 | 180 | 102 | 450 | 0.567 | 0.698 | 0.626 |

## Endpoint summary at primary k≥8

| Endpoint | Positives | Candidates | P | R | F1 |
|---|---:|---:|---:|---:|---:|
| `legacy_non_ok_including_expert` | 370 | 207 | 0.696 | 0.389 | 0.499 |
| `strict_explicit_defect` | 338 | 200 | 0.685 | 0.405 | 0.509 |
| `gold_related` | 181 | 163 | 0.613 | 0.552 | 0.581 |
| `wrong_groundtruth_only` | 106 | 144 | 0.562 | 0.764 | 0.648 |

## Overlap and evidence boundary

At k≥8: both systems flag 141 items; response-pattern only 66; BenchAudit only 151.

Separately, the deterministic T1 scan confirmed 7 byte-identical duplicate-choice items, including 6 labelled `ok`. Those prove that the supervised labels are incomplete; a mechanically confirmed `ok` item must not be interpreted as a genuine detector false positive merely because Redux says `ok`.

The response panel is not 15 independent experts, and this population was used during BenchAudit development. The comparison is an in-sample baseline, not a generalization result. The post-hoc best threshold is an optimistic upper bound and is not the primary result.
