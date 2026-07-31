# Production external-evidence Git verifier protocol V2

Date: 2026-07-31

Status: **frozen before V2 verifier implementation or production activation**

Parent policy: `external-evidence-policy-v1`

Supersedes only the APPS real-positive selection rule in
`EXTERNAL_EVIDENCE_GIT_VERIFIER_PROTOCOL_20260731.md`. It does not modify,
erase, or reinterpret the V1 protocol or its preflight result.

## 0. Corrected question

Can BenchAudit independently verify that a normative file is exactly the file
at a benchmark's frozen cutoff revision, while also exercising strict-ancestor
relation derivation in isolated constructed fixtures?

V1 incorrectly required the one real positive replay to satisfy two different
goals simultaneously:

1. cover the strict-ancestor branch of relation derivation; and
2. prove the normative bytes at the benchmark cutoff.

The first goal is control-flow coverage and is satisfied by a constructed Git
fixture. The second is the semantic real-replay claim. For a normative cutoff
snapshot, `source_commit == cutoff_commit` is the natural identity case: it
directly binds the receipt bytes to the benchmark revision being audited and
cannot substitute a later correction for the frozen source.

## 1. Immutable V1 history

The following V1 artifacts remain immutable:

| Artifact | SHA-256 |
|---|---|
| V1 protocol (as of hardening commit `e66ac39`) | `01798c8264b985a8a0044362230e20819891f3144f64286b2b42238eba63daaa` |
| V1 preflight report | `6576d487a49a1a53fa67838358c3b59aaac698e33a172358263ed6c1438d660c` |
| V1 source-selection receipt | `ce38712e53c32fc5283de1e1451c459ad21b1c63cdb428151e675b8fe30d50b6` |

The V1 result remains:

`NOT_IDENTIFIABLE_PRODUCTION_VERIFIER`

under the V1 requirement for a strict ancestor containing cutoff-identical
`README.md` bytes. V2 does not turn that negative result into a V1 pass.

## 2. Evidence frozen before V2

V2's real positive was checked for satisfiability before this protocol was
written. The already committed V1 source-selection receipt records a real
fetch from:

`https://huggingface.co/datasets/codeparrot/apps`

It binds:

- cutoff commit: `21e74ddf8de1a21436da12e3e653065c5213e9d1`;
- cutoff tree: `ed2c8491f8814cfde47c10aec96407485dfc233b`;
- `README.md` blob: `6053317a3ea13af4b2490691aff725e21a40268f`;
- content SHA-256:
  `bc954bda94e94e9ce92d80ec16d69607444fcdff240cae89df6ca84ff497e846`;
- fresh bare repository: true;
- existing clone and checkout used: false;
- shallow history, redirects, credentials, alternates, grafts, and replacement
  refs: false.

For the V2 identity case, source and cutoff are the same fetched commit and
therefore select the same tree entry, blob object, and content byte stream.
The required positive is mechanically satisfiable. This conclusion uses no
task outcome, API, LLM, alternate path, or post-result source selection.

## 3. Relation semantics

The policy relation table is unchanged:

| Source/cutoff graph relation | Derived relation | Maximum policy use |
|---|---|---|
| source equals cutoff | `pre_cutoff` identity | routing, detection, validation, confirmation for `normative` evidence |
| source is a strict ancestor of cutoff | `pre_cutoff` history | same uses when both source and cutoff bytes satisfy policy v1 |
| cutoff is a strict ancestor of source | `post_cutoff` | routing and validation only |
| unrelated, missing, or contradictory | `unverifiable` | empty set |

Equality is not a fallback and is not inferred from timestamps. It must be
verified from the fetched object IDs and both ancestry directions in the fresh
object database.

Policy v1 independently enforces the Git DAG invariant that bidirectional
ancestry requires identical source and cutoff commit IDs. A verifier reporting
both ancestry directions as true for distinct commits is rejected before
relation capabilities are derived. This defense was added in the separate
pre-implementation hardening commit `61c2ab0`.

Strict-ancestor behavior remains mandatory and must be covered by the frozen
constructed test. It is no longer an unnecessary precondition for the APPS
normative-cutoff positive replay.

## 4. Inherited security contract

Except for the real-positive selection rule, V2 inherits V1 Sections 2--7 and
10 without relaxation. In particular:

- the canonical remote comes only from a code-owned trusted manifest;
- local `git remote -v`, an existing clone, local refs, alternates, grafts, and
  replacement refs are never trusted;
- each verification uses a new empty object database;
- GitHub and Hugging Face use separate host handlers and unknown hosts fail
  closed;
- redirects, credentials, SSH, non-HTTPS transports, and unexpected ports are
  rejected;
- Hugging Face LFS pointers are `unverifiable` in Phase 2A;
- SHA-256 is computed over the content bytes returned by
  `git cat-file blob <blob-oid>`, excluding the Git object header;
- no working tree is checked out or hashed;
- role binding is restricted to `normative` paths in a code-allowlisted
  manifest;
- no checker, producer, CLI, or report path is activated in Phase 2A.

No V2 implementation may change `external-evidence-policy-v1` to obtain a
pass.

## 5. Frozen tests

All 20 V1 tests remain required. None is deleted or weakened. V2 adds one
policy-level adversarial test, for a total of 21 frozen tests: distinct source
and cutoff commit IDs with both ancestry directions reported true must be
rejected.

Two tests have distinct responsibilities:

1. the strict-ancestor constructed fixture must use different commits,
   forward ancestry true, reverse ancestry false, matching source/cutoff
   content under policy v1, and a valid normative role;
2. the equal-commit constructed fixture must use the same source/cutoff
   commit, both ancestry directions true, matching source/cutoff content, and
   a valid normative role.

The remaining attacks continue to cover forged remotes, fork-created ancestry,
wrong source or cutoff bytes, missing objects, incomplete history, replacement
refs, grafts, alternates, cross-receipt replay, role/path ambiguity, manifest
substitution, unknown hosts, URL attacks, LFS pointers, tool/network errors,
stable-summary determinism, and production non-activation.

The real APPS replay is an additional integration requirement, not a
replacement for either constructed branch test.

## 6. APPS V2 real replay

Frozen target:

- benchmark: `codeparrot/apps`;
- host: Hugging Face dataset repository;
- canonical remote:
  `https://huggingface.co/datasets/codeparrot/apps`;
- source commit: `21e74ddf8de1a21436da12e3e653065c5213e9d1`;
- cutoff commit: `21e74ddf8de1a21436da12e3e653065c5213e9d1`;
- required relation: equal-commit `pre_cutoff` identity;
- normative path: `README.md`;
- expected source and cutoff blob:
  `6053317a3ea13af4b2490691aff725e21a40268f`;
- expected source and cutoff content SHA-256:
  `bc954bda94e94e9ce92d80ec16d69607444fcdff240cae89df6ca84ff497e846`.

The production verifier must independently reproduce these facts from a new
empty object database configured only with the trusted-manifest remote. It may
not reuse the V1 bare repository, Git objects, or a local clone. The earlier
receipt establishes only that the positive is satisfiable; it is not accepted
as the V2 verifier's execution result.

## 7. Stable and raw transcripts

The stable-summary schema is unchanged from V1. It contains exactly:

- receipt payload SHA-256;
- trusted-manifest ID, payload SHA-256, host kind, and canonical remote;
- source/cutoff commit IDs and source path;
- fetched object IDs used for ancestry and tree lookup;
- both ancestry booleans;
- source/cutoff blob IDs and content SHA-256 values;
- role-binding result and verified role;
- host-handler ID and verifier policy/source SHA-256;
- final verified boolean, derived relation, and normalized reason code;
- security-control booleans for redirects, alternates, grafts, replacement
  refs, shallow state, credentials, and checkout absence.

Wall-clock timestamps, temporary paths, process IDs, command durations, DNS
answers, transfer sizes or speeds, and human-readable stderr are raw-transcript
fields only. Repeated raw hashes may differ; repeated stable-summary hashes
must match.

## 8. Go / no-go

`PASS_VERIFIER_NOT_ACTIVATED` requires:

- all 21 frozen tests pass;
- all constructed attacks fail closed;
- the APPS V2 real replay reproduces the pinned remote, equal-commit identity,
  role binding, blob IDs, and README content SHA-256;
- two independent real replays, each using its own new empty object database,
  produce the same stable-summary SHA-256;
- production non-activation remains mechanically true;
- targeted and full repository tests pass from a fresh clone.

Any false acceptance, host fallback, local-clone trust, role ambiguity,
content mismatch, nondeterministic stable transcript, changed policy, or
accidental activation is `FAIL`.

Network unavailability, official object unavailability, unsupported LFS, or
inability to enforce the execution boundary is
`NOT_IDENTIFIABLE_PRODUCTION_VERIFIER`. It must not be converted into a local
fixture pass, reuse of V1 objects, or a widened host/content policy.

## 9. Positive-satisfiability freeze rule

For every future protocol whose positive requires a relation between two or
more objects, protocol freezing must record before implementation:

1. the exact immutable object identifiers;
2. the exact relation required for a pass;
3. a zero-implementation preflight or earlier independent receipt showing the
   relation is satisfiable;
4. the preflight artifact SHA-256 and whether target outcomes were inspected;
5. an explicit `NOT_IDENTIFIABLE` stop if the relation is unavailable.

Branch coverage does not justify adding an unnecessary semantic condition to
a real positive. Constructed fixtures cover branches; the real replay must
test the claim actually made about the frozen benchmark artifact.

## 10. Phase boundary

Phase 2A may implement and test the verifier only after this V2 protocol is
committed. It must still end with no production activation.

Phase 2B remains forbidden until the V2 implementation, transcripts, attacks,
fresh-clone tests, and non-activation receipt receive independent review.
