# MMLU-1000 offline response-pattern baseline protocol

> Frozen: 2026-08-03 (Asia/Singapore)  
> Status: protocol only; response-pattern metrics had not been computed  
> Incremental budget: API 0, network 0, LLM 0

## 0. Question

Can a simple, fully offline response-pattern signal from 15 previously recorded
model answer matrices match or exceed BenchAudit's MMLU-1000 defect-detection
performance?

For an item with declared gold label `g`, the baseline score is:

> the largest number of models that independently emitted the same valid
> non-`g` option label.

This is a deliberately strong, cheap baseline. A result that matches or exceeds
BenchAudit changes the paper's claim; it must not be hidden or weakened after
inspection.

The 15 responses already exist. “Cost ¥0” means zero **incremental** API cost for
this analysis, not that the historical model responses were free to produce.

## 1. Frozen inputs

### 1.1 Population and BenchAudit output

| Artifact | SHA-256 |
|---|---|
| `experiments/mmlu_redux_pilot1000.jsonl` | `70cc9ee184db4017b323bda03061f7c3d56e57ad1ab4b1a3415263fd664072b8` |
| `reports/ranking_impact/audit_full1000.json` | `8fc5fa57330b704faa48f7007f228a7ae3f44d02beaa30c1e96970ba9aa88cc6` |

The source population contains exactly 1,000 unique item IDs. The sorted-ID
SHA-256 convention is UTF-8 IDs in lexical order, LF joined and LF terminated.
Expected hash:
`91325c9c67cb0a92ebf8832efbf5ee09730d47322493d29def9fe222799475b3`.

### 1.2 Answer matrices

Every file must contain exactly the same 1,000-ID set. File order is irrelevant;
rows join only by exact item ID.

| Model file | SHA-256 |
|---|---|
| `amazon__nova-pro-v1.jsonl` | `75c8f1239ac93b248594799beea47f9642743db0b30b07c1fb929a60420186e7` |
| `cohere__command-r-08-2024.jsonl` | `a550b7dd005294267c769f860297b84dbcc9607bbc52fbbebd7918e71f4cf4be` |
| `deepseek.jsonl` | `fa7acdf241df1a01eee1eda1a00e645c605aee503b0416edd726d089527b6101` |
| `google__gemini-2.5-flash.jsonl` | `2bc96f33b908d22b4703f91e33c598eafa03b3be6a3516ca9c92fdd8fb400ec9` |
| `meta-llama__llama-3.1-70b-instruct.jsonl` | `c19b0936c1ea6723f2f7169a0793d622eb7a43a14bd816d90c9c221d83efa72a` |
| `meta-llama__llama-3.1-8b-instruct.jsonl` | `afc4ad5b9f76a08ee5929771880d35019e2b98055a30711200addf5500ccaf19` |
| `meta-llama__llama-3.3-70b-instruct.jsonl` | `2d9ee021748d2501754cac714faafb09b7159b419a6ef11eaded46c86e5edf44` |
| `microsoft__phi-4.jsonl` | `ca82caa157fd6816368e80bfd805b50943e5063d80108375c20215c4d6710a20` |
| `mistralai__mistral-nemo.jsonl` | `f024d64e3c14fa07614e930906715af54f8394bb50eaade17fc4dcdfe789c6a8` |
| `mistralai__mistral-small-24b-instruct-2501.jsonl` | `7d28319ac1b4b45bdfb80bfb786ce1c443c75e824043959321672b2ca28760bf` |
| `openai__gpt-4.1-mini.jsonl` | `ad595880ab90cbe09411c96eba97f6e533101ebf293d66ae3f37c1a6fba3bf42` |
| `openai__gpt-4o-mini.jsonl` | `7e122b072aba7874815f75c62203b628970ad003ed86776a1ab1b9ba358cdcd4` |
| `openai__gpt-4o.jsonl` | `9b274b186d8e60a03ece47b032823f0d79d3bc879c30152b91f340a103515ec9` |
| `qwen__qwen-2.5-72b-instruct.jsonl` | `c043efc588e2166a525e42f6093c7469aa3f08a7517d5d1126be5bcefa072465` |
| `qwen__qwen-2.5-7b-instruct.jsonl` | `85c50927156ca133b0e09cad0d72a9fc71bd75dcbffdd495451686ccac22b04c` |

Each answer row must contain `id`, `gold`, `pred`, `correct`, `error_type`, and
`subject`. Across a given item, answer-file gold, error type, and subject must
exactly match the source row. `correct` must equal normalized `pred == gold`.
Any mismatch, duplicate, missing item, unknown file, or hash drift stops the
experiment.

## 2. Frozen response score

For each model response:

1. a string prediction is normalized by `str.strip().upper()`;
2. only exact labels `A`, `B`, `C`, `D` are valid votes;
3. JSON null, the string `None`, empty strings, and all other values are
   abstentions;
4. the declared gold is normalized by the same label rule and must be valid;
5. gold votes are ignored;
6. count votes separately for each valid non-gold label;
7. `score = max(non_gold_label_counts)`, or zero when there is no non-gold vote.

A tie between different non-gold labels does not add their counts. The receipt
records every maximizing label and its count. All 15 models have equal weight.
No model-family de-duplication, model-quality weighting, subject adjustment, or
answer-content inspection is permitted.

The models are not statistically independent: some share model families,
training data, providers, or benchmark exposure. Therefore this signal is a
response-consensus heuristic, not 15 independent expert votes.

## 3. Thresholds and primary comparison

The scanner reports every absolute threshold `k = 1, 2, ..., 15`.

Frozen named points:

- **primary:** `k >= 8`, a strict majority of the 15-model panel agreeing on
  the same non-gold label;
- **strong:** `k >= 12`;
- **unanimous-panel:** `k = 15`.

The threshold with maximum F1 may be reported only as
`post_hoc_oracle_upper_bound`. Ties break toward the larger `k`. It may not
replace the `k>=8` primary result and may not support an out-of-sample claim.

No threshold is tuned by subject, defect type, model family, or inspection of
individual predictions.

## 4. Frozen truth endpoints

All endpoints must be reported; none may be substituted after inspection.

### 4.1 Legacy published-binary endpoint

- positive: `metadata.error_type != "ok"`, including `expert`;
- negative: `metadata.error_type == "ok"`.

This reproduces the existing 370-positive comparison and BenchAudit's
`206/370` recall. It is retained only for numerical compatibility. It must be
labelled `legacy_non_ok_including_expert` because `expert` is an abstention, not
an explicit defect.

### 4.2 Strict explicit-defect endpoint

- positive: `wrong_groundtruth`, `bad_question_clarity`,
  `multiple_correct_answers`, `no_correct_answer`, or
  `bad_options_clarity`;
- negative: `ok`;
- excluded: `expert`.

This is the scientific primary endpoint.

### 4.3 Gold-related endpoint

- positive: `wrong_groundtruth`, `multiple_correct_answers`, or
  `no_correct_answer`;
- negative: `ok`;
- excluded: every other label.

This endpoint is closer to what same-non-gold consensus can plausibly detect.

### 4.4 Wrong-groundtruth-only endpoint

- positive: `wrong_groundtruth`;
- negative: `ok`;
- excluded: every other label.

This is the narrowest, most directly aligned diagnostic endpoint.

## 5. BenchAudit comparator

An item is a BenchAudit candidate when `audit_full1000.json` contains at least
one finding with:

- `defect_scope == "substantive"`; and
- `evidence_tier == "review"`.

Operational/coverage-only/unknown findings do not count. Multiple findings on
one item count once. The script must independently reproduce, on the legacy
endpoint:

`TP=206, FP=86, FN=164, TN=544, precision≈0.705, recall≈0.557, F1≈0.622`.

Failure to reproduce the integer confusion matrix stops the experiment. The
same frozen candidate set is then scored on all four endpoints.

BenchAudit has been developed on this population. The response-pattern result
is likewise an in-sample baseline comparison, not a holdout generalization
claim.

## 6. Metrics and interpretation

For every endpoint and every `k`, report integer TP/FP/FN/TN, candidate count,
precision, recall, F1, specificity, and false-positive rate. Undefined ratios
are JSON null, never silently zero.

Also report:

- score histogram and abstention-count histogram;
- per-subject metrics for `k>=8`, with no subject-specific tuning;
- overlap between the `k>=8` candidate set and BenchAudit candidates;
- the exact disagreement item IDs in machine-readable output;
- a deterministic analytic random comparator at the same candidate count as
  each system: expected recall equals candidate fraction and expected precision
  equals endpoint prevalence. It is context only, not a sampled experiment;
- the seven T1 exact-duplicate items as a separate evidence note. Their six
  Redux-`ok` findings demonstrate label incompleteness; they must not be called
  response-pattern false positives merely because the frozen truth says `ok`.

Do not list “human reannotation” as a detector with recall 1.0. The Redux labels
define these supervised endpoints; scoring the labels against themselves is
circular.

## 7. Outputs and determinism

Publish under `reports/mmlu_response_pattern_baseline_20260803/`:

- `scores.jsonl`: item ID, gold, valid-vote count, abstention count, non-gold
  counts, maximum count, maximizing labels, source label, subject;
- `metrics.json`: all endpoints, thresholds, BenchAudit comparator, overlaps,
  histograms, and oracle upper bounds;
- `REPORT.md`: concise comparison tables and claim boundary;
- `receipt.json`: every frozen hash, code hash, output hash, row/model counts,
  zero incremental API/network/LLM use, and `production_activation=false`;
- `raw_run.json`: wall-clock/PID/path data excluded from stable hashes.

Two independent runs in empty directories must produce byte-identical scores,
metrics, report, and stable receipt. Any invalid binding or row yields
`BASELINE_INCOMPLETE` and no stable PASS artifacts.

## 8. Required tests and non-activation

At minimum:

1. eight identical non-gold votes trigger the primary threshold;
2. votes split across alternatives are not summed;
3. null/`None`/invalid predictions abstain;
4. gold votes never contribute to the score;
5. every endpoint constructs the frozen positive/negative/excluded sets;
6. undefined metrics remain null;
7. oracle-F1 tie-break chooses larger `k` and remains labelled post hoc;
8. duplicate/missing IDs, answer/source mismatch, or hash drift fails closed;
9. BenchAudit legacy confusion matrix reproduces exactly;
10. two constructed runs yield byte-identical stable outputs;
11. no network, LLM client, API-key access, production import, or production
    activation path exists;
12. fresh-clone tests verify constructive logic and committed output hashes;
    source/report integration may skip only when ignored frozen artifacts are
    absent.

The experiment may add only a standalone script, tests, this protocol, and new
result artifacts. It must not modify `benchcore/**`, production methods,
historical responses, MMLU source rows, audit reports, or blind-test manifests.
