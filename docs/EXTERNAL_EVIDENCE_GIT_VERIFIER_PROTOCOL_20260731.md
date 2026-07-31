# Production external-evidence Git verifier protocol

Date: 2026-07-31

Status: **frozen before verifier implementation or production activation**

Parent policy: `external-evidence-policy-v1`

## 0. Question

Can BenchAudit independently verify the remote identity, Git ancestry, tree
bytes, and normative-role binding claimed by an `ExternalEvidenceReceipt`,
without trusting an existing local clone or a producer-supplied boolean?

Phase 1 built and tested the policy gate. This phase builds the trust-bearing
verifier behind that gate.

## 1. Scope split

The work is divided into two separately reviewed stages:

### Phase 2A: verifier implementation

- implement host-specific Git verification;
- implement one frozen-manifest role binding (`normative` only);
- emit replayable verification transcripts;
- run constructed attacks and one APPS remote replay;
- keep every checker, CLI, and report producer disconnected.

### Phase 2B: production activation

This stage is forbidden until Phase 2A receives independent review. It may
then add an explicit consumer/CLI path and a producer receipt contract in a
separate commit and protocol.

Passing Phase 2A does not activate external evidence for real findings.

## 2. Threat model

The verifier must reject:

- a local clone whose `remote.origin.url` was rewritten;
- a fork containing attacker-created ancestry;
- a receipt that names the right commit but wrong bytes;
- a receipt or verification result replayed across another receipt;
- an unknown host treated as generic Git;
- a Git replacement object, graft, alternate object store, or local object
  injection;
- an HTTP redirect to a different origin;
- a producer-chosen source role not authorized by the frozen benchmark
  manifest;
- missing objects, shallow/incomplete ancestry, LFS indirection not covered by
  the manifest, or any verifier/tool error.

The verifier is not designed to remain sound after arbitrary modification of
BenchAudit's own trusted code or frozen manifest registry.

## 3. Trust roots

### 3.1 Trusted benchmark source manifest

Phase 2A supports one checked-in, versioned APPS manifest containing exactly:

- manifest schema and manifest ID;
- benchmark ID;
- host kind: `huggingface_dataset`;
- canonical HTTPS remote URL;
- exact cutoff commit;
- exact normative paths allowed for role binding;
- expected policy and receipt versions;
- SHA-256 of the manifest payload.

The trusted manifest hash must also be present in a code-owned allowlist. A
caller-supplied manifest path or receipt cannot extend the allowlist.

Only paths explicitly listed as `normative` may make
`role_binding_verified=True`. Metadata, correction, and search-lead roles are
out of scope for Phase 2A and fail closed.

### 3.2 Official remote

The canonical remote comes only from the trusted manifest. The verifier must
not read or trust `git remote -v` from an existing clone.

Receipt source and cutoff remotes must normalize to the manifest remote, but
that comparison alone is not proof. Fetch is performed in a new empty object
store whose only configured remote is the manifest URL.

### 3.3 Execution environment

Remote verification runs in a digest-pinned environment with:

- no mounted Git repository, object cache, credentials, SSH agent, or secrets;
- a new temporary object database for each verification;
- system/global Git configuration disabled;
- credential helpers and interactive prompts disabled;
- redirects disabled;
- only the host-specific HTTPS transport enabled;
- no alternates, grafts, or replacement refs;
- a fixed Git version recorded in the transcript;
- network egress restricted to the manifest's canonical host.

Failure to enforce or attest any item is `unverifiable`.

## 4. Host-specific handlers

Unknown hosts fail closed. There is no generic "try Git" fallback.

### 4.1 GitHub handler

Accepted form:

`https://github.com/<owner>/<repository>.git`

The handler rejects SSH, `git://`, `file://`, embedded credentials, query
strings, fragments, alternate ports, and redirects. Git LFS pointers are
rejected unless a later protocol explicitly freezes LFS object verification.

### 4.2 Hugging Face dataset handler

Accepted form:

`https://huggingface.co/datasets/<owner>/<repository>`

The handler applies Hugging Face dataset-repository semantics and separately
detects Git LFS pointer blobs. Phase 2A can confirm only ordinary Git blobs.
An LFS pointer or missing ordinary blob is `unverifiable`, not the underlying
dataset content.

## 5. Fresh-object ancestry replay

For every receipt:

1. select the trusted manifest by immutable manifest ID;
2. reject remote, cutoff, role, or path mismatch before network access;
3. initialize a new empty Git object store;
4. configure only the canonical manifest remote;
5. fetch the exact source and cutoff objects without using shallow history,
   alternates, local references, or an existing clone;
6. run full object/connectivity validation;
7. reject replacement refs, grafts, alternates, unexpected remotes, or missing
   objects;
8. calculate both ancestry directions from the newly fetched graph;
9. read the exact `commit:path` blobs from source and cutoff trees;
10. compute byte-level SHA-256 locally;
11. emit a canonical transcript binding every input, command policy, observed
    object ID, ancestry result, blob hash, manifest hash, tool version, and
    final status.

No timestamp participates in relation derivation.

## 6. Verification output

The verifier may return `ExternalEvidenceVerification(verified=True)` only
when all of the following are true:

- receipt payload SHA-256 matches the replayed receipt;
- trusted manifest hash and ID match the code-owned allowlist;
- canonical host handler accepted the remote;
- the fresh-object fetch and connectivity checks succeeded;
- exact commits and path match the receipt;
- source-tree SHA-256 matches the receipt;
- pre-cutoff verification also obtains the cutoff-tree SHA-256 required by
  policy v1;
- role binding is exactly the manifest's normative binding;
- the canonical transcript was produced without ignored errors.

Every other outcome is `verified=False` or an exception, both of which the
existing policy converts to an empty allowed-use set.

## 7. Production non-activation invariant

Until Phase 2B:

- no `benchcore` class may instantiate `ExternalEvidenceVerification`;
- no checker may emit `external_evidence_receipts`;
- no CLI/configuration path may supply `external_evidence_verifier`;
- constructed test verifiers remain under `tests/` only.

A static test enforces these conditions. Any activation requires a separately
frozen protocol and commit after independent review.

## 8. Frozen tests

At minimum, Phase 2A must cover:

1. strict ancestor: source differs from cutoff, forward ancestry true, reverse
   false, normative role, correct blobs -> all four uses;
2. equal source/cutoff commit -> valid pre-cutoff identity case;
3. reverse ancestry -> post-cutoff capability ceiling;
4. unrelated histories -> empty capabilities;
5. local clone with forged `remote.origin.url` is ignored/rejected;
6. fork-created ancestry cannot satisfy an official-manifest verification;
7. correct commits with wrong source blob hash are rejected;
8. correct source blob but wrong cutoff blob hash is rejected;
9. missing source/cutoff object or incomplete history is rejected;
10. replacement refs, grafts, and alternates are rejected;
11. relation proof missing or bound to another receipt is rejected;
12. role/path absent from the trusted manifest is rejected;
13. caller-supplied manifest or modified manifest hash is rejected;
14. unknown host is rejected before fetch;
15. GitHub and Hugging Face URLs are handled by separate parsers;
16. redirects, embedded credentials, non-HTTPS schemes, and alternate ports
    are rejected;
17. Hugging Face LFS pointer is rejected as unverifiable;
18. verifier/network/tool error cannot become a semantic rejection or
    confirmation;
19. repeated verification of the same frozen objects yields the same stable
    transcript summary SHA-256;
20. static production non-activation test remains green.

Constructed repository attacks must use isolated fixtures. The one real remote
replay is APPS only and must occur after all pre-network checks pass.

## 9. APPS real replay

Frozen target:

- benchmark: `codeparrot/apps`;
- host: Hugging Face dataset repository;
- cutoff: `21e74ddf8de1a21436da12e3e653065c5213e9d1`;
- normative path: `README.md`;
- expected SHA-256:
  `bc954bda94e94e9ce92d80ec16d69607444fcdff240cae89df6ca84ff497e846`.

The existing offline positive fixture is not accepted as the real replay. The
production verifier must fetch against the trusted manifest and reproduce the
ancestry/tree facts itself.

## 10. Required artifacts

- trusted APPS source manifest and payload hash;
- verifier source and source SHA-256;
- canonical per-run verification transcript;
- stable transcript summary and SHA-256;
- constructed attack results;
- fresh-clone targeted and full-suite test results;
- explicit zero-production-activation receipt.

Raw credentials, Git object packs, repository clones, and dataset bytes must
not be committed.

## 11. Go / no-go

`PASS_VERIFIER_NOT_ACTIVATED` requires:

- all 20 frozen tests pass;
- all attacks fail closed;
- APPS real replay reproduces the pinned remote, exact commit relation, role
  binding, and README SHA-256;
- repeated transcript summaries are deterministic;
- production non-activation remains mechanically true;
- full repository tests pass from a fresh clone.

Any false acceptance, host fallback, local-clone trust, role ambiguity,
content mismatch, nondeterministic transcript, or accidental activation is
`FAIL`.

Network unavailability, official object unavailability, unsupported LFS, or
inability to enforce the execution boundary is
`NOT_IDENTIFIABLE_PRODUCTION_VERIFIER`. It must not be converted into a local
fixture pass or a widened host policy.
