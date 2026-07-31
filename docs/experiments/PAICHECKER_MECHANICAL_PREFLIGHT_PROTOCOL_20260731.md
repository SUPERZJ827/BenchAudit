# PAIChecker mechanical-decidability preflight protocol

Date: 2026-07-31  
Branch: `research/paichecker-mechanical-preflight-20260731`  
API/LLM budget: zero

## Provenance and timing

This executable protocol preserves the Stage 0/1 gates from the pre-existing
Chinese plan:

- source path:
  `/home/zhoujun/llmdata/after623/PAICHECKER_机械可判性预飞计划_20260731.md`
- source SHA-256:
  `bc2307844cbddb0adb790771d2c3b01f877da08800b8fcef4dea9ed8eafe4541`
- source mtime:
  `2026-07-31 14:19:03.357571243 +0800`

The source plan existed before this investigation. However, the official
paper and repository README were inspected before this executable protocol
was committed. Therefore this run must not be described as a blinded
preregistration. The stopping rules below are unchanged from the source plan.

## Research question

Does the public PAIChecker artifact expose enough labeled source evidence to
evaluate a zero-LLM, locally replayable detector for a mechanically decidable
subset of PR-issue misalignment?

The preflight does not claim that a lexical or metadata observation is itself
a confirmed benchmark defect.

## Frozen source

- Paper: `arXiv:2607.28587v1`
- Official repository:
  `https://github.com/manyifire/PAIChecker`
- Repository revision: the default branch HEAD fetched at execution time,
  recorded in the receipt

No substitute dataset, unofficial mirror, manually reconstructed label, or
fresh GitHub scraping may be used if the official artifact is insufficient.

## Stage 0: public-data availability

Clone the official repository and record:

1. commit SHA and commit timestamp;
2. tracked file paths, sizes, and SHA-256 values;
3. candidate JSON/JSONL/CSV/Parquet files and their aggregate schemas;
4. record counts without exporting source text;
5. whether any labeled research dataset contains:
   - `instance_id`;
   - binary and/or fine-grained human label;
   - issue body;
   - issue discussion;
   - PR description;
   - production patch;
   - test patch.

The single documented example input is not a labeled research dataset.
Source-code fixtures and model-output schemas are not annotations.

### Stage 0 gate

Return `NOT_IDENTIFIABLE_DATA` and stop if either condition holds:

- the repository contains no labeled research dataset; or
- labels exist only as IDs/aggregates and the evidence required for the
  proposed groups cannot be linked locally.

Do not proceed to Stage 1 or implement a detector after this gate fails.

## Stage 1: mechanical extractability

Stage 1 is allowed only after Stage 0 passes. It measures field availability,
not correctness.

The three evidence groups are:

- A: issue-closing references in PR descriptions;
- B: literals in test patches plus issue text and production patch;
- C: issue body, issue comments, and assertion-bearing test patch.

The combined denominator is the union of uniquely identified labeled records,
not the sum of duplicated group rows.

### Stage 1 gate

Proceed only if both hold:

- at least 20% of unique labeled records are extractable for at least one
  group; and
- at least one group contains at least 30 extractable records.

Otherwise return `NOT_IDENTIFIABLE_PREFLIGHT` and stop.

## Methodological corrections frozen before any detector implementation

1. The paper's `92.12%` is binary accuracy against human annotations on
   SWE-Gym, not an LLM-consensus rate.
2. A generic `#N` reference count is not SC-1 proof. A future rule must at
   least distinguish issue-closing references from contextual references.
3. A test literal absent from the issue is not UL-1 proof. A future rule must
   additionally bind the same fixed runtime literal in the production patch
   and must abstain when derivability or semantic role cannot be established.
4. Human PAIChecker labels may evaluate conditional precision/recall, but do
   not themselves promote BenchAudit evidence to `confirmed`.

## Outputs

- `docs/experiments/paichecker_data_receipt_20260731.json`
- `docs/experiments/PAICHECKER_MECHANICAL_PREFLIGHT_RESULTS_20260731.md`

The receipt contains aggregate metadata only. It must record zero LLM/API
calls and the exact stopping decision.
