# External-evidence provenance addendum

Date: 2026-07-31  
Status: frozen before implementation  
Scope: schema, policy derivation, promotion gate, and constructed tests only  
Network/API/LLM budget: zero

This is a new policy addendum. It does not modify any previously frozen
experiment protocol or retroactively change an experiment result.

## 1. Goal

External material may help BenchAudit identify a benchmark protocol, route a
candidate, or validate a result. It must not acquire confirmation authority
merely because a producer wrote `pre_cutoff`, `verified`, or
`permitted_use=detection` into a JSON object.

The implementation therefore separates:

1. an immutable source receipt;
2. an independent provenance verifier;
3. a pure `derive_allowed_uses()` policy function;
4. a central promotion gate that calls the verifier and ignores caller-supplied
   permission claims.

## 2. Non-goals

- No website, repository, dataset, or API is fetched in this phase.
- No existing PAIChecker labels are reconstructed from substitute sources.
- No execution environment is authorized by this receipt. Container digest,
  dependency state, isolation, and transcript attestation remain execution
  contract responsibilities.
- No arbitrary web page can become pre-cutoff evidence from a timestamp alone.

## 3. Immutable cutoff and relation proof

A Git cutoff is identified by:

- normalized official remote URL;
- full cutoff commit object ID;
- full source commit object ID;
- source path in the cutoff history;
- SHA-256 of the source bytes.

Commit dates are descriptive metadata only. They never establish temporal
relation.

For one Git repository:

- `pre_cutoff` requires the source commit to be an ancestor of the cutoff
  commit and the recorded content hash to match the verified tree/blob bytes;
- `post_cutoff` requires the cutoff commit to be an ancestor of the source
  commit and the recorded content hash to match the verified source bytes;
- unrelated commits, absent proofs, different remotes, or unverifiable sources
  produce `unverifiable`.

The I/O-bearing verifier performs graph and content checks against a pinned
official remote. The policy function is pure and consumes only its structured
verification result.

A hash of the `.git` directory is deliberately excluded. Clone packing,
reflogs, object layout, and local configuration are not deterministic trust
roots. The trust binding is the normalized official remote plus content
addressed Git objects and replayed tree bytes.

## 4. Source role is provenance, not keyword classification

Roles:

- `normative`: material selected by the benchmark manifest as an instruction,
  evaluator, harness, or official task contract;
- `contemporaneous_metadata`: metadata attached to the benchmark construction
  or source repository but not itself the task contract;
- `post_cutoff_correction`: errata, known-problem reports, corrective PRs, or
  other material whose role is to reveal/repair a defect;
- `search_lead`: an unverified discovery lead.

A GitHub issue can be normative when the benchmark manifest uses that issue as
the problem statement. Words such as `bug`, `wrong`, and `incorrect` do not
determine role. Role binding must be independently verified against the
benchmark manifest/provenance graph.

## 5. Schema

`ExternalEvidenceReceipt` contains:

- receipt and declared policy versions;
- source role;
- source and cutoff remote URLs;
- source and cutoff commits;
- source path and content SHA-256;
- relation-proof descriptor.

The receipt contains no trusted `allowed_uses`. Unknown input fields with that
name are ignored.

`ExternalEvidenceVerification` is returned by a configured verifier and binds:

- verifier trust domain;
- official remote acceptance;
- role-binding result;
- verified relation (`pre_cutoff`, `post_cutoff`, or `unverifiable`);
- exact source/cutoff commits, path, and observed content hash.

Missing verification, missing relation proof, mismatched bindings, unknown
policy versions, or verifier errors fail closed.

## 6. Pure policy table

Role capabilities:

| Role | routing | detection | confirmation | validation |
|---|---:|---:|---:|---:|
| normative | yes | yes | yes | yes |
| contemporaneous_metadata | yes | yes | no | yes |
| post_cutoff_correction | yes | no | no | yes |
| search_lead | yes | no | no | no |

Relation capabilities:

| Relation | routing | detection | confirmation | validation |
|---|---:|---:|---:|---:|
| pre_cutoff | yes | yes | yes | yes |
| post_cutoff | yes | no | no | yes |
| unverifiable | no | no | no | no |

`derive_allowed_uses()` returns the intersection of role and relation
capabilities only when every binding and active-policy check succeeds.

Consequences:

- normative + verified pre-cutoff may be a prerequisite of a confirmation, but
  never confirms a finding by itself;
- contemporaneous metadata cannot independently confirm;
- corrections cannot enter detection even if their commit is pre-cutoff;
- unverifiable evidence has an empty allowed-use set;
- an old receipt is re-derived under the active policy and never reuses a
  cached permission result.

`contemporaneous_metadata` deliberately has no confirmation capability. A
pinned GitHub event, release record, or cross-PR link proves that the metadata
snapshot existed; it does not by itself prove benchmark semantics or evaluator
behavior. If a future evidence class has an independently replayable semantic
proof, it must receive a new role and a separately frozen policy revision. The
current metadata role will not be silently widened.

## 7. Central promotion behavior

If a finding declares `external_evidence_receipts`:

1. promotion parses every receipt;
2. it calls the configured independent verifier for each receipt;
3. it re-runs `derive_allowed_uses()` using the active policy;
4. permissions are intersected across all receipts;
5. missing `detection` produces `unknown`;
6. detection without `confirmation` caps the finding at `review`;
7. only evidence allowed for confirmation proceeds to the existing exact proof
   tuple and proof validator.

With no configured verifier, external evidence is unverifiable and cannot
enter detection. Existing findings with no external receipt are unchanged.

An explicitly declared empty `external_evidence_receipts` list means that the
finding declared an external-evidence dependency but supplied no usable
receipt. It therefore fails closed to `unknown`; it does not mean "no external
evidence was needed." A producer that did not use external evidence must omit
the field.

## 8. Opt-in boundary

This gate governs **declared** external evidence. It cannot prove that an
arbitrary checker did not access external information and omit the receipt.
Accordingly, the valid claim is:

> Declared external evidence cannot gain detection or confirmation authority
> without independent provenance replay and policy derivation.

It is not valid to claim that BenchAudit prevents every undeclared network or
out-of-band input from influencing a checker. A repository-level static test
detects the cheaper direct failure mode: a module that imports a network I/O
client and directly constructs findings without declaring external receipts.
That scan is defense in depth, not whole-program information-flow proof.

## 9. Frozen constructed tests

At least these ten behaviors must be tested:

1. verified normative pre-cutoff evidence permits all four uses;
2. post-cutoff correction permits routing and validation only;
3. an older timestamp on a non-ancestor commit remains unverifiable;
4. caller-supplied `allowed_uses=["confirmation"]` is ignored;
5. unverifiable evidence has an empty allowed-use set;
6. correct ancestry with a mismatched content hash is rejected;
7. absent/empty relation proof is rejected;
8. unknown policy version is rejected;
9. an old receipt is recomputed under the active policy, not cached;
10. verification against a different/untrusted remote is rejected.

Additional integration tests must show:

- validation-only evidence cannot produce a substantive detection decision;
- detection-only evidence cannot promote a registered objective proof;
- trusted normative evidence does not self-confirm an unregistered proof;
- no verifier fails closed;
- findings without external receipts preserve current promotion behavior.

All pass claims must come from a fresh clone containing only committed files.

## 10. Completion boundary

This phase is complete when:

- `derive_allowed_uses()` is a file/network-independent pure function;
- the central gate consumes verifier output rather than producer permission
  fields;
- the frozen constructed and integration tests pass from a fresh clone;
- no network or model call occurred.

APPS is intentionally deferred until this constructed gate passes independent
review.
