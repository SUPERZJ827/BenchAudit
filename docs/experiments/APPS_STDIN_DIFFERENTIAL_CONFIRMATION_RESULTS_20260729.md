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
| Confirmed relative coverage gaps | **7** |
| Affected tasks | **4** |
| Witness yield | **5.19%** |
| Affected-task rate | **15.38%** |
| LLM/API calls | **0** |

The seven confirmed observations came from four deterministic mutation
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

## Determinism

Two complete repetitions used the same frozen task list, code, image, resource
limits, and mutation budget.

| Artifact | Run 1 | Run 2 |
|---|---|---|
| Stable summary SHA-256 | `153411da35dd1cc25c46b0b5a82972fa226d690f39985dd950d056c022ae4330` | same |
| Full raw result SHA-256 | `28709312b5b0ad190641e587504b49f4ea04c48c4b69ed1e5ce2600f4e40e5a9` | same |

The pinned container image was
`sha256:9e30f4122a069ab7f626cdd70a3c11ddbbf44a9bd0cc4cc834136a2a2f08e995`.
The execution driver SHA-256 was
`b48cd74eba936838fa6a824cffa98fa34c44b544acfb1d080fd9168456774edc`.

## Verification

- script-specific tests after the run: **14 passed**;
- full repository regression before the run: **772 passed**;
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
