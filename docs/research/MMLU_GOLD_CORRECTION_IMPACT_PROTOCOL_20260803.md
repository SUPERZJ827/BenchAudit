# MMLU-Redux gold-correction impact: frozen reanalysis protocol

> Frozen: 2026-08-03 (Asia/Singapore)  
> Phase: P0 of the ICLR measurement-study plan  
> API budget: 0  
> Outcome inspected before freeze: **true**

## 0. Claim status

This is a reproducibility and uncertainty-analysis protocol for an already
observed result. It is **not** a prospective preregistration. Before this file
was frozen, the authors had already seen that 101 labels differ, all 15 model
scores increase, the ranking Kendall tau is approximately 0.981, and correction
gain is associated with original accuracy. No p-value from this reanalysis may
be described as confirmatory evidence for a preregistered hypothesis.

The analysis is conditional on one frozen panel of 15 models and their archived
single-run answers. The models are related and are not a random sample from a
model population. Item bootstrap intervals quantify uncertainty over the fixed
1,000-item sample; they do not make the 15 models independent.

## 1. Frozen inputs

| Input | SHA-256 |
|---|---|
| `/home/zhoujun/llmdata/datasets/mmlu_redux/mmlu_redux_all_5700_finegrained.jsonl` | `0c8ccf09cbb422e4cd999524aa581e3bd3040c9dcd75f1c0b2408a49ef66b3d4` |
| `experiments/mmlu_redux_pilot1000.jsonl` | `70cc9ee184db4017b323bda03061f7c3d56e57ad1ab4b1a3415263fd664072b8` |
| `reports/ranking_impact/answers/amazon__nova-pro-v1.jsonl` | `75c8f1239ac93b248594799beea47f9642743db0b30b07c1fb929a60420186e7` |
| `reports/ranking_impact/answers/cohere__command-r-08-2024.jsonl` | `a550b7dd005294267c769f860297b84dbcc9607bbc52fbbebd7918e71f4cf4be` |
| `reports/ranking_impact/answers/deepseek.jsonl` | `fa7acdf241df1a01eee1eda1a00e645c605aee503b0416edd726d089527b6101` |
| `reports/ranking_impact/answers/google__gemini-2.5-flash.jsonl` | `2bc96f33b908d22b4703f91e33c598eafa03b6be6a3516ca9c92fdd8fb400ec9` |
| `reports/ranking_impact/answers/meta-llama__llama-3.1-70b-instruct.jsonl` | `c19b0936c1ea6723f2f7169a0793d622eb7a43a14bd816d90c9c221d83efa72a` |
| `reports/ranking_impact/answers/meta-llama__llama-3.1-8b-instruct.jsonl` | `afc4ad5b9f76a08ee5929771880d35019e2b98055a30711200addf5500ccaf19` |
| `reports/ranking_impact/answers/meta-llama__llama-3.3-70b-instruct.jsonl` | `2d9ee021748d2501754cac714faafb09b7159b419a6ef11eaded46c86e5edf44` |
| `reports/ranking_impact/answers/microsoft__phi-4.jsonl` | `ca82caa157fd6816368e80bfd805b50943e5063d80108375c20215c4d6710a20` |
| `reports/ranking_impact/answers/mistralai__mistral-nemo.jsonl` | `f024d64e3c14fa07614e930906715af54f8394bb50eaade17fc4dcdfe789c6a8` |
| `reports/ranking_impact/answers/mistralai__mistral-small-24b-instruct-2501.jsonl` | `7d28319ac1b4b45bdfb80bfb786ce1c443c75e824043959321672b2ca28760bf` |
| `reports/ranking_impact/answers/openai__gpt-4.1-mini.jsonl` | `ad595880ab90cbe09411c96eba97f6e533101ebf293d66ae3f37c1a6fba3bf42` |
| `reports/ranking_impact/answers/openai__gpt-4o-mini.jsonl` | `7e122b072aba7874815f75c62203b628970ad003ed86776a1ab1b9ba358cdcd4` |
| `reports/ranking_impact/answers/openai__gpt-4o.jsonl` | `9b274b186d8e60a03ece47b032823f0d79d3bc879c30152b91f340a103515ec9` |
| `reports/ranking_impact/answers/qwen__qwen-2.5-72b-instruct.jsonl` | `c043efc588e2166a525e42f6093c7469aa3f08a7517d5d1126be5bcefa072465` |
| `reports/ranking_impact/answers/qwen__qwen-2.5-7b-instruct.jsonl` | `85c50927156ca133b0e09cad0d72a9fc71bd75dcbffdd495451686ccac22b04c` |

The implementation must fail closed on a missing file or hash mismatch. The
dataset path is a command-line input and must not be hard-coded as a portable
repository path.

## 2. Input integrity gates

The run is `NOT_IDENTIFIABLE_INPUT` unless all conditions hold:

1. the pilot contains exactly 1,000 unique item IDs;
2. exactly the 15 answer files above are present and each has exactly those
   1,000 unique IDs;
3. `pred`, `gold`, `correct`, and `subject` exist for every answer row;
4. each answer row's `gold` and `subject` match the frozen pilot/dataset row;
5. `correct == (pred == gold)` for every row;
6. every pilot ID joins to exactly one full-dataset row;
7. a missing/blank `metadata.verified_gold` is treated as unchanged gold, not
   as a corrected answer;
8. original inputs remain byte-identical after execution.

## 3. Score definitions

For item `i` and model `m`:

```text
old_correct[i,m] = 1(pred[i,m] == original_gold[i])
new_correct[i,m] = 1(pred[i,m] == effective_verified_gold[i])
effective_verified_gold[i] = verified_gold[i] if nonblank else original_gold[i]
```

For each model, report `old_accuracy`, `corrected_accuracy`, and
`correction_gain = corrected_accuracy - old_accuracy`.

Rank models by descending accuracy, breaking an exact tie by model slug. Report
Kendall tau between the two total orders, maximum rank shift, top-1 change, and
every changed rank. The tie break is an operational total-order convention and
must not be interpreted as a scientific difference between tied models.

## 4. Pairwise definitions

For each unordered model pair, orient the pair using the **full-sample original
ranking**. Let `H` be the originally higher-scoring model and `L` the lower:

```text
g0 = old_accuracy[H] - old_accuracy[L]
g1 = corrected_accuracy[H] - corrected_accuracy[L]
gap_change = g1 - g0
relative_gap_change = gap_change / g0   (only if g0 > 0)
```

Use exact integer correct counts for comparisons; do not compare rounded table
values. Report these mutually interpretable quantities:

- `expanded`: `gap_change > 0`;
- `contracted_including_flips`: `gap_change < 0`;
- `unchanged`: `gap_change == 0`;
- `rank_flipped`: `g1 < 0` (a subset of contracted pairs);
- mean and median signed relative gap change over pairs with `g0 > 0`;
- mean absolute relative gap change, explicitly labelled descriptive.

The maximum correction-gain span may be reported as a sensitivity diagnostic,
but it must never be used to label every smaller original gap "unreliable".
Pair-specific `abs(gap_change)` and its interval are the relevant quantities.

## 5. Bootstrap uncertainty

- 10,000 replicates;
- NumPy `Generator(PCG64)` seed `20260803`;
- stratify by `subject`;
- within each subject, sample items with replacement to the original subject
  count;
- use the identical resampled item indices for every model, preserving the
  paired cross-model structure;
- model-pair orientation remains fixed from the observed original ranking;
- percentile 95% intervals use empirical 2.5% and 97.5% quantiles with NumPy's
  default linear quantile interpolation.

Report 95% intervals for every model correction gain, every pair gap change,
the mean signed relative gap change, and Spearman correlation between original
accuracy and correction gain. Spearman is descriptive and conditional on the
fixed panel; no population-level p-value is a primary result. Pairwise 95%
intervals are exploratory and are not simultaneous family-wise guarantees.

## 6. Primary interpretation gates

The output may claim only:

- whether original labels compress gaps **in this fixed panel**, using the
  observed expanded/contracted counts and bootstrap interval for mean signed
  relative change;
- whether higher observed accuracy is descriptively associated with larger
  correction gain, with the fixed-panel and dependence caveats;
- the observed ranking stability or change.

It must not claim novelty, cross-benchmark generality, model-population
inference, or that a percentage of comparisons is "unreliable".

## 7. Outputs and determinism

Write new files only under
`reports/mmlu_gold_correction_impact_20260803/`:

- `analysis.json`: stable complete numerical result;
- `REPORT.md`: human-readable report generated from `analysis.json`;
- `receipt.json`: input hashes, code/protocol hashes, environment, zero-API
  declaration, integrity-gate results, and output hashes.

No timestamp, elapsed time, PID, temporary path, hostname, or unordered mapping
may enter `analysis.json` or the stable portion of the receipt. Run twice in
separate empty output directories; `analysis.json` and `REPORT.md` must be
byte-identical. The final committed directory is materialized only after this
check. Historical reports are read-only.

## 8. Tests

At minimum:

1. changed and unchanged gold scoring;
2. missing verified gold falls back to original;
3. duplicate/missing/mismatched IDs fail closed;
4. incorrect archived `correct` flag fails closed;
5. pair orientation and expanded/contracted/flip categories;
6. exact ties have deterministic order and are excluded from relative ratios;
7. shared bootstrap indices preserve pairing;
8. same seed produces byte-identical analysis;
9. input hash mismatch fails closed;
10. receipt reports zero API attempts and input bytes unchanged.

## 9. Stop conditions

Stop without interpreting results if an integrity gate fails, a frozen input is
modified, the two deterministic replays differ, or any network/API attempt is
made. Do not repair an input, replace a model, alter the bootstrap seed/count,
or change a formula after observing the rerun.
