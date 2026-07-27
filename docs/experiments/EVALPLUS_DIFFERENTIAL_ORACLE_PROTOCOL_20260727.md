# EvalPlus differential-oracle confirmation protocol

Status: **frozen before the MR-4 implementation and confirmation run**.

## Question

Can BenchAudit confirm an evaluator coverage gap on a benchmark for which no
benchmark-specific proof validator was written?

The claim is deliberately narrow:

> A declared weak oracle accepts a deterministic candidate while an
> independently executed, declared stronger oracle rejects the same candidate.

This is a **relative evaluator coverage gap**.  It is not, by itself, a claim
that every stronger-oracle test is an infallible specification of human intent.

## Data

- HumanEval original tests vs. HumanEval+ tests.
- MBPP base tests vs. MBPP+ tests.
- Canonical solutions and tests are loaded from the pinned Hugging Face dataset
  revisions recorded by the experiment.
- Candidate programs are deterministic AST mutations.  The generic checker
  receives only identities, hashes, typed outcomes, and an externally attested
  transcript.  It contains no HumanEval- or MBPP-specific validation branch.
- Final runs use two mutations per AST family, a 10-second per-probe limit,
  a 90-second outer task limit, and eight concurrent workers.  These values are
  included in the stable summary hash.

## MR-4 relation

For a candidate `c`, weak oracle `W`, and declared stronger oracle `S`:

1. the canonical solution must complete and pass both `W` and `S`;
2. `c` must execute under both oracles;
3. `W(c) = pass`;
4. `S(c) = fail`;
5. neither observation may be a timeout, runner error, or malformed result;
6. the same candidate hash must be bound to both observations;
7. a separate execution trust domain must attest the exact transcript;
8. promotion must independently replay all structural obligations.

Only the conjunction may become `confirmed`.

The runner makes at most one fixed retry after a worker/container transport
failure.  It never retries a canonical failure or any candidate verdict, so
this availability rule cannot select a more favorable semantic outcome.

## Controls

The run must include:

- **canonical control:** canonical solutions produce zero findings;
- **identical-oracle control:** comparing the weak oracle with itself produces
  zero confirmed findings;
- **timeout control:** injected timeout outcomes remain indeterminate and
  produce zero confirmed findings;
- **swapped-direction control:** `W(c) = fail, S(c) = pass` is not reported as
  an underconstrained weak evaluator;
- **attestation control:** removing or corrupting external attestation caps the
  exact same observation at `review`;
- **determinism control:** two fixed-protocol runs have identical stable summary
  SHA-256 values.

## Metrics

Report separately for HumanEval and MBPP:

- requested and valid tasks;
- generated candidates;
- completed weak/strong pairs;
- timeout/error/indeterminate pairs;
- coverage-gap witnesses and affected tasks;
- confirmed/review/unknown counts after central promotion;
- witness yield among completed candidate pairs;
- affected-task rate among valid tasks;
- all control false-positive counts.

## Go / no-go rule

The north-star experiment passes only if all of the following hold:

1. at least one real, externally attested confirmed coverage gap is produced in
   each benchmark;
2. no benchmark-specific proof validator or task-ID allowlist is used;
3. every control has zero confirmed false positives;
4. timeout/error outcomes never count as semantic failures;
5. full tests and the safety-claim registry pass;
6. the stable summary is reproducible.

Failure of any safety condition is a no-go even if the headline count improves.
