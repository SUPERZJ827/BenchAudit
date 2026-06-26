# BenchCore Experiment Results

## Main Results Table

Supervised experiments with Platinum human defect labels as ground truth.
Metrics: P = Precision, R = Recall, F1.

| Dataset | Items | Defects | Conf P | Conf R | Conf F1 | Cand P | Cand R | Cand F1 | Priority P | Priority R | Priority F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SVAMP-Platinum | 100 | 38 | 0.900 | 0.474 | 0.621 | 0.860 | 0.974 | **0.914** | 0.897 | 0.684 | 0.776 |
| SVAMP-Platinum (repro) | 100 | 38 | 0.826 | 0.500 | 0.623 | 0.837 | 0.947 | 0.889 | 0.862 | 0.658 | 0.746 |
| GSM8K-Platinum | 100 | 10 | 0.667 | 0.600 | 0.632 | 0.400 | 1.000 | 0.571 | 0.714 | 1.000 | **0.833** |
| MMLU-Redux | 200 | 100 | 0.875 | 0.210 | 0.339 | 0.740 | 0.770 | **0.755** | 0.860 | 0.490 | 0.624 |

**Three tiers**:
- `confirmed`: high precision (programmatic rules agree)
- `candidate`: high recall (any signal)
- `priority_candidate`: balanced (confirmed OR high-confidence review)

---

## Ablation Study (SVAMP, Candidate tier)

Each row adds one checker family to the previous configuration.

| Configuration | Auditors active | Cand P | Cand R | Cand F1 | Conf P | Conf R | Conf F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| v1: Task integrity | integrity | 0.727 | 0.632 | 0.676 | 1.000 | 0.079 | 0.146 |
| v2: +Quantity consistency | +quantity | 0.800 | 0.737 | 0.767 | 0.909 | 0.263 | 0.408 |
| v3: +Blind semantics | +blind\_semantics | 0.842 | 0.842 | 0.842 | 0.818 | 0.237 | 0.367 |
| v4: +Event-state | +event\_state | 0.818 | 0.947 | 0.878 | 0.783 | 0.474 | 0.590 |
| v5: +Prompt refinement | +prompt\_fix | **0.860** | **0.974** | **0.914** | **0.900** | **0.474** | **0.621** |

Key insight: each checker family independently increases recall. Prompt refinement in v5 recovers precision without sacrificing recall.

---

## Review Budget Curves

Fraction of items that must be reviewed to reach a given recall level, compared to random baseline.

| Dataset | Budget for Recall=0.77 | Budget for Recall=1.0 | Random baseline for Recall=1.0 |
|---|---:|---:|---:|
| SVAMP | 22% | **43%** | 100% |
| GSM8K | 5% | **15%** | 100% |
| MMLU-Redux | 52% | — (max 77%) | — |

GSM8K achieves full recall by reviewing only 15% of items, a **6.7× efficiency gain** over random review.

---

## Audit-Only Benchmarks (no Platinum labels)

These pilots demonstrate BenchCore on unlabeled data. No P/R/F1 reported.

| Dataset | Items | Affected | Confirmed | Top defect types |
|---|---:|---:|---:|---|
| ASDiv | 100 | 5 | 1 | ambiguous_goal (5), no_correct_answer (1) |
| WikiTableQuestions | 100 | 30 | 0 | presentation_corruption (17), ambiguous_goal (10) |
| ARC-Challenge | 200 | 22 | 3 | multiple_correct_answers_risk (11), multiple_correct_answers (4) |

**Manual verification of ARC-Challenge flags** (11 items inspected):
- 4 confirmed true positives: 2 multiple-correct-answer questions, 1 wrong gold (biodiesel labeled as biogas), 1 unit error (current stated in ohms)
- 7 false positives: system over-flagged well-formed items

**Manual verification of ASDiv flags** (5 items inspected):
- 2 confirmed true positives: discount scope ambiguity, washing-machine story inconsistency
- 1 weak positive: "serve equally" floor-division convention
- 2 false positives: gold=0.63 (dollars) is correct, mean 5.666...→5.7 is correct 1 d.p. rounding

---

## SVAMP False Positive Analysis

Of the 6 candidate false positives in the v5 run:

| Category | Count |
|---|---:|
| True false positive (genuine system error) | 2 |
| Clean label but real quality issue (missed by Platinum annotators) | 4 |
| Presentation artifact | 1 |

Adjusted precision (reclassifying real-quality-issue FPs as TPs): **(37+4)/43 = 0.953**
Reported supervised candidate precision: **0.860**
