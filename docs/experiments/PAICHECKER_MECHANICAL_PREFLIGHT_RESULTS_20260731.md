# PAIChecker mechanical-decidability preflight results

Date: 2026-07-31  
Decision: **`NOT_IDENTIFIABLE_DATA`**  
Stage reached: Stage 0 only  
LLM/API calls: **0**

## Outcome

The official PAIChecker repository does not currently publish the labeled
research datasets needed by the proposed evaluation. Under the frozen stop
rule, Stage 1 was not run and R-UL/R-SC1 were not implemented.

This run therefore provides **no detection-effect improvement** for
BenchAudit. Its useful result is a fast, reproducible stop: it prevents
building and tuning a detector that cannot be evaluated against the paper's
third-party labels.

## Paper verification

The paper is real and was submitted to arXiv on 2026-07-30 as
`arXiv:2607.28587v1`; it reports acceptance at ASE 2026.

The following claims in the source plan agree with the paper:

- 68/500 (13.6%) SWE-bench Verified instances were labeled as misaligned;
- the taxonomy has five pattern families and eleven scenarios;
- the evaluation sets contain 2,438 SWE-Gym and 300 SWE-bench Multilingual
  instances;
- annotator agreement is reported as Cohen's kappa 0.91 for binary judgments
  and 0.86 for fine-grained labels;
- the best reported SWE-Gym binary accuracy is 92.12%, with 84.66% exact
  match;
- removing Phase I, II, and III changes binary accuracy by -24.29, -4.71,
  and -3.15 percentage points, respectively.

One terminology correction is required: 92.12% is **binary accuracy against
human annotations**, not an "LLM consensus" rate.

## Official artifact scan

Frozen official revision:

- repository: `https://github.com/manyifire/PAIChecker`
- commit: `4f2bd0b092765891203c72a43d22eb01c305981d`
- timestamp: `2026-07-30T23:21:57+08:00`
- commit title: `Initial public release`

Aggregate scan:

| Measure | Result |
|---|---:|
| Tracked files | 25 |
| Candidate JSON/JSONL/CSV/Parquet files | 1 |
| Labeled research datasets | 0 |
| LLM/API calls | 0 |

The only candidate data file is `examples/dp_example.jsonl`:

- one record;
- contains source-evidence fields such as `instance_id`,
  `problem_statement`, `pr_description`, `patch`, and `test_patch`;
- contains no human label field;
- is explicitly documented as one example input, not evaluation data.

The official README states that the public repository contains the core
detector, one example, and assistant skills, and does not contain the raw
research datasets, historical outputs, evaluation artifacts, or all material
needed to reproduce the paper.

This conflicts with the paper's statement that all annotated data and
artifacts are publicly available. The result records the observable
repository state rather than trying to resolve that publication mismatch by
substituting other data.

## Method review of the proposed rules

The high-level direction remains useful: PAIChecker identifies an important
benchmark-defect family, and BenchAudit's locally replayable confirmation
contract is meaningfully different from PAIChecker's LLM-agent
self-correction.

However, the original v1 rule definitions are not yet confirmation-safe.

### R-SC1

Counting every `#N` reference is insufficient. The paper itself gives cases
where a multi-issue reference is a typo or where several issues share one
root cause and should not be labeled scope creep. A future mechanical
observation must distinguish issue-closing references from contextual
references and bind them to repository metadata. Even then, the objective
observation "PR declares multiple closing issues" must be kept separate from
the semantic claim "the benchmark task is defective."

### R-UL

A test literal absent verbatim from the issue is not sufficient: legitimate
tests routinely assert derived values, identifiers, internal constants, and
representative examples absent from prose. PAIChecker's UL definition also
requires that the PR introduce the same fixed runtime literal and that the
test assert it. A confirmation-safe future rule therefore needs:

1. a literal extracted from an assertion in the test patch;
2. the identical literal introduced in the production patch;
3. absence from the normative issue text after normalization;
4. a mechanical reason that the literal is not derivable from the task
   contract;
5. fail-closed abstention when any role or derivation is ambiguous.

Without those conditions, R-UL can only produce review candidates.

## Gate calculation

Stage 0 failed before the Stage 1 denominator could be formed:

- unique labeled records available: 0;
- extractable labeled records: not measurable;
- combined extractability: not measurable;
- any group with at least 30 extractable records: no.

Decision:

```text
NOT_IDENTIFIABLE_DATA
official_repository_contains_no_labeled_research_dataset
```

Per protocol, no substitute labels were gathered, no target records were
manually reconstructed, and no detector was implemented.

## What this means for BenchAudit

PAIChecker is useful in three ways today:

1. it independently validates PR-issue misalignment as a consequential
   benchmark-quality problem;
2. it sharpens BenchAudit's novelty boundary: LLM discovery and
   self-correction already exist, so our defensible contribution must be
   locally replayable, fail-closed confirmation;
3. it supplies a promising external evaluation target **if and when** the
   announced annotations are actually released.

It does not currently supply a runnable labeled experiment, cannot replace
the failed DBCode Phase A target, and has not improved BenchAudit's measured
precision, recall, confirmed count, or coverage.

## Reproduction

Receipt:
`docs/experiments/paichecker_data_receipt_20260731.json`

Scanner:
`scripts/scan_paichecker_artifact.py`

Run:

```bash
python scripts/scan_paichecker_artifact.py \
  /path/to/official/PAIChecker \
  --out docs/experiments/paichecker_data_receipt_20260731.json
```

The receipt contains only aggregate schemas, paths, sizes, and hashes. It
does not reproduce issue, PR, patch, or comment text.

## Reopen condition

Reopen Stage 0 only when the official repository (or an author-linked
official artifact) publishes:

- per-instance human labels;
- stable `instance_id` linkage;
- enough issue/PR/test evidence to evaluate at least one proposed group.

When reopened, pin the new artifact commit and rerun the unchanged scanner.
Do not lower the Stage 1 20% / 30-instance gate based on the newly visible
outcomes.
