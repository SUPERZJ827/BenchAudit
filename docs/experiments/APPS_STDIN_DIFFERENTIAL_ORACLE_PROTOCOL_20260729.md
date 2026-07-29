# APPS stdin/stdout differential-oracle transfer protocol

Status: **frozen before inspecting task-level outcomes, implementing the APPS
adapter, or executing any candidate program**.

## Question

Can the existing generic MR-4 proof contract transfer from function-call
benchmarks to a different execution protocol: stdin/stdout programs?

The claim is deliberately narrower than an APPS benchmark audit:

> Given a frozen weak prefix of APPS test cases and the corresponding complete
> APPS test set, can BenchAudit confirm that the same deterministic candidate
> passes the former and fails the latter?

This tests the portability of the execution adapter and proof contract.  The
weak oracle is constructed for this experiment, so a positive result **must
not** be described as a defect in the official APPS evaluator.

## Frozen source

- dataset repository: `codeparrot/apps`;
- repository revision:
  `21e74ddf8de1a21436da12e3e653065c5213e9d1`;
- test split blob id:
  `ce62a3228ba3463b6fffcb7079d586e1a4c75f8d`;
- test split declared size: `1,292,436,853` bytes;
- source paper and benchmark repository are recorded in the result report.

The downloaded file SHA-256 and byte size are recorded in a separate input
receipt before any task is executed.  A missing file, revision mismatch, blob
mismatch, or later byte change is fail-closed.

## Static eligibility and task selection

The pilot uses the test split only.  A row is statically eligible when all of
the following hold:

1. `problem_id` is present and unique;
2. `input_output` parses as a JSON object;
3. `fn_name` is absent or null, selecting stdin/stdout rather than call-based
   execution;
4. `inputs` and `outputs` are lists of equal length;
5. there are between 5 and 20 test cases, inclusive;
6. `solutions` parses as a non-empty JSON list;
7. the first listed solution is a Python string, parses as Python, and contains
   at most 10,000 UTF-8 bytes;
8. the serialized test material contains at most 100,000 UTF-8 bytes.

No execution result participates in static eligibility or task ordering.

Eligible rows are ordered by
`SHA256("benchaudit-apps-stdin-v1:" + problem_id)` and then by numeric
`problem_id`.  The first 30 rows form the requested pilot.  A canonical
solution that does not complete and pass both declared oracles is retained in
the report as `canonical_invalid`; it is never replaced by another solution or
task after observing execution.

## Frozen oracle relation

For each requested task:

- weak oracle `W`: the first two APPS test cases in dataset order;
- strong oracle `S`: all APPS test cases in dataset order;
- comparator: the versioned local APPS stdin comparator whose source SHA-256
  is bound into the execution transcript;
- canonical source: the first listed solution;
- candidate sources: at most one deterministic mutation per existing MR-4 AST
  family, generated in the existing frozen family order.

The strong test set is a strict extension of the weak set because every
eligible task has at least five cases and the first two cases are preserved
byte-for-byte.

## Comparator and execution semantics

Each candidate/test case runs in a fresh Python subprocess inside the existing
digest-pinned, read-only, network-disabled, non-root container.  Standard input
is materialized from the APPS input field.  Standard output is compared using a
versioned deterministic comparator supporting:

- leading/trailing whitespace normalization;
- exact line-preserving comparison;
- token-wise numeric comparison with fixed tolerances;
- order-insensitive token comparison only when both sides have identical token
  multiplicities.

The comparator does not call an LLM and does not infer intent.  A subprocess
timeout, signal, runner error, malformed test case, or comparator error is
`indeterminate`, never a semantic rejection.

## Confirmation contract

For candidate `c`, confirmation requires all of the following:

1. the canonical solution completes and passes both `W` and `S`;
2. `c` completes under both oracles;
3. `W(c) = pass`;
4. `S(c) = fail`;
5. the exact same candidate hash is bound to both observations;
6. the declared strong oracle identity differs from the weak identity;
7. a separate worker signs the exact execution transcript;
8. the parent pins the worker key and independently invokes the central
   promotion policy;
9. the generic checker contains no APPS task id, expected witness, or
   benchmark-specific semantic proof branch.

Only the conjunction may become `confirmed`.

## Resource limits

- requested tasks: 30;
- mutations per AST family: 1;
- per test-case subprocess timeout: 2 seconds;
- outer task timeout: 120 seconds;
- concurrent workers: 6;
- operational retries: at most one retry for worker/container transport
  failure only;
- LLM/API calls: 0.

Canonical failures and candidate semantic outcomes are never retried.

## Required controls

- canonical solutions produce zero findings;
- identical weak/strong outcomes produce zero confirmed findings;
- timeout/error/malformed outcomes produce zero confirmed findings;
- swapped direction (`W = fail`, `S = pass`) produces zero confirmed findings;
- missing or corrupt attestation produces zero confirmed findings;
- the same frozen pilot run twice produces the same stable summary SHA-256;
- the comparator and adapter unit tests pass;
- the full repository test suite and safety-claim registry pass.

## Metrics

Report:

- total rows scanned and statically eligible rows;
- requested, valid, canonical-invalid, and operational-failed tasks;
- candidate count and completed/indeterminate weak–strong pairs;
- confirmed relative coverage gaps and affected tasks;
- witness yield and affected-task rate;
- result counts by mutation family;
- all control false-positive counts;
- wall time and zero-API receipt;
- stable summary SHA-256 for both repetitions.

## Interpretation and stop rule

This pilot is a transfer test, not a search for a favorable APPS result.

- **Adapter/proof-contract pass:** all safety controls are zero, both runs are
  deterministic, and at least one completed pair is evaluated.  A zero-witness
  result is retained as a valid negative result.
- **Positive transfer evidence:** the pass conditions hold and at least one
  externally attested confirmed relative coverage gap is observed.
- **No-go:** any safety control escapes, a timeout/error is treated as
  rejection, task selection depends on execution outcome, the result is not
  reproducible, or the report labels the constructed weak oracle as an
  official APPS evaluator defect.

No threshold, mutation family, task, test-prefix length, comparator tolerance,
or resource limit may be changed after task-level execution begins.
