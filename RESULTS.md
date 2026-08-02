# BenchCore Experiment Results

> **Evidence-policy note (2026-07-14):** older tables preserve the labels used by
> their historical experiment code. In particular, an LLM vote or a checker-local
> `review_only=False` flag is **not** a current automatic confirmation. The current
> centralized policy confirms only an exact, versioned proof tuple whose payload is
> revalidated; model judgments remain review signals and coverage failures remain
> unknown. Candidate P/R/F1 below are still valid supervised ranking metrics, but
> legacy “confirmed tier” rows must not be interpreted as proof-sound precision.

## Workspace-Bench release experiments (2026-07-14)

The release protocol separates controlled structural recall, semantic evidence
binding, and findings on unmodified data.  Full interpretation and limitations:
[`BENCHAUDIT_NEAR_FINAL_WORKSPACEBENCH_EXPERIMENT_20260714_zh.md`](BENCHAUDIT_NEAR_FINAL_WORKSPACEBENCH_EXPERIMENT_20260714_zh.md).

### Controlled structural invariants

| Suite | Source tasks | Paired mutations | Exact recall | Paired discrimination | Extra / duplicate alarms |
|---|---:|---:|---:|---:|---:|
| Workspace Full | 388 | 1,940 | 1,940/1,940 = **1.000** | 1,940/1,940 = **1.000** | 0 / 0 |
| Workspace Lite | 100 | 500 | 500/500 = **1.000** | 500/500 = **1.000** | 0 / 0 |

At pair level, the Full 95% Wilson lower bound is 0.9980 and the Lite lower
bound is 0.9924.  Five rows from the same source task are correlated; the more
conservative all-five-perfect source-task lower bounds are 0.9902 (388/388) and
0.9630 (100/100).  These are five co-designed deterministic schema/artifact
operators—a conformance/regression result, not natural-defect prevalence,
held-out root-cause recall, or arbitrary semantic recall.  The Full unmutated
side had no natural alarm.  The Lite unmutated side had one review-level
output-generator heuristic alarm; hidden-oracle equivalence and score impact
remain unproven, and it is not an injected-target false positive.

### Paired semantic-grounding challenge

Fifty real Lite source tasks × four objective interventions produced 200
clean/mutant pairs and 400 isolated single-rubric decisions.

| Decision layer | Mutant recall | Clean FP | Paired | Strict paired | Uncertain |
|---|---:|---:|---:|---:|---:|
| Raw LLM scanner | 1.000 | 0.170 | **0.830** | **0.830** | 0/400 |
| Citation-grounded model, certificate excluded | 0.570 | 0.050 | **0.540** | **0.395** | 137/400 |
| Objective certificate | 1.000 | 0.000 | **1.000** | **1.000** | 0/400 |
| Certificate-aware controlled decision | 1.000 | 0.000 | **1.000** | **1.000** | 0/400 |

The pair-level certificate-aware 95% Wilson interval is [0.981, 1.000].  The
200 pairs are clustered within 50 source tasks: all four operators were correct
for 50/50 sources (source-level Wilson [0.929, 1.000]), versus 25/50 for raw LLM
and 0/50 for citation-grounded decisions.  The challenge generator and the
resolver share four exact atomic grammars, so this is certificate conformance,
not paraphrase generalization.  The objective-certificate and certificate-aware
rows use the same decision path and are not independent replications.

The result applies only to four narrow task/contract/complete-inventory
predicates. Input inventory was complete for 50/50 tasks, while complete
attachment-content coverage was only 24/50; therefore it must not be presented
as 100% attachment-semantic or arbitrary-benchmark recall.  The final
source-hash gate and exact-cache validation both passed.  See
[`ANALYSIS_zh.md`](reports/workspace_semantic_challenge_lite100_20260714_v3_final/ANALYSIS_zh.md).

### Unmodified Workspace data

| Suite | Coverage ledger | Confirmed | Review signals | Coverage unknown |
|---|---:|---:|---:|---:|
| Lite CN 100 | 1,300 planned; 800 completed; 500 ineligible | 0 | 1 suspected visible output-generator script | 0 |
| Full 388 | 5,044 planned; 3,104 completed; 1,940 ineligible | 0 | 2 temporal-wording candidates | 0 |

These three rows are review candidates, not verified defects.  Both package
plans also contain 7 skipped and 5 unsupported methods (alongside 8 executed
and 5 ineligible methods), so selected-checker `unknown=0` is not full-package
coverage.  Likewise, `completed_no_finding` is a checker outcome and not a clean
benchmark verdict.  The controlled Lite runs use `lite_100.jsonl` (SHA prefix
`fe59c596`), while the unmodified Lite-CN audit uses a separately pinned local
representation (SHA prefix `89be51be`); their item-level results must not be
silently pooled.

## Ablation Baselines — Four-Way Comparison

Four systems compared on two supervised datasets (SVAMP-Platinum n=100; MMLU-Redux n=1000).
All use DeepSeek as the underlying LLM where applicable.

| System | What it uses | SVAMP P | SVAMP R | SVAMP F1 | MMLU P | MMLU R | MMLU F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| **Rules-Only** | Static checkers, no LLM | 0.000 | 0.000 | 0.000 | 0.714 | 0.014 | 0.027 |
| **Naive LLM** | Single-pass LLM, no taxonomy, no rules | 0.897 | 0.684 | 0.776 | 0.808 | 0.478 | 0.601 |
| **LLM + Taxonomy** | Single-pass LLM with defect taxonomy in prompt | 0.917 | 0.579 | 0.710 | 0.775 | 0.503 | 0.610 |
| **BenchCore** | Static rules + structured LLM decomposition | **0.860** | **0.974** | **0.914** | **0.641** | **0.686** | **0.663** |

**Key findings**:
- Rules-Only achieves near-zero recall on SVAMP (all defects require arithmetic reasoning or LLM) and R=0.014 on MMLU (only `missing_context` structural flags). This establishes that LLM is essential, not optional.
- LLM+Taxonomy vs Naive LLM: taxonomy *hurts* on SVAMP (R 0.684→0.579, F1 −0.066) but marginally *helps* on MMLU (R 0.478→0.503, F1 +0.009). On SVAMP the taxonomy causes the LLM to require a category match rather than holistically flagging quality issues, suppressing legitimate detections. The net effect across datasets is negligible (+/−0.005 F1).
- BenchCore vs best single-pass LLM: +0.138 F1 on SVAMP (+0.290 recall), +0.062 F1 on MMLU (+0.208 recall). The recall gains confirm that structured decomposition (separate oracle, option, and question auditors) finds defects invisible to holistic single-pass classification regardless of whether a taxonomy is provided.

**Ablation interpretation**: Adding a taxonomy to a flat prompt does not replicate BenchCore's benefit; the gain comes from *decomposition* (asking the LLM about specific artifact dimensions in sequence) and *programmatic evidence* (quantity consistency, differential candidates), not from vocabulary enrichment.

---

## Baseline Comparison (Original)

**Naive LLM baseline**: single-pass prompt asking only "does this item have a quality issue?" — no
defect taxonomy, no artifact decomposition, no programmatic rules.
**BenchCore**: structured multi-checker pipeline (candidate tier; priority tier for GSM8K).

| Dataset | System | P | R | F1 | ΔF1 | ΔRecall |
|---|---|---:|---:|---:|---:|---:|
| SVAMP | Naive LLM (DeepSeek) | 0.897 | 0.684 | 0.776 | — | — |
| SVAMP | **BenchCore v5** | 0.860 | **0.974** | **0.914** | **+0.138** | **+0.290** |
| GSM8K | Naive LLM (DeepSeek) | 0.750 | 0.900 | 0.818 | — | — |
| GSM8K | **BenchCore** (priority) | 0.714 | **1.000** | **0.833** | +0.015 | +0.100 |
| MMLU-Redux (n=200) | Naive LLM (DeepSeek) | 0.845 | 0.490 | 0.620 | — | — |
| MMLU-Redux (n=200) | **BenchCore** (candidate) | 0.740 | **0.770** | **0.755** | **+0.135** | **+0.280** |
| MMLU-Redux (n=1000) | Naive LLM (DeepSeek) | 0.808 | 0.478 | 0.601 | — | — |
| MMLU-Redux (n=1000) | **BenchCore** (candidate) | 0.641 | **0.686** | **0.663** | **+0.062** | **+0.208** |

**Key finding**: The naive LLM detects obvious defects (wrong arithmetic, clearly bad options) but
misses subtle structural defects requiring multi-step reasoning across the full item:
- SVAMP: naive LLM finds 26/38 defects; BenchCore finds 37/38 (+11 via quantity/event-state checkers)
- MMLU:  naive LLM finds 49/100 defects; BenchCore finds 77/100 (+28 via option/gold auditors)
- GSM8K: gap is small (+0.015 F1) because GSM8K defects are mostly wrong arithmetic — solvable in one pass

For MMLU-Redux, BenchCore also outperforms the best published automated result from Gema et al. (2024):
Claude 3 Opus + RAG achieved F2=41.92 (P≈14%, R≈84%); BenchCore: P=74%, R=77%, F1=75.5%.

---

## Main Results Table

All six benchmark pilots. Supervised rows (†) have Platinum human defect labels and report P/R/F1.
Audit-only rows report detection counts only.

| Dataset | Domain | Items | Known defects | Flagged | Confirmed | Cand P | Cand R | Cand F1 | Priority P | Priority R | Priority F1 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SVAMP-Platinum † | Math | 100 | 38 | 43 | 20 | 0.860 | 0.974 | **0.914** | 0.897 | 0.684 | 0.776 |
| SVAMP-Platinum (repro) † | Math | 100 | 38 | 43 | — | 0.837 | 0.947 | 0.889 | 0.862 | 0.658 | 0.746 |
| GSM8K-Platinum † | Math | 100 | 10 | 25 | 9 | 0.400 | 1.000 | 0.571 | 0.714 | 1.000 | **0.833** |
| MMLU-Redux † | Multi-choice | 200 | 100 | 104 | 24 | 0.740 | 0.770 | **0.755** | 0.860 | 0.490 | 0.624 |
| ARC-Challenge | Multi-choice | 200 | — | 22 | 3 | — | — | — | — | — | — |
| ASDiv | Math | 100 | — | 5 | 1 | — | — | — | — | — | — |
| WikiTableQuestions | Table QA | 100 | — | 30 | 0 | — | — | — | — | — | — |

† Supervised evaluation against Platinum human defect labels.

**Three tiers**:
- `candidate`: any signal (high recall)
- `priority_candidate`: confirmed OR high-confidence review (balanced)
- `confirmed`: programmatic rules agree (high precision); not shown above as separate columns

**Manual verification results** (audit-only datasets):
- ARC-Challenge: 11 items verified → 4 true positives (2 multi-answer, 1 wrong gold, 1 unit error)
- ASDiv: 5 items verified → 2 true positives (discount scope ambiguity, story inconsistency)

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

Each checker family independently increases recall. Prompt refinement in v5 recovers precision without sacrificing recall, yielding the best F1.

---

## Review Budget Curves

Fraction of items reviewed to reach a given recall level vs. random baseline.

| Dataset | Budget for Recall=0.77 | Budget for Recall=1.0 | Efficiency gain |
|---|---:|---:|---:|
| SVAMP | 22% | **43%** | 2.3× |
| GSM8K | 5% | **15%** | **6.7×** |
| MMLU-Redux | 52% | — (max 77% at 52%) | — |

GSM8K achieves full recall by reviewing only 15% of items (**6.7× efficiency gain** over random review).

---

## SVAMP False Positive Analysis

Of the 6 candidate false positives in the v5 run:

| Category | Count |
|---|---:|
| True false positive (genuine system error) | 2 |
| Clean label but real quality issue missed by Platinum | 4 |
| Presentation artifact | 1 |

Adjusted precision reclassifying missed-issue FPs as TPs: **(37+4)/43 = 0.953**
Reported supervised candidate precision: **0.860**

This suggests BenchCore finds real defects beyond what the Platinum annotation captured.

---

## Majority Voting (n=3) Results

Voting uses 3 LLM calls at temperature=0.3 per key decision point (blind solver, question clarity, gold auditor, option set auditor). A defect is flagged at `review_only=False` only when ≥2/3 calls agree; 1/3 agreement keeps `review_only=True`.

| Dataset | System | Conf P | Conf R | Conf F1 | Cand P | Cand R | Cand F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| SVAMP n=100 | BenchCore v5 (no voting) | 0.900 | 0.474 | 0.621 | 0.860 | 0.974 | 0.914 |
| SVAMP n=100 | **BenchCore + vote3** | **0.897** | **0.684** | **0.776** | 0.809 | **1.000** | 0.894 |
| MMLU n=1000 | BenchCore (no voting) | 0.875 | 0.210 | 0.339 | 0.641 | 0.686 | 0.663 |
| MMLU n=1000 | **BenchCore + vote3** | **0.811** | **0.268** | **0.402** | 0.629 | **0.751** | **0.685** |

**Voting findings (both datasets)**:
- SVAMP confirmed F1: 0.621 → **0.776** (+0.155); candidate recall: 0.974 → **1.000** (perfect)
- MMLU confirmed F1: 0.339 → **0.402** (+0.063); candidate recall: 0.686 → **0.751** (+0.065)
- `llm_question_clarity` violations can now be promoted to `review_only=False` (previously hardcoded `True`), the main driver of confirmed recall improvement
- Precision tradeoff: confirmed P 0.875→0.811 on MMLU (voting promotes borderline items that turn out to be FP)
- `multiple_correct_answers` confirmed recall remains 0.077 — this defect type is detected by `llm_option_applicability` which is always `review_only=True` and was not covered by voting; future improvement opportunity

---

## Confirmed Tier Metrics

Full three-tier breakdown for reference.

| Dataset | Conf P | Conf R | Conf F1 | Cand P | Cand R | Cand F1 | Priority P | Priority R | Priority F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SVAMP v5 | 0.900 | 0.474 | 0.621 | 0.860 | 0.974 | **0.914** | 0.897 | 0.684 | 0.776 |
| SVAMP vote3 | 0.897 | 0.684 | **0.776** | 0.809 | 1.000 | 0.894 | 0.909 | 0.789 | 0.845 |
| SVAMP repro | 0.826 | 0.500 | 0.623 | 0.837 | 0.947 | 0.889 | 0.862 | 0.658 | 0.746 |
| GSM8K | 0.667 | 0.600 | 0.632 | 0.400 | 1.000 | 0.571 | 0.714 | 1.000 | **0.833** |
| MMLU-Redux (n=1000) | 0.875 | 0.210 | 0.339 | 0.641 | 0.686 | **0.663** | 0.727 | 0.503 | 0.595 |
| MMLU vote3 (n=1000) | 0.811 | 0.268 | **0.402** | 0.629 | 0.751 | **0.685** | 0.720 | 0.527 | 0.608 |

---

## Execution-Grounded Evaluator Audit (DS-1000 pilot, 2026-07-13)

> **Superseded automation status (2026-07-14):** the two DS-1000 cases below
> remain valuable manually verified findings, but the original run must not be
> cited as sound automatic confirmation. A second audit found that the old
> driver did not always replay identical harness inputs, treated finite-sample
> output proximity as equivalence, and ran locally without a real sandbox. The
> implementation now requires exact typed equality, serialized same-input
> replay, explicit semantic contracts, and an isolated runner. A further adversarial
> test showed that evaluator code and numeric adjudication still share one interpreter,
> so harness code can monkeypatch the comparator. Current execution observations are
> therefore forcibly capped at `review` until a separate trusted adjudicator exists;
> the old report predates these gates and has not been rerun.

New tier: `benchcore/evaluator_execution.py` — the LLM only *generates* probe solutions;
every verdict is decided by real execution (differential validation on the harness's own
test inputs, asymmetric strict/loose comparators so both confirmation directions are
conservative). Full report: `reports/ds1000_execution_audit.md`.

**Real data (DS-1000 Pandas+Numpy, 60 items, 411 probes)**: 141 validated equivalent
probes (0 rejected), 190 validated mutants → 186 killed, 4 survived. Hand-verified:
**2 genuine evaluator defects** — id=11 (harness cannot detect whether the timezone was
actually removed, the very property the task tests) and id=300 (`assert_allclose`
broadcasting makes it shape-blind); id=308 was a method FP (property-based comparator
ignores `ans`; task admits many outputs) → fixed with an automatic property-based guard
that downgrades such survivals to review. Plus 4 `test_string` surface-strictness reviews.

**Injected-defect validation (20 clean items × 3 evaluator-defect classes, probes
cache-paired with the clean condition)**:

| Injected defect | Detected |
|---|---:|
| neutralize_comparator | 20/20 (100%) |
| reject_gold | 20/20 (100%) |
| implementation_assert | 13/20 (65%) |

`implementation_assert` misses occur when the pinned token is the natural idiom that all
generated equivalents also use — detection depends on probe diversity (honest recall floor
with n=3 equivalents).
