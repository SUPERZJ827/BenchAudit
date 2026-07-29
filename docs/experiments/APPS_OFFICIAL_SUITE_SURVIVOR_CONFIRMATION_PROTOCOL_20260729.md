# APPS official-suite survivor confirmation protocol

Status: **frozen before reading the 16 target problem statements, implementing
an input-contract parser, generating any new input, or re-executing any
surviving mutant**.

Branch:
`research/apps-official-survivor-confirmation-20260729`

## 0. Why this experiment exists

The previous APPS transfer pilot contains 26 deterministic AST mutants that
pass the complete APPS test list.  They occur in 16 of 26 valid tasks and span
eight mutation families.

That observation is not yet a confirmed official-suite coverage gap:

- a mutant can be semantically equivalent to the canonical program;
- a changed statement can be dead or unreachable;
- two behaviorally different programs can both satisfy a non-unique task;
- a generated distinguishing input can be outside the task's legal domain.

The new experiment asks a narrower, falsifiable question:

> Can a task-independent, mechanically checked input-domain certificate produce
> at least one legal input on which APPS-declared reference solutions agree and
> an official-suite-surviving mutant differs?

The maximum positive claim is:

> APPS's complete published tests do not constrain the behavior shared by its
> declared reference solutions on one mechanically certified in-domain input.

This remains a relational claim about declared benchmark artifacts.  It is not
an absolute proof that APPS's evaluator or human-authored specification is
wrong.

## 1. Novelty boundary

Simply generating tests to kill surviving mutants is not a new research
contribution.  STING already follows the sequence “generate semantically
altered variants → retain those surviving benchmark tests → generate targeted
tests → keep tests that pass the ground-truth patch and reject a survivor” on
SWE-bench Verified:

- paper: <https://arxiv.org/abs/2604.01518>
- reported result: 77% of instances had at least one surviving variant;
- generated tests were retained only after ground-truth/variant differential
  execution and robustness validation.

Equivalent mutants are also a known central threat to mutation-score
interpretation:

- <https://arxiv.org/abs/2404.09241>

Therefore this pilot is worth continuing only if the following possible
difference survives experiment:

> generated tests carry a locally replayable certificate of task-domain
> legality, and the confirmation path is fail-closed rather than trusting an
> LLM or unverified test generator.

If the only successful inputs come from unconstrained fuzzing, LLM judgment,
or reference-solution consensus without an input-domain certificate, the result
is `review` and does not establish the proposed distinction.

## 2. Frozen source and target pool

### 2.1 Dataset

- repository: `codeparrot/apps`;
- revision:
  `21e74ddf8de1a21436da12e3e653065c5213e9d1`;
- test split SHA-256:
  `5b003a65ac40feb47dd5eaec267a767a6fc435bdcfa68ff715fe869f948e760c`;
- input receipt:
  `docs/experiments/apps_stdin_input_receipt_20260729.json`.

### 2.2 Survivor pool

- source artifact:
  `docs/experiments/apps_stdin_differential_pairs_20260729.jsonl`;
- source SHA-256:
  `7b2190b71b02ccf5a26fea93857edc4fadc01253be16120ca9352a84297d5420`;
- selection predicate:
  `outcome == "weak_pass_strong_pass"`;
- frozen pool size: 26 mutants in 16 tasks.

No task, family, difficulty, or source code may be removed after reading its
problem statement.  Operationally ineligible cases remain in the report with a
typed reason.

The mutant source is regenerated from the pinned first reference solution and
the frozen `family` plus `transformation_index`.  Its SHA-256 must match the
candidate hash in the source artifact.  A mismatch is fail-closed.

## 3. Outcomes and evidence ceilings

Every survivor receives exactly one terminal status:

1. `confirmed_declared_reference_behavior_gap`;
2. `review_distinguishing_input_without_domain_certificate`;
3. `no_distinguishing_input_within_budget`;
4. `not_identifiable_input_contract`;
5. `not_identifiable_reference_disagreement`;
6. `not_identifiable_equivalent_or_unreached_mutant`;
7. `operational_failed`.

Only status 1 may enter `confirmed`, and only under the conjunction in Section
8.  Status 2 is permanently review-only.  Statuses 3–7 produce no substantive
finding.

No result in this pilot may be labelled `benchmark_answer_error`,
`official_APPS_evaluator_defect`, or `incorrect_solution_accepted`.

## 4. InputDomainCertificateV1

### 4.1 Purpose

The certificate proves only that a concrete stdin string satisfies a supported
input-format and numeric-domain fragment explicitly stated in the problem
text.  It does not prove the output specification.

### 4.2 Supported schema families

Version 1 supports only:

1. `single_integer`: one integer with an explicit inclusive range;
2. `fixed_integer_tuple`: one line containing a fixed number of integers, each
   with explicit inclusive ranges;
3. `counted_integer_vector`: a leading integer `n`, followed by exactly `n`
   integers, with explicit ranges for `n` and vector elements;
4. `fixed_lines_of_integers`: a fixed, explicitly stated number of lines, each
   matching one of families 1–3.

The following are out of scope for V1:

- multiple test cases controlled by `t`;
- graphs, trees, grids, matrices, permutations, or strings;
- floating-point input;
- constraints requiring uniqueness, sortedness, connectivity, primality, or
  relations not expressible as field count and inclusive integer bounds;
- optional fields, alternative formats, or natural-language-only bounds;
- any ambiguity about whether a number describes input, output, or an example.

Out-of-scope or ambiguous tasks are `not_identifiable_input_contract`, not
negative examples.

### 4.3 Mechanical parser

The parser may recognize only a frozen English grammar:

- input declarations headed by an exact `Input`/`INPUT` section;
- `first/second/... line contains ...` declarations;
- fixed counts expressed as Arabic numerals or the words one through ten;
- inclusive bounds of the form `L <= x <= U`, `L ≤ x ≤ U`,
  `between L and U`, or `from L to U`;
- count links expressed as exactly `n integers`, `n space-separated integers`,
  or `a list/array of n integers`.

Every parsed field and constraint must contain:

- the exact source substring;
- byte offsets in the question;
- a SHA-256 of the full question;
- the typed parse;
- the concrete value being certified.

Competing parses, missing bounds, unmatched count variables, overlapping
source spans, unsupported number words, or unused stdin tokens cause
fail-closed rejection.

No task id, benchmark difficulty, target mutation family, or observed output
may participate in parsing.

### 4.4 Certificate replay

A local verifier independently reparses the anchored spans and checks:

- all stdin tokens are consumed exactly once;
- line counts and vector lengths match;
- every integer is within its inclusive bound;
- the certificate question hash matches the pinned dataset row;
- serialization and reparse are byte-stable.

An LLM cannot issue or repair this certificate.

## 5. Reference behavior contract

For each mechanically eligible task:

1. take the first three normalized-AST-distinct APPS reference solutions in
   dataset order;
2. the first is the canonical source from which the mutant was generated;
3. all three must complete on the generated input;
4. all three outputs must be equal under the frozen APPS stdin comparator;
5. timeout, signal, exception, comparator error, or disagreement makes the
   input `not_identifiable_reference_disagreement`;
6. the mutant must complete and produce a different output.

Fewer than three distinct reference solutions makes the survivor
`not_identifiable_reference_disagreement`.  Reference consensus is supporting
evidence, not a substitute for the input-domain certificate.

The claim is explicitly relative to APPS-declared reference behavior.  The
experiment does not infer that consensus is infallible human ground truth.

## 6. Frozen input search

Each survivor receives two equal-budget arms.  Both enumerate all 64 candidates
before outcome comparison; neither stops after finding a distinction.

### 6.1 Arm A: mutation-blind boundary search

Arm A sees only `InputDomainCertificateV1`.  It enumerates values in this fixed
order, retaining those within bounds:

1. lower bound;
2. upper bound;
3. lower bound + 1;
4. upper bound - 1;
5. 0;
6. 1;
7. -1;
8. integer midpoint.

For vectors, lengths use the same ordering and elements use:

- all lower;
- all upper;
- all zero when legal;
- all one when legal;
- alternating lower/upper;
- one changed position at a time in ascending index order.

Candidates are ordered by canonical JSON and SHA-256 after the fixed templates,
deduplicated, and truncated to 64.

### 6.2 Arm B: mutation-guided boundary search

Arm B has the same 64-input limit.  It may additionally inspect only:

- the changed AST node;
- integer constants in that node and its direct parent predicate;
- comparison operators and range/slice bounds in that local region.

It prioritizes `c-1`, `c`, and `c+1` when legal, then fills unused budget with
Arm A in its original order.

Arm B cannot inspect official per-case pass/fail results, previously discovered
distinguishing inputs, task ids, or target labels.

### 6.3 No LLM in this protocol

This pilot uses zero LLM/API calls.  An LLM-assisted generator requires a
separate frozen protocol.  LLM-generated inputs would remain review-only unless
the unchanged local certificate verifier accepts them.

## 7. Official-suite survival replay

Before testing generated inputs, the regenerated mutant and canonical source
must be re-executed against the complete APPS test list under the pinned
container and comparator.

Eligibility requires:

- canonical passes the complete list;
- mutant passes the complete list;
- all observations complete;
- source hashes match the frozen pool;
- the full transcript is signed by a separate worker.

Any difference from the earlier source artifact is reported and excludes the
survivor.  No retry is permitted for semantic outcomes.  At most one retry is
allowed for worker/container transport failure.

## 8. Confirmation conjunction

`confirmed_declared_reference_behavior_gap` requires all of:

1. the mutant belongs to the frozen 26-survivor pool;
2. regenerated source hash matches;
3. canonical and mutant both pass all official APPS tests in the new attested
   run;
4. a concrete generated input has a valid `InputDomainCertificateV1`;
5. the input is not byte-identical to an official test input;
6. three normalized-AST-distinct declared reference solutions complete and
   agree on output;
7. the mutant completes and disagrees with that output;
8. no timeout, signal, exception, malformed output, or comparator error occurs;
9. worker transcript binds dataset revision, question hash, source hashes,
   official tests, generated input, certificate, outputs, driver hash, and
   container digest;
10. the parent pins the worker key;
11. central promotion independently replays the certificate and all structural
    obligations;
12. the proof kind is disabled without valid external attestation.

Changing a method name, evidence tier string, candidate id, source hash,
question span, input value, output, or attestation must cap the observation at
review.

## 9. Controls

The implementation must include:

- canonical-vs-canonical produces zero findings;
- a synthetic equivalent mutant produces zero distinguishing input;
- an invalid or out-of-range input never confirms;
- a valid input with reference disagreement never confirms;
- timeout/error/signal never becomes semantic rejection;
- mutant failing the official full suite is ineligible;
- missing or corrupt attestation never confirms;
- changed question text or certificate span invalidates the proof;
- changed mutant source hash invalidates the proof;
- duplicated official input is excluded from new-gap evidence;
- swapped canonical/mutant direction cannot satisfy the contract;
- task-id and expected-witness scans over checker, parser, and promotion code
  return zero matches;
- two complete runs have identical stable summaries and finding identities.

At least one synthetic positive fixture and one fixture for every fail-closed
branch are required before real execution.

## 10. Metrics

Report:

- 26 frozen survivors and 16 source tasks;
- input-contract eligibility count and reasons for exclusion;
- number of tasks with at least three distinct reference solutions;
- generated, certified, executed, and indeterminate inputs per arm;
- number of behaviorally distinguishing inputs per arm;
- confirmed/review/not-identifiable counts;
- unique confirmed survivors and tasks;
- confirmation rate over mechanically identifiable survivors;
- Arm B minus Arm A incremental confirmations under equal budget;
- execution time and candidate-input count;
- all control counts;
- LLM/API calls, fixed at zero;
- two stable summary SHA-256 values.

Survivor count alone is not a success metric.

## 11. Go / no-go

This is a feasibility gate, not a paper-scale evaluation.

### Go

Proceed only if:

- at least one survivor reaches
  `confirmed_declared_reference_behavior_gap`;
- all controls remain zero;
- no task-specific proof validator or allowlist exists;
- the two runs are deterministic;
- full tests and safety registry pass.

### Not identifiable

If fewer than three of the 26 survivors have a mechanically supported input
contract and three distinct reference solutions, record
`NOT_IDENTIFIABLE_V1`.  Do not broaden the grammar after seeing target tasks.

### No-go

If at least three survivors are mechanically identifiable but none confirms,
record `NO_GO_V1`.  Retain all negative results and do not add task-specific
rules.

Any safety-control escape is an unconditional no-go even if confirmations are
found.

## 12. Interpretation after the pilot

- A positive pilot supports a narrow claim about proof-carrying, task-domain
  test augmentation for declared benchmark reference behavior.
- A review-only distinction supports candidate generation, not confirmation.
- A not-identifiable result says the V1 certificate language is too narrow; it
  does not show that official tests are sufficient.
- A no-go result falsifies this V1 approach on the frozen survivor pool.
- Merely reproducing STING with APPS and an LLM is not sufficient novelty for a
  new paper.

No implementation begins until this protocol receives independent review.
