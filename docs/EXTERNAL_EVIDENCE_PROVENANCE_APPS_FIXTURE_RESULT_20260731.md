# External-evidence provenance gate: APPS positive fixture

Date: 2026-07-31

Branch: `feature/external-evidence-provenance-gate-20260731`

Decision: `PASS_POSITIVE_FIXTURE_ONLY`

Network/API/LLM calls: 0

## 1. Review decisions

The independent schema review was accepted with these explicit decisions:

1. The gate is opt-in. It governs findings that declare
   `external_evidence_receipts`; it is not whole-program proof that a checker
   never concealed external access.
2. `contemporaneous_metadata` remains permanently ineligible for automatic
   confirmation under policy v1. A future replayable semantic evidence class
   requires a new role and separately frozen policy revision.
3. An empty receipt list is a declared but unusable external dependency and
   fails closed.
4. Post-cutoff verification must not carry an ignored cutoff-tree blob hash.
5. The unused `ExternalEvidencePolicyDecision.present` field was removed.

## 2. Defense-in-depth scan

A repository test parses every Python module under `benchcore/`. Modules that
import a network-I/O client (`requests`, `httpx`, `socket`, or
`urllib.request`) may not directly construct `Violation`/`_violation` calls
unless that call contains `external_evidence_receipts`.

The scan exercises real network-capable modules and currently finds no direct
undeclared finding producer. It is deliberately documented as a cheap static
check, not transitive information-flow analysis.

## 3. Frozen APPS basis

The source is the existing receipt committed before APPS task outcomes were
inspected:

- repository: `codeparrot/apps`;
- revision: `21e74ddf8de1a21436da12e3e653065c5213e9d1`;
- selected normative path: `README.md`;
- content SHA-256:
  `bc954bda94e94e9ce92d80ec16d69607444fcdff240cae89df6ca84ff497e846`;
- `task_outcomes_inspected_before_receipt: false`.

The APPS receipt was imported as its original one-file historical commit. No
dataset bytes, webpage, repository, or API were fetched.

## 4. What the positive fixture proves

The fixture translates the frozen APPS fields into one `normative` receipt at
the exact cutoff revision. A constructed offline verification object binds the
exact receipt payload, same Git revision, README path, content hash, official
remote identity, and normative role.

The tests prove that this positive path is reachable:

- `derive_allowed_uses()` returns routing, detection, confirmation, and
  validation;
- the receipt permits a registered objective proof to reach its existing
  validator and become `confirmed`;
- the same receipt cannot self-confirm an unregistered proof, which remains
  `review`.

Thus the gate is not safe merely because it rejects every input.

## 5. What it does not prove

The verification object is explicitly marked `fixture_only`. This phase does
not implement or claim a production Git verifier that clones the official
remote and independently replays graph ancestry and tree blobs. The fixture
tests schema/policy/promotion integration against real frozen APPS provenance
fields; it is not a new APPS defect result or an execution attestation.

## 6. Tests

Before the result report commit:

- external-evidence targeted tests: `23 passed`;
- full repository suite: `751 passed`;
- worktree after the fixture/test commit: clean.

The targeted suite contains both allow and reject paths.

## 7. Artifact hashes

| File | SHA-256 |
|---|---|
| `docs/experiments/apps_stdin_input_receipt_20260729.json` | `9d4096cf343620a2a9c6f2e9fb241ed4ef50db2e7a59417e82dc319085a028e6` |
| `docs/experiments/apps_external_evidence_positive_fixture_20260731.json` | `83bb50f2742371892aa2df6bc82d54ab5be368874a20838e8964d252c1d51710` |
| `benchcore/external_evidence.py` | `200f27499e0e329624c7a84c9cdb7a4fb1cfe8ed62e3ff6044963d0b55994417` |
| `benchcore/promotion.py` | `1a82be75c45cda1e3abd459b8052c674a843dccdda901b4c920f4b3c9c8b66e9` |
| `tests/test_external_evidence.py` | `4f1ac1fba1e94cc47f1eb193dcb23383f00889159f2d1de3f88658989ffd8785` |

Fixture/test commit:

`208b85d63c8322c949e969eef2f17563bcce8bbe`
