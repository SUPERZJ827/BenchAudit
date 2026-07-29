# APPS stdin/stdout differential-oracle transfer result

Date: 2026-07-29

## Result

The frozen pilot **passed its adapter/proof-contract gate** and produced
positive transfer evidence:

| Metric | Result |
|---|---:|
| APPS test rows scanned | 5,000 |
| Statically eligible stdin/stdout rows | 1,343 |
| Requested tasks | 30 |
| Valid executable tasks | 26 |
| Canonical-invalid tasks | 3 |
| No-applicable-mutation tasks | 1 |
| Generated candidates on valid tasks | 140 |
| Completed weak/strong pairs | 135 |
| Indeterminate pairs | 5 |
| Confirmed gaps vs. constructed two-case prefix | **7** |
| Affected tasks | **4** |
| Witness yield over all completed pairs | **5.19%** (7/135) |
| Candidates passing the weak oracle | **33** |
| Conditional gap yield after weak pass | **21.21%** (7/33) |
| Affected-task rate | **15.38%** |
| LLM/API calls | **0** |

The seven confirmed constructed-prefix observations came from four
deterministic mutation
families:

| Mutation family | Confirmed |
|---|---:|
| condition negation | 3 |
| boolean operator | 2 |
| arithmetic operator | 1 |
| numeric constant | 1 |

The affected APPS problem ids were 1402, 1785, 1849, and 4352.

## What was actually tested

APPS is a code-generation benchmark containing 10,000 problems with test cases
and reference solutions.  This pilot used its 5,000-row test split and selected
stdin/stdout tasks under a protocol frozen before execution.  See the
[APPS paper](https://arxiv.org/abs/2105.09938), the
[official benchmark repository](https://github.com/hendrycks/apps), and the
[dataset mirror](https://huggingface.co/datasets/codeparrot/apps).

For every selected task:

- the weak oracle was the first two official APPS test cases;
- the strong oracle was the complete official test list;
- the same deterministic AST mutant was executed against both;
- the canonical solution had to pass both;
- timeout, signal, malformed output, runner failure, or missing attestation
  could not become semantic rejection or `confirmed`;
- a separate worker signed the transcript and the parent independently invoked
  BenchAudit's central promotion policy.

This is the same generic MR-4 relation previously used for function-call
HumanEval+/MBPP+, now exercised through a new stdin/stdout adapter.  No
APPS-specific task id or expected witness appears in the checker.

## Claim boundary

The positive claim is:

> The generic weak/strong-oracle proof contract transferred to a different
> execution protocol and objectively confirmed seven relative coverage gaps.

It is **not**:

> The official APPS evaluator contains seven defects.

The weak two-case prefix was deliberately constructed for this experiment.
Therefore the result validates adapter and proof-contract portability, not a
defect claim about APPS's official full evaluator.  The three canonical-invalid
tasks also show that the local comparator does not perfectly cover every APPS
execution convention; those tasks were excluded fail-closed and were not
replaced.

## Safety controls

All required false-positive controls remained zero:

| Control | Confirmed |
|---|---:|
| Canonical solution | 0 |
| Identical weak/strong outcome | 0 |
| Timeout or error treated as rejection | 0 |
| Swapped direction | 0 |
| Missing attestation | 0 |
| Corrupt attestation | 0 |

Four timeout pairs and one other indeterminate pair were excluded rather than
converted into failures.

## Candidate-level reproducibility bundle

The repository now includes
`apps_stdin_differential_confirmation_detail.json`.  It contains, for every
candidate:

- problem id and task status;
- candidate id, family, transformation index, and source SHA-256;
- typed weak and strong observations;
- confirmed status and the transcript SHA-256 for confirmed candidates.

This permits the 7 findings, 135 completed pairs, 33 weak passes, both yield
denominators, task exclusions, and all aggregate counts to be independently
recomputed without downloading the 1.29 GB dataset.  The detailed artifact
SHA-256 is
`646f6774a5a25d118c99a5f3f82b9dea64704a29689dfa31ab62f4ae03f4080b`.

For convenient independent recomputation, the repository also includes the
135 completed weak/strong pairs as one row per candidate in
`apps_stdin_differential_pairs_20260729.jsonl`.  Its SHA-256 is
`7b2190b71b02ccf5a26fea93857edc4fadc01253be16120ca9352a84297d5420`.
Those 135 rows directly reproduce 7 confirmed constructed-prefix gaps, 33 weak
passes, both reported yields, and four affected problem ids.

The output-only serialization was added after the original run in response to
independent review.  It does not change task selection, mutation generation,
execution, comparison, attestation, checking, or promotion.  Two detailed
replays and the tracked copy are byte-identical.

## Determinism

Two complete repetitions used the same frozen task list, code, image, resource
limits, and mutation budget.  The original observations corresponding to the
reported hashes are now committed in the two reproducibility artifacts above.

| Artifact | Detailed run 1 | Detailed run 2 |
|---|---|---|
| Stable summary SHA-256 | `4d3a384e05fb7eafa9cb35aab5b5e442dfcd22c99299a70ea7f318189f0dc4f4` | same |
| Full detailed result SHA-256 | `646f6774a5a25d118c99a5f3f82b9dea64704a29689dfa31ab62f4ae03f4080b` | same |

The original two pre-serialization runs also remain recorded: their stable
summary SHA-256 was
`153411da35dd1cc25c46b0b5a82972fa226d690f39985dd950d056c022ae4330`
and their full-result SHA-256 was
`28709312b5b0ad190641e587504b49f4ea04c48c4b69ed1e5ce2600f4e40e5a9`.

The pinned container image was
`sha256:9e30f4122a069ab7f626cdd70a3c11ddbbf44a9bd0cc4cc834136a2a2f08e995`.
The execution driver SHA-256 was
`b48cd74eba936838fa6a824cffa98fa34c44b544acfb1d080fd9168456774edc`.

## Verification

- script-specific tests after the detailed replay: **17 passed**;
- full repository regression before the run: **772 passed**;
- full repository regression after adding the reproducibility bundle:
  **777 passed**;
- safety-claim registry: **valid**;
- dataset input receipt:
  `5b003a65ac40feb47dd5eaec267a767a6fc435bdcfa68ff715fe869f948e760c`;
- LLM/API calls: **0**.

The implementation was committed before task-level execution.  Two additional
tests added afterward cover row-order-independent hash selection and
same-size input-file tampering; they do not alter runner behavior or the
reported result.

## What this adds to BenchAudit

Before this pilot, the strongest generic confirmation result was restricted to
function-call evaluators.  This result adds evidence that:

1. benchmark-specific loading and execution can remain outside the generic
   confirmation checker;
2. stdin/stdout materialization can be adapted without weakening the central
   fail-closed promotion contract;
3. objective confirmation can be obtained with zero model calls;
4. execution-protocol diversity, not only benchmark diversity within one
   harness family, is a practical route toward broader automatic adaptation.

The next meaningful test should use a naturally occurring weak/strong oracle
pair or an independently strengthened public test suite.  Repeating more
constructed prefixes would increase the count without strengthening the claim.
