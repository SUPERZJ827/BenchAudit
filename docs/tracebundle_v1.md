# TraceBundle v1

TraceBundle is BenchAudit's lightweight interchange format for archived agent
runs, evaluator results, and output artifacts. It is intentionally separate
from `BenchmarkItem`: a benchmark item describes what should be done, while a
trace bundle records what happened during one or more attempts.

The first version has three goals:

1. preserve stable item/run/system identities without relying on row order;
2. retain enough structure for deterministic consistency checks;
3. feed archived correctness observations into `triage-responses` without
   asking models to execute the benchmark again.

Trace evidence is observational. Every candidate produced by
`triage-traces` is capped at `review`; an independent replay or verifier is
still required for automatic confirmation.

The machine-readable schema is
[`configs/tracebundle_v1.schema.json`](../configs/tracebundle_v1.schema.json).

## Canonical JSON form

```json
{
  "schema_version": "tracebundle.v1",
  "benchmark_id": "my-benchmark",
  "runs": [
    {
      "run_id": "task-17__agent-a__attempt-0",
      "item_id": "task-17",
      "system_id": "agent-a",
      "attempt": 0,
      "control_id": "task-17-identical-1",
      "control_kind": "identical",
      "outcome": {
        "status": "passed",
        "correct": true,
        "score": 0.83,
        "reward": 1.0,
        "error_type": null
      },
      "events": [
        {
          "sequence": 0,
          "event_type": "process_exit",
          "timestamp": "2026-07-24T10:30:00Z",
          "message": null,
          "attributes": {"exit_code": 0}
        }
      ],
      "artifacts": [
        {
          "artifact_id": "final-output",
          "role": "output",
          "path": "outputs/task-17/result.xlsx",
          "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
          "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
      ],
      "evaluations": [
        {
          "evaluator_id": "official-judge",
          "rubric_id": "rubric-3",
          "verdict": "pass",
          "score": 1.0,
          "message": null
        }
      ],
      "metadata": {
        "environment_image": "registry.example/image@sha256:...",
        "source_trial_file": "trials/task-17.json"
      }
    }
  ]
}
```

JSONL is also supported. Each line is one run and must repeat
`schema_version` and `benchmark_id`.

## Required run fields

| Field | Meaning |
|---|---|
| `run_id` | Globally unique run identifier |
| `item_id` | Stable benchmark item identifier |
| `system_id` | Model, agent, or system identity |
| `attempt` | Non-negative repeat index |
| `outcome.status` | `passed`, `failed`, `error`, `timeout`, `cancelled`, or `unknown` |

The triple `(item_id, system_id, attempt)` must also be unique. This prevents
silent duplicate weighting and gives repeated attempts stable response-panel
columns.

## Optional evidence

- `outcome.correct`: strict JSON boolean used by response triage;
- `outcome.score`: normalized score in `[0, 1]`;
- `outcome.reward`: finite raw reward;
- `events`: ordered tool, process, judge, or environment observations;
- `artifacts`: relative artifact locators and optional SHA-256 digests;
- `evaluations`: overall or per-rubric verdicts;
- `control_id` and `control_kind`: explicitly declared paired controls;
- `metadata` and event `attributes`: benchmark-specific JSON extensions.

Unknown fields outside `metadata` or `attributes` are rejected. This catches
typos such as `succes` instead of silently treating them as new schema.

## Identical controls

Runs may declare:

```json
{
  "control_id": "same-output-task-17",
  "control_kind": "identical"
}
```

Only use `identical` when the compared condition is genuinely identical under
the frozen protocol. `triage-traces` can then measure:

- pass/fail mismatch;
- score spread;
- output artifact digest mismatch.

Declaring a control does not prove identity cryptographically. Preserve the
input, evaluator, environment, and prompt digests under `metadata` when they
are available.

## Deterministic candidates

The current implementation can flag:

- repeated pass/fail disagreement;
- repeated score instability;
- one atomic identical-control mismatch finding with outcome, score, and
  artifact modalities (rather than duplicate findings for one root cause);
- evaluators disagreeing on the same run and rubric;
- a passed run containing a non-zero process exit;
- pass/fail status disagreeing with explicit `correct`;
- a failing run receiving a high reward;
- a dataset-level cluster of errors, timeouts, or cancellations.

These are candidate-generation rules, not universal defect predicates. For
example, repeated pass/fail disagreement may be caused by a stochastic task
rather than a broken evaluator.

## CLI

```bash
benchcore triage-traces traces/ \
  --out reports/trace_audit.json \
  --md reports/trace_audit.md \
  --normalized-out reports/tracebundle.normalized.json \
  --responses-out reports/trace_responses.jsonl \
  --print-summary
```

The optional correctness export can be passed to the existing candidate
ranking layer:

```bash
benchcore triage-responses reports/trace_responses.jsonl \
  --report reports/audit.json \
  --panel-kind repeated-runs \
  --minimum-models 2 \
  --minimum-responses-per-item 2 \
  --out reports/response_triage.json \
  --md reports/response_triage.md
```

Use `independent-models` instead of `repeated-runs` only when the system
identifiers really represent independently developed models.

## Intake checklist for a new result collection

Before writing a dataset-specific adapter, preserve the raw files unchanged
and record their SHA-256 digests. Then answer:

1. What is the stable task/item ID?
2. What distinguishes systems and repeated attempts?
3. Is pass/fail an official verdict, a derived value, or an LLM judgement?
4. Is score normalized to `[0, 1]`; if not, should it remain raw reward?
5. Are rubric-level decisions available?
6. Are output files available, and can their digests be computed?
7. Are timestamps, exit codes, stdout/stderr, tool calls, and environment
   identities available?
8. Which comparisons are genuine identical controls?
9. Does the trace contain secrets, credentials, private prompts, or personal
   information that must be redacted before ingestion?
10. Can an official evaluator or replay environment later verify candidates?

The dataset-specific adapter should only translate fields into TraceBundle. It
must not decide which rows are defects or read downstream human defect labels.

## Security and privacy

`triage-traces` reads JSON only; it does not execute commands, fetch URLs, or
open referenced artifacts. Artifact paths must be relative and cannot contain
`..`. Resource limits guard file size, run count, and events per run.

Trace messages and metadata can still contain credentials or private data.
Redaction must happen before a bundle is shared or sent to a remote model. The
default trace triage itself makes no API calls.
