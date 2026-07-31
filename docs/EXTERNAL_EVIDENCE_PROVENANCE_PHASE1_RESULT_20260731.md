# External-evidence provenance gate: Phase 1 result

Date: 2026-07-31  
Branch: `feature/external-evidence-provenance-gate-20260731`  
Decision: `PASS_CONSTRUCTED_GATE`  
Network/API/LLM calls: 0

## 1. Scope

This phase implements only the frozen schema, pure policy derivation, central
promotion gate, and constructed/adversarial tests. It does not fetch or
classify any real external source and does not change a previously frozen
experiment result.

APPS fixture backfilling remains a later phase.

## 2. Commits

| Commit | Purpose |
|---|---|
| `ef1a606592097ac0456c7f98b77bdc2952ddaf82` | Freeze addendum and policy table before implementation |
| `356cdd7a021f81dae5b6d54ca009c9929dbd6762` | Implement receipt schema, pure policy, and central gate |
| `2e6b3a45f7b9d43db2fbeb5fae322c8a72362c8e` | Add constructed and promotion-integration attacks |

The result report is a post-result documentation commit and does not alter the
implementation or tests above.

## 3. Implemented trust split

`ExternalEvidenceReceipt` is an untrusted source claim. It records immutable
Git identifiers, a path, a content hash, source role, and policy version. It
does not contain a trusted permission decision; unknown caller fields such as
`allowed_uses` and cached policy decisions are ignored.

`ExternalEvidenceVerification` is returned by a separately configured
verifier. It binds the exact receipt payload hash, pinned official remote,
source-role provenance, Git objects, path, observed source/cutoff tree hashes,
and graph ancestry facts.

`derive_allowed_uses()` is pure: it performs no filesystem, Git, network, API,
or model operation. It:

1. rejects unknown receipt or active-policy versions;
2. rejects missing or mismatched proof bindings;
3. derives cutoff relation from independently replayed ancestry facts;
4. verifies tree content hashes;
5. intersects role and relation capabilities.

## 4. Frozen derivation table

Role capabilities:

| Role | routing | detection | confirmation | validation |
|---|---:|---:|---:|---:|
| `normative` | yes | yes | yes | yes |
| `contemporaneous_metadata` | yes | yes | no | yes |
| `post_cutoff_correction` | yes | no | no | yes |
| `search_lead` | yes | no | no | no |

Relation capabilities:

| Derived relation | routing | detection | confirmation | validation |
|---|---:|---:|---:|---:|
| `pre_cutoff` | yes | yes | yes | yes |
| `post_cutoff` | yes | no | no | yes |
| `unverifiable` | no | no | no | no |

The effective set is the intersection. Multiple receipts are also intersected,
so adding a weaker source cannot increase authority.

## 5. Central promotion behavior

When `external_evidence_receipts` is present:

| Derived authority | Promotion behavior |
|---|---|
| no `detection` | force `unknown` |
| `detection`, no `confirmation` | cap at `review` |
| includes `confirmation` | proceed to the existing exact proof registry and validator |

Therefore a trusted normative receipt is a prerequisite, not proof by itself.
An unregistered proof remains `review`.

Findings that declare no external receipts preserve the previous promotion
behavior.

## 6. Adversarial coverage

The 18 new tests include:

- caller-forged `allowed_uses`;
- cached old policy decisions;
- unrelated Git histories;
- missing relation proof;
- correct ancestry with a wrong cutoff-tree content hash;
- receipt/verification payload mismatch;
- fake verification remote;
- unknown receipt and active-policy versions;
- absent independent verifier;
- multiple-receipt capability intersection;
- validation-only evidence attempting substantive detection;
- metadata attempting confirmation;
- normative evidence attempting to self-confirm an unregistered proof;
- unchanged behavior for findings without external evidence.

## 7. Reproduction

Fresh clone:

`/tmp/benchaudit-external-evidence-gate-fresh-20260731-1507`

Checked-out commit:

`2e6b3a45f7b9d43db2fbeb5fae322c8a72362c8e`

Results from that fresh clone:

- targeted: `18 passed`;
- full suite: `746 passed`;
- worktree before tests: clean.

No uncommitted file from the implementation worktree participated in those
tests.

## 8. Artifact hashes

| File | SHA-256 |
|---|---|
| `docs/EXTERNAL_EVIDENCE_PROVENANCE_ADDENDUM_20260731.md` | `1d42c7d8ec870203d2c9b906b1c0d093b685de6b0710942933496bd10ba15fe7` |
| `benchcore/external_evidence.py` | `8391a088092f218e30cfcf680e0247eb05a61e1360d7a6c1d3c9ed088089cc80` |
| `benchcore/promotion.py` | `1a82be75c45cda1e3abd459b8052c674a843dccdda901b4c920f4b3c9c8b66e9` |
| `tests/test_external_evidence.py` | `0cfccf5d3403c8fa50a02fa4912170db331f9d42e4173d3ff017c292110aa529` |

## 9. Boundary

Phase 1 proves that producer-controlled permission claims cannot cross the
constructed central gate when the finding declares external evidence. This is
an opt-in provenance contract: it does not prove that a checker cannot conceal
external access by omitting the receipt field. It does not yet prove a real Git
verifier implementation or a real APPS provenance fixture. With no configured
verifier, the implementation fails closed.
