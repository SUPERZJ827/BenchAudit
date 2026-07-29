# APPS input-contract V1 preflight results

Date: 2026-07-29

Decision: **`NOT_IDENTIFIABLE_PREFLIGHT_V1`**

## What was tested

Before reading any of the 16 target problem statements or implementing the
survivor-confirmation runner, the frozen V1 input-contract scanner was applied
to the non-target APPS test rows.  This tests whether the proposed mechanical
certificate language is broad enough to justify implementing the target
experiment.

The preflight:

- skipped the 16 target rows before JSON decoding;
- parsed no target question text;
- executed no candidate or reference solution;
- made zero LLM/API calls;
- emitted aggregate counts only.

## Frozen result

| Measure | Result |
|---|---:|
| Dataset rows scanned | 5,000 |
| Target rows skipped before JSON decoding | 16 |
| Non-target statically eligible stdin/stdout rows | 1,327 |
| Rows supported by V1 | 33 |
| V1 coverage | **2.49%** |
| Pre-registered proceed threshold | **20.00%** |
| Candidate/reference executions | 0 |
| LLM/API calls | 0 |
| Decision | **`NOT_IDENTIFIABLE_PREFLIGHT_V1`** |

Supported schema families:

| Schema | Rows |
|---|---:|
| `single_integer` | 27 |
| `fixed_integer_tuple` | 6 |
| `counted_integer_vector` | 0 |
| `fixed_lines_of_integers` | 0 |

The two more expressive V1 families were therefore inactive: all 33 supported
rows came from the two simplest scalar/tuple patterns.  This strengthens the
negative diagnosis.  The issue is not merely that the overall count missed the
threshold; half of the assumed certificate structures did not appear once in a
mechanically admissible form.

The full-question fail-closed scan excluded 686/1,327 eligible non-target rows
(51.7%) because constraints such as `guaranteed`, `distinct`, `exactly one`,
parity, permutation, connectivity, tree structure, primality, or ordering
appeared outside the narrow input-shape grammar.  This scan was added during
independent protocol review specifically to prevent a format parser from
certifying inputs that violate semantic preconditions.  Its observed scale
shows that the false-confirmation path was not merely theoretical: omitting
full-question constraints would have exposed roughly half of the preflight
population to potentially invalid certificates.

The conclusion is not sensitive to treating every parser near-miss as
recoverable.  There were 115 such rows: 12 counted-vector, 74 fixed-line,
20 fixed-tuple, and 9 single-integer near-misses.  Even the deliberately
optimistic upper bound `(33 + 115) / 1327 = 11.15%` remains below the frozen
20% threshold.

## Interpretation

This is a feasibility failure of the V1 certificate language, not evidence
that APPS's official tests are sufficient.  The proposed parser would cover
too little of the unseen non-target population to justify inspecting the
survivor tasks or building the confirmation runner.

Following the pre-registered stop rule:

- the 16 target problem statements remain unparsed by this experiment;
- no target input is generated;
- no survivor is re-executed;
- no V2 grammar is built;
- no task-specific exception or proof validator is added.

This prevents a general confirmation experiment from degenerating into a
hand-built parser for one benchmark.

## Reproducibility

| Artifact | SHA-256 |
|---|---|
| APPS test split | `5b003a65ac40feb47dd5eaec267a767a6fc435bdcfa68ff715fe869f948e760c` |
| Frozen survivor-pair artifact | `7b2190b71b02ccf5a26fea93857edc4fadc01253be16120ca9352a84297d5420` |
| Excluded target-id set | `2cda1dd969e59d33f0dc535c7096298b5fe360aef560627868dd3c2874554ec4` |
| Scanner source | `c45801e81dfc57d32b8dc7e1c80b0f9bc26965529439a7ac0ca4b9405a2d89da` |
| Aggregate preflight JSON | `0a1269bad244c801ad2e072dac5c9766409b029ebcea7c57225de3bed3950c5b` |
| Stable summary | `a3d360c39d59928ebb66bd29108b5c4cba8fe556b106b8e9dd1220358bd44c39` |

Files:

- scanner: `scripts/preflight_apps_input_contract_v1.py`;
- tests: `tests/test_apps_input_contract_preflight.py`;
- aggregate receipt:
  `docs/experiments/apps_input_contract_v1_preflight_20260729.json`;
- governing protocol:
  `docs/experiments/APPS_OFFICIAL_SUITE_SURVIVOR_CONFIRMATION_PROTOCOL_20260729.md`.

The protocol hardening and scanner were finalized in the working tree before
the aggregate-only preflight, but committed afterward.  The receipt binds the
exact executed scanner by source SHA-256.  No target outcome was available to
guide these changes because target rows were skipped before decoding.

The frozen 20% threshold and scanner were committed together 80 seconds before
the result commit.  Future preflights should commit the threshold separately
before scanner execution to make chronology directly observable.  Here the
decision was a large failure (2.49% versus 20%), so changing the threshold
afterward would have required moving it strongly against the pre-registered
stopping discipline.

The 1.29 GB dataset split is not committed to this repository.  Independent
re-execution therefore requires obtaining the pinned dataset revision and
verifying its recorded SHA-256; the committed receipt alone supports internal
consistency and source binding, not a dataset-free rerun.

Post-run verification:

- preflight tests: **6 passed**;
- full repository tests: **783 passed**;
- safety-claim registry validator: **passed**;
- independently recomputed stable summary SHA-256:
  `a3d360c39d59928ebb66bd29108b5c4cba8fe556b106b8e9dd1220358bd44c39`.
