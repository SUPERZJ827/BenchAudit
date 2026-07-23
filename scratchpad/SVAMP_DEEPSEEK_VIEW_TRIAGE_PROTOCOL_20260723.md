# SVAMP-Platinum DeepSeek-view triage protocol

Frozen before collecting new DeepSeek responses on 2026-07-23.

## Purpose

Test whether prompt-diverse repeated views from one model can serve as a
low-cost fallback when a true multi-model response matrix is unavailable.
This is deliberately weaker than the validated 15-model MMLU setting.

The experiment must not relabel repeated views as independent models.  A
negative result establishes a product boundary: same-model prompt diversity
cannot replace organization/model-family diversity.

## Dataset and leakage boundary

- Full 300-item `madrylab/platinum-bench` SVAMP split.
- Public inference/audit input contains only item ID, task, original gold,
  output contract, and evaluator.
- `cleaning_status`, corrected target, and audit labels are written to a
  physically separate label artifact.
- No label may be read during response collection, audit scoring, or candidate
  ranking.
- Evaluation opens labels only after response and score artifacts are frozen.

Primary positive label:

- `revised` or `rejected` (38 total);
- clean negative: `consensus` or `verified` (262 total).

`revised`-only results (3 items) are descriptive and must not support broad
claims.

## Response views

Model: `deepseek-v4-flash`.

Eight fixed prompt views:

1. direct arithmetic;
2. equation first;
3. stepwise solver;
4. independent verifier;
5. unit and quantity check;
6. alternative method;
7. ambiguity-aware solver;
8. minimal answer.

Views 1–4 use non-thinking mode; views 5–8 use thinking mode. Temperature is
zero. Prompts differ, but no stochastic-repeat independence is claimed.

Each response must be a JSON object with a single numeric `answer`. Invalid,
missing, truncated, or unparsable responses are missing observations—not
incorrect answers. Correctness is evaluated against the benchmark's original
numeric gold, matching the benchmark-under-audit.

Budget:

- at most 2,400 successful logical calls (300 × 8);
- exact provider-attempt cap of 1,300 for each four-view client;
- at most 300 output tokens per call;
- 32 worker threads;
- every raw parsed response cached for resumability.

## Methods

1. static BenchAudit score from the stripped dataset;
2. DeepSeek prompt-view error rate;
3. equal-percentile `BenchAudit + view error rate` fusion through the production
   `triage-responses` implementation.

All behavior signals remain `review-only`.  No DeepSeek response may promote a
finding to `confirmed`.

## Metrics

Report AP, P@20/50/100, R@20/50/100, and lift over prevalence on:

- full 300;
- the previously fixed Pilot-100 manifest, as a secondary enriched slice.

Also report:

- response completeness;
- unique correctness patterns across views;
- pairwise view agreement;
- number of behavior-eligible items;
- API calls and provider-reported token use;
- exact SHA-256 provenance.

## Frozen decision

Treat repeated DeepSeek views as a useful fallback only if, on the full 300:

1. fusion AP exceeds both standalone methods by at least `+0.020`;
2. fusion P@50 is not below static BenchAudit P@50;
3. at least three unique correctness patterns survive the production diversity
   gate;
4. at least 95% of items have all eight valid responses.

Otherwise retain the strict product requirement: import genuine multi-model
historical trajectories, and use DeepSeek only for semantic attribution after
candidate selection.

