# MMLU-Redux gold-correction score impact

> Outcome-inspected deterministic reanalysis; not a prospective preregistration.
> Inference is conditional on the fixed 15-model panel.

## Frozen panel

- Items: 1000 (101 changed gold labels)
- Models: 15
- Subjects: 57
- Model pairs: 105

## Model scores

| Model | Original | Corrected | Gain | 95% item-bootstrap CI | Rank |
|---|---:|---:|---:|---:|---:|
| deepseek | 0.803 | 0.867 | +0.064 | [+0.048, +0.080] | 1 → 1 |
| google__gemini-2.5-flash | 0.770 | 0.830 | +0.060 | [+0.044, +0.076] | 2 → 2 |
| openai__gpt-4o | 0.745 | 0.800 | +0.055 | [+0.039, +0.072] | 3 → 3 |
| qwen__qwen-2.5-72b-instruct | 0.734 | 0.782 | +0.048 | [+0.031, +0.065] | 4 → 4 |
| openai__gpt-4.1-mini | 0.715 | 0.769 | +0.054 | [+0.038, +0.070] | 5 → 5 |
| amazon__nova-pro-v1 | 0.709 | 0.758 | +0.049 | [+0.032, +0.066] | 6 → 6 |
| microsoft__phi-4 | 0.705 | 0.755 | +0.050 | [+0.033, +0.067] | 7 → 7 |
| meta-llama__llama-3.1-70b-instruct | 0.697 | 0.750 | +0.053 | [+0.037, +0.070] | 8 → 8 |
| mistralai__mistral-small-24b-instruct-2501 | 0.692 | 0.743 | +0.051 | [+0.035, +0.067] | 9 → 10 |
| meta-llama__llama-3.3-70b-instruct | 0.689 | 0.744 | +0.055 | [+0.039, +0.071] | 10 → 9 |
| openai__gpt-4o-mini | 0.679 | 0.728 | +0.049 | [+0.033, +0.066] | 11 → 11 |
| cohere__command-r-08-2024 | 0.638 | 0.673 | +0.035 | [+0.019, +0.052] | 12 → 12 |
| qwen__qwen-2.5-7b-instruct | 0.634 | 0.667 | +0.033 | [+0.017, +0.050] | 13 → 13 |
| meta-llama__llama-3.1-8b-instruct | 0.593 | 0.629 | +0.036 | [+0.020, +0.052] | 14 → 14 |
| mistralai__mistral-nemo | 0.582 | 0.616 | +0.034 | [+0.017, +0.051] | 15 → 15 |

## Ranking and pairwise effects

- Kendall tau: **0.981**
- Maximum rank shift: **1**
- Top-1 changed: **false**
- Expanded / contracted / unchanged gaps: **83 / 20 / 2**
- Rank-flipped pairs: **1**
- Mean signed relative gap change: **+11.294%** (95% item-bootstrap CI [-1.929%, +33.279%])
- Mean absolute relative gap change (descriptive): 19.497%

## Fixed-panel association

Spearman(original accuracy, correction gain) = **0.785**; paired item-bootstrap 95% interval [0.467, 0.900]. This is descriptive for the fixed, non-independent model panel; no model-population p-value is reported.

## Interpretation boundary

In this panel, erroneous gold labels usually compressed model score gaps: most gaps expanded after correction. The ranking itself was nearly unchanged. This analysis does not establish novelty, cross-benchmark generality, or that any fixed percentage of model comparisons is unreliable.

