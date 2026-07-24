# BenchAudit

[![CI](https://github.com/SUPERZJ827/BenchAudit/actions/workflows/ci.yml/badge.svg)](https://github.com/SUPERZJ827/BenchAudit/actions/workflows/ci.yml)

BenchAudit is an evidence-aware quality and evaluator auditing framework for
LLM and agent benchmarks.

It treats a benchmark as a measurement system rather than a flat question-and-
answer file. The system inspects five core artifacts:

```text
task
context / attachments
output contract
oracle / ground truth
evaluator / rubric / tests
```

The central design rule is:

> Confidence is not proof.

LLM judgements, model disagreement, and behavioral anomalies can prioritize
review, but they cannot automatically confirm a benchmark defect. Automatic
confirmation requires a registered, replayable proof whose assumptions are
checked again by the central promotion policy.

This is a research system. It can automatically adapt schemas and audit plans
for several benchmark families, but it does not claim to detect every defect in
an arbitrary benchmark.

## Highlights

- Artifact-aware schema normalization for JSON, JSONL, CSV, TSV, and Parquet.
- Package scanning and capability-aware audit planning.
- Automatic routing for generic QA, SWE-bench, WorkspaceBench, and
  TerminalBench-style inputs.
- Static, dataset-level, metamorphic, mutation, cross-artifact, and
  execution-grounded checks.
- Fail-closed evidence tiers: `confirmed`, `review`, and `unknown`.
- Review-only response triage using archived multi-model correctness results.
- Strict TraceBundle ingestion for archived runs, artifacts, rubric verdicts,
  repeated attempts, and identical controls.
- Deterministic defect injection, provenance manifests, and regression scoring.
- Container-backed execution with read-only filesystems, no network, dropped
  capabilities, resource limits, and digest-pinned production images.
- Explicit data-egress opt-in for remote LLM-backed checks.

## Why audit the benchmark?

A low model score does not necessarily imply a model capability failure. It can
also be caused by:

- an ambiguous or underspecified task;
- missing context or attachments;
- an incorrect or non-unique gold answer;
- an output contract that conflicts with the evaluator;
- a test suite that rejects valid alternatives;
- a comparator that accepts behaviorally wrong outputs;
- a parser, environment, rubric, or judge failure.

BenchAudit separates these failure surfaces so that “no finding” is not confused
with “the required artifact or verifier was unavailable.”

## Evidence model

| Tier | Meaning | Typical evidence |
|---|---|---|
| `confirmed` | Replayable objective contradiction with validated prerequisites | Live artifact replay, deterministic dataset proof, trusted execution attestation |
| `review` | Useful candidate that still admits another explanation | LLM semantic judgement, response anomaly, untrusted/shared execution |
| `unknown` | Required artifact, mapping, adapter, or verifier is missing | Unsupported family capability, incomplete package, unverified adapter |

Severity and evidence strength are deliberately orthogonal. A potentially
critical issue can still remain `review` or `unknown`.

The central authority is `benchcore/promotion.py`. New checkers do not gain
confirmation rights merely by setting a high confidence or a local boolean.

## Installation

Python 3.10 or newer is required.

```bash
git clone https://github.com/SUPERZJ827/BenchAudit.git
cd BenchAudit

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Optional dependencies for the research analysis scripts:

```bash
python -m pip install -e ".[research]"
```

Run the test suite:

```bash
pytest -q
```

## Quick start

### 1. Inspect an unknown benchmark package

```bash
benchcore plan /path/to/benchmark \
  --out reports/audit_plan.json \
  --md reports/audit_plan.md
```

The plan records:

- detected benchmark family and confidence;
- present and missing artifacts;
- selected, skipped, ineligible, and unsupported checks;
- whether an LLM or execution environment is required.

Planning never silently purchases an LLM call.

### 2. Run the default audit

```bash
benchcore audit benchmark.jsonl \
  --profile auto \
  --out reports/audit.json \
  --md reports/audit.md \
  --print-summary
```

The default path is deterministic. Remote LLM-backed checks require explicit
flags and explicit permission to send benchmark data.

### 3. Inspect or override field mapping

```bash
benchcore infer-mapping benchmark.jsonl

benchcore canonicalize benchmark.jsonl \
  --mapping mapping.json \
  --out canonical.jsonl
```

Common source fields are mapped into a stable `BenchmarkItem`, while the
original row remains available for family-specific checks and provenance.

### 4. Audit with selected semantic methods

```bash
benchcore audit benchmark.jsonl \
  --llm-audit \
  --llm-auditors gold,question,option \
  --llm-config configs/llm_deepseek.json \
  --allow-remote-data-egress \
  --out reports/semantic_audit.json
```

LLM findings remain review evidence. A model vote, including a unanimous vote,
does not automatically enter the `confirmed` tier.

### 5. Triage using archived model responses

If per-item correctness results already exist, candidate ranking can be
improved without asking models to solve the benchmark again:

```bash
benchcore triage-responses path/to/model-response-directory \
  --report reports/audit.json \
  --panel-kind independent-models \
  --minimum-models 5 \
  --minimum-responses-per-item 5 \
  --audit-score-mode priority-risk \
  --out reports/response_triage.json \
  --md reports/response_triage.md \
  --print-summary
```

Supported response representations include:

```json
{"id": "q1", "correct": {"model-a": true, "model-b": false}}
{"item_id": "q1", "model_id": "model-a", "correct": true}
{"id": "q1", "correct": true}
```

The third form is used when each model has its own JSONL file.

The loader:

- joins by stable item ID rather than row order;
- rejects duplicate `(item_id, model_id)` pairs;
- accepts only JSON booleans or integer `0/1`;
- audits model and item coverage;
- disables fusion when correctness-pattern diversity is insufficient;
- records whether columns are independent models, prompt views, or repeated
  runs;
- emits Wilson intervals for finite response panels.

All response-triage rows are `review-only`. High error rate can indicate a
defect, genuine difficulty, missing knowledge, or ambiguity; it is not a defect
probability.

### 6. Ingest archived execution traces

When full runs, rubric verdicts, output digests, or repeated trials are already
available, normalize and inspect them without executing the benchmark again:

```bash
benchcore triage-traces examples/tracebundle_v1.json \
  --out reports/trace_audit.json \
  --md reports/trace_audit.md \
  --normalized-out reports/tracebundle.normalized.json \
  --responses-out reports/trace_responses.jsonl \
  --print-summary
```

TraceBundle joins observations by stable IDs, rejects duplicate runs and unsafe
artifact paths, preserves source SHA-256 digests, measures identical-control
and repeated-run disagreement, and can export strict correctness observations
for `triage-responses`. It performs no API calls or code execution. All trace
candidates remain `review-only`; observational disagreement is not independent
proof of a benchmark defect.

See [`docs/tracebundle_v1.md`](docs/tracebundle_v1.md) for the schema, intake
checklist, privacy boundary, and adapter guidance.

### 7. Route audits with defect-pattern memory

Defect-pattern memory stores reusable failure mechanisms and verifier recipes,
not historical task text or answers. Matching uses only schema/evaluator
features, capabilities, and existing audit signals:

```bash
benchcore memory-shadow benchmark.jsonl \
  --memory examples/defect_patterns.v1.jsonl \
  --dataset NewCodeBenchmark \
  --dataset-family new-code-eval \
  --feature capability:execute_candidate \
  --feature mutation_point:numeric_constant \
  --out reports/pattern_shadow.json \
  --md reports/pattern_shadow.md
```

Same-dataset and same-family evidence is excluded by default. A match only
routes a verifier and has a hard `review` ceiling; it never changes existing
findings or confirms a defect. Concrete evidence cases are provenance pointers
and do not participate in retrieval.

The zero-API leave-one-benchmark-out experiment can be replayed with:

```bash
python scripts/run_pattern_memory_evalplus_lobo.py \
  --limit-humaneval 164 \
  --limit-mbpp 378 \
  --workers 12 \
  --per-family 2 \
  --budget 6 \
  --minimum-source-witness-tasks 2 \
  --out /tmp/pattern_memory_evalplus_lobo.json
```

It requires the `research` dependencies and the local `ds1000-audit:v1`
container. The hidden outcome is original-tests-pass / EvalPlus-tests-fail.
Task text and target EvalPlus outcomes are not used for probe selection.

### 8. Build deterministic regression defects

```bash
benchcore inject-defects benchmark.jsonl \
  --seed 20260712 \
  --mutations-per-item 2 \
  --out experiments/injected.jsonl \
  --manifest-out experiments/injected.manifest.json

benchcore score-injections \
  --manifest experiments/injected.manifest.json \
  --report reports/injected_audit.json \
  --out reports/injected_recall.json
```

Every injected row records the source item, changed field, before/after hash,
operator, seed, and expected defect type. Synthetic recall is a checker
regression metric; it is not a claim about arbitrary natural-defect recall.

## Execution-grounded evaluator audit

For executable evaluators, BenchAudit can explore:

1. **Gold replay** — does the harness accept its own reference solution?
2. **Equivalent alternatives** — are behaviorally equivalent implementations
   rejected?
3. **Behavioral mutations** — do demonstrably different implementations still
   pass?

The LLM may propose probes, but execution decides the observation. Production
execution requires a digest-pinned container:

```bash
benchcore audit benchmark.jsonl \
  --execution-evaluator-audit \
  --execution-container-image \
    registry.example/benchaudit@sha256:<64-hex-digest> \
  --llm-config configs/llm_deepseek.json \
  --allow-remote-data-egress \
  --out reports/execution_audit.json
```

Host execution is disabled by default. Even when explicitly enabled through
both unsafe-local acknowledgements, its evidence ceiling remains `review`.
Execution and adjudication that share an untrusted driver also remain
`review`; a process completing successfully is not by itself a trusted proof.

## Benchmark-family behavior

| Family | Primary oracle/evaluator form | Main audit focus |
|---|---|---|
| Generic QA / MCQ | Gold answer, choices, answer contract | Gold/choice validity, ambiguity, numeric and set equivalence |
| SWE-bench / code | Repository, patch, tests | Test contract, solution leakage, executable replay |
| WorkspaceBench | Input/output files and multiple rubrics | Artifact inventory, rubric grounding, contract mismatch, counterfactual file mutations |
| TerminalBench | Task, environment, terminal behavior, tests | Static contract drift, release pairing, execution claims |

Agent benchmarks are not forced into a scalar-gold model. Missing a scalar
answer is not automatically a missing oracle when correctness is defined by
rubrics, tests, or final environment state.

## Selected results

The full tables, definitions, and limitations are in [RESULTS.md](RESULTS.md).

| Experiment | Result | Interpretation |
|---|---:|---|
| SVAMP-Platinum pilot, 100 items / 38 known defects | Candidate P/R/F1 = 0.860 / 0.974 / 0.914 | High-recall review queue; not proof-sound confirmed F1 |
| MMLU-Redux, 1,000 items / 15 archived models | Audit AP 0.573 → response-fused AP 0.734 | Archived behavior improves candidate ranking without new task execution |
| MMLU-Redux ranking sensitivity | Kendall τ = 0.981 after removing 181 objective defects | One adjacent global rank swap; no Top-1 change |
| Workspace official counterfactual study | Whole-output deletion detected in 11/11; mean −54.7 pp | Strong sensitivity to obvious absence |
| Workspace identical-output control | 6/11 independent re-evaluations changed by more than 3 pp | Fine-grained single-judge deltas require a noise control |
| Terminal enriched paired subset | Deterministic F1 0.741; union F1 0.786 | The preregistered paired-method gate still failed; the method was not promoted |
| EvalPlus structural-memory LOBO | MBPP→HumanEval task recall 0.690→0.828; HumanEval→MBPP 0.952→0.984 at equal probe counts | Cross-benchmark mutation-family priors improve verifier routing; memory remains review-only |

The EvalPlus recall denominator contains only tasks for which the frozen
mutation pool exposed at least one original-pass / stronger-oracle-fail
witness. It is verifier-routing recall within that pool, not estimated recall
over all natural benchmark defects.

Negative results are retained. In particular:

- same-model temperature sampling reduced probe recall;
- correlated prompt views did not replace independent multi-model evidence;
- psychometric fusion did not reliably beat simple response-error fusion across
  subjects;
- a semantic second-stage improved some top-K precision but did not improve
  average precision;
- stricter Terminal release pairing filtered false candidates but lost too much
  recall.

## Repository layout

```text
benchcore/                      production library and CLI
tests/                          regression and safety tests
examples/                       small runnable inputs
configs/                        API configuration templates using env-var keys
scripts/                        dataset adapters and reproducible runners
experiments/response_triage/    frozen response-triage research protocols
reports/                        selected small reproducibility artifacts
docker/                         pinned execution image recipes
DESIGN.md                       evidence and architecture design notes
RESULTS.md                      curated experiment results and limitations
```

Generated datasets, reports, model caches, secrets, and local research notes are
ignored by default.

## Security and privacy

- API keys are read from environment variables; configuration files do not
  contain credentials.
- Remote data egress requires an explicit CLI flag.
- Generated or benchmark-provided code should run only in a pinned container.
- Container execution disables networking, drops Linux capabilities, uses a
  read-only filesystem, and applies CPU, memory, and process limits.
- Reports preserve provenance and distinguish operational failures from model
  or benchmark failures.

Do not audit private benchmark artifacts with a remote model unless their data
handling policy explicitly permits it.

## Current limitations

- Automatic schema and plan adaptation does not automatically synthesize every
  unseen benchmark runtime, dependency graph, submission protocol, or parser.
- Semantic gold and rubric defects often remain review judgements.
- Response anomalies require archived per-item runs and can confound difficulty
  with benchmark defects.
- Trusted confirmation for executable benchmarks requires an independent
  adjudication boundary, not merely a successful sandbox run.
- Pattern-memory evidence currently covers executable Python evaluator
  incompleteness; broader natural benchmarks and non-code domains remain
  future work.

The intended direction is a cost-aware cascade:

```text
artifact scan
  -> deterministic checks
  -> archived-response / trace triage
  -> domain-specific verifier
  -> limited semantic review
  -> confirmed, review, or unknown
```
