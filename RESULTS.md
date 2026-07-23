# BenchCore Experiment Results

> Updated evidence-policy summary: 2026-07-23.
>
> Older tables below preserve the labels emitted by their historical runners.
> Under the current centralized promotion policy, an LLM vote or a
> checker-local `review_only=False` flag is not sufficient for automatic
> confirmation. Candidate precision/recall metrics remain valid as supervised
> ranking metrics, but legacy “confirmed” rows must not be interpreted as
> proof-sound automatic confirmation unless their evidence is revalidated by
> the current policy.

## Current headline results

### Archived-response candidate triage

MMLU-Redux uses 1,000 item-level responses from 15 models. The main evaluation
compares 181 third-party objective defects with 630 `ok` items.

| Method | Average precision |
|---|---:|
| BenchAudit candidate risk | 0.573 |
| Multi-model item error rate | 0.634 |
| BenchAudit + error rate | **0.734** |
| BenchAudit + psychometric fusion | 0.740 |

The 0.006 overall advantage of the psychometric variant did not generalize
across subjects:

- paired subject mean delta against the simple fusion: `-0.0275`;
- bootstrap 95% CI: `[-0.0821, +0.0245]`;
- subject wins/ties/losses: `6/1/12`;
- positive grouped folds: `3/5`.

The production implementation therefore uses the simpler response-error
fusion. All behavior-derived rows are `review-only`; response error is a
triage signal, not a defect probability.

The production code is:

- `benchcore/response_triage.py`;
- `benchcore.cli triage-responses`;
- `tests/test_response_triage.py`.

Frozen analysis protocols are under `experiments/response_triage/`.

### Ranking sensitivity

On the same 1,000-item MMLU-Redux subset and 15-model leaderboard, removing 181
third-party objective defects produced:

- global Kendall's tau: **0.981**;
- maximum rank change: **1**;
- one adjacent global rank swap;
- no Top-1 change.

Per-subject winner changes are not used as headline evidence: equal-size random
deletion controls showed that small subject subsets and tie-breaking can
produce similar churn.

### Correlated prompt-view fallback

On all 300 SVAMP-Platinum items, eight fixed DeepSeek prompt views produced:

| Method | AP | P@20 | P@50 | R@50 |
|---|---:|---:|---:|---:|
| Static BenchAudit | 0.189 | 0.245 | 0.169 | 0.222 |
| Prompt-view error rate | **0.554** | **0.746** | 0.477 | 0.628 |
| Preregistered audit + view fusion | 0.528 | 0.600 | **0.548** | **0.722** |

The views had pairwise correctness agreement 0.956 and are not independent
models. The frozen fusion gate failed, so the fallback is retained only as a
provenance-labelled review signal.

A behavior-first cascade then sent only the top 100/300 items to semantic LLM
auditors. It improved P@20 from 0.700 to 0.750 but reduced AP from 0.589 to
0.581; the semantic gate was not promoted into automatic reranking.

### Workspace counterfactual evaluation

The official filesystem judge study completed 53/53 valid evaluation units
over 11 usable baseline tasks:

- deleting the complete output caused a significant drop in 11/11 tasks;
- mean whole-output deletion delta: **-54.7 percentage points**;
- reward-gaming self-claims were rewarded in 0/5 controls;
- 6/11 identical-output independent re-evaluations differed by more than
  3 percentage points;
- identical-output mean absolute delta: **7.3 percentage points**.

The result supports deterministic, rubric-targeted counterfactual testing for
obvious missing artifacts. Fine-grained single-judge deltas remain below the
observed judge-noise floor and are not automatically confirmed.

### Terminal paired evaluation

In the 31-task enriched paired subset:

| Method | Recall | F1 |
|---|---:|---:|
| Deterministic | 0.588 | 0.741 |
| Paired only | 0.118 | 0.211 |
| Union | 0.647 | 0.786 |

Although the union F1 increased, the preregistered paired-method retention gate
became mathematically unreachable and the experiment was stopped. The paired
method was not promoted into the default pipeline. `defect_supported` and
`repair_localized` are reported separately.

### Execution-evidence status

Historical DS-1000 runs remain useful for manually reviewed evaluator
counterexamples, but shared execution/adjudication drivers are capped at
`review`. A successful process or sandbox run alone is not a trusted proof.
Automatic confirmation requires an independently attested execution boundary
and revalidated proof prerequisites.

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
