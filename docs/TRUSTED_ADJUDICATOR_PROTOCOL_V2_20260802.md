# BenchAudit Trusted Adjudicator Protocol V2 — OS-Visible Observations

> Status: **frozen before implementation; pending independent review**
>
> Protocol date: 2026-08-02
>
> Current pre-implementation conclusion: **OS-visible stdout is structurally identifiable under the frozen trust assumptions; no production path is activated**
>
> Scope: raw stdout/stderr bytes, exit status, and bounded file artifacts captured at an OS boundary. In-memory language objects are explicitly outside V2.

## 0. Purpose and claim boundary

V2 corrects two scope defects in V1 without modifying V1 or activating any proof:

1. It narrows V1's negative conclusion to in-memory language-level observations.
2. It evaluates OS-visible observations under an explicit `non_adaptive_pre_cutoff` adversary model.

The V2 claim is deliberately conditional:

> A trusted capture supervisor that owns the process pipes or artifact directory can attest the exact bytes emitted by a frozen sandbox execution and can apply a pre-registered byte-level contract without importing benchmark code. Confirmation is admissible only when the benchmark harness revision is mechanically bound to the non-adaptive pre-cutoff model and every capture, contract, and attestation condition below succeeds.

V2 does not claim Byzantine-harness security. It does not establish that arbitrary bytes are semantically correct merely because a process emitted them. It establishes provenance for the observable bytes, then relies on a trusted, pre-registered contract for their interpretation.

## 1. Relationship to V1

### 1.1 Immutable parent protocol

The parent document is:

| Object | Value |
|---|---|
| Path | `docs/TRUSTED_ADJUDICATOR_PROTOCOL_V1_20260802.md` |
| SHA-256 | `9cbe5b1badf62540bd113b8822a1a584d8bcd3d9995a602fb14c7b7ad020cb0f` |
| Commit | `4193ee2` |
| Status | frozen historical protocol; not edited by V2 |

### 1.2 One rule superseded, nothing else reinterpreted

V1's unqualified `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR` is superseded only as follows:

| Observation form | Governing result |
|---|---|
| In-memory Python/language object with no independent capture boundary | `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR_IN_MEMORY`; V1's reasoning and stop rule remain in force |
| OS-visible stdout/stderr raw bytes and exit status | Evaluated by V2 |
| OS-visible file artifact captured from a dedicated sandbox output boundary | Evaluated conditionally by V2 |
| Any observation outside these classes | Not evaluated; highest admissible tier remains review |

V2 does not turn the historical DS-1000 ids 11 or 300 into confirmed findings. It does not weaken the id 308 negative control. It does not remove any entry from `DISABLED_UNATTESTED_PROOFS`.

### 1.3 Why the in-memory and OS-visible cases differ

The mechanically relevant distinction is:

> For an in-memory object, untrusted code controls the serializer that claims which bytes represent the object. For an OS-visible stream, the trusted supervisor owns the receiving pipe endpoint and the kernel supplies the exact bytes written by the sandbox execution group; there is no caller-selected serializer between the observable and the capture.

The child may choose arbitrary bytes. That is not a provenance ambiguity: “the sandbox execution emitted these bytes” is exactly the observation. Whether those bytes satisfy the benchmark contract is a separate, trusted comparison question.

## A. Observation-form classification

### A.1 In-memory language-level object

- Observable: Python/R/Java/other runtime object.
- Capture boundary: none independent of the interpreter that constructs it.
- Typical examples: pandas DataFrame held in a DS-1000 harness, Python object passed directly to `exec_test`.
- V2 status: not evaluated; V1's `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR_IN_MEMORY` applies.

Serializing the object in the same interpreter and sending the result over a pipe does not convert it into an OS-visible trusted observation. The emitted bytes would still be a claim about the hidden object rather than the benchmark output itself.

### A.2 OS-visible byte stream and exit status

- Observable: raw stdout bytes, raw stderr bytes, EOF, process-group completion status, signal/timeout/overflow flags.
- Capture boundary: kernel pipes owned by a trusted supervisor outside the sandbox execution group.
- Typical example: APPS stdin/stdout program execution.
- V2 status: structurally identifiable if §§B–F are satisfied.

The semantic output stream must be explicitly named. Stderr is never silently merged into stdout. Exit status is a separate typed observation, not text appended to either stream.

### A.3 OS-visible file artifact

- Observable: bounded file bytes and metadata from a dedicated output directory after the execution group is terminated and the directory is sealed.
- Capture boundary: supervisor-controlled mount or export boundary, opened by descriptor rather than benchmark-supplied path traversal.
- Typical examples: generated workbook, JSON result file, rendered report.
- V2 status: conditionally identifiable. APPS stdout, not file output, is the V2 frozen positive.

A compliant file capture must reject symlinks, device files, sockets, FIFOs, hard links escaping the output tree, path traversal, mutable external mounts, oversize files, unexpected file counts, sparse-file abuse, and files still open by a live descendant. If those controls are not available, file observation remains review-only.

## B. Provenance of OS-visible observations

### B.1 Trusted capture supervisor

The capture supervisor is a separate trusted executable/runtime that:

1. creates the stdin, stdout, and stderr pipes;
2. launches the pinned sandbox/container execution;
3. owns the only receiving endpoints;
4. streams raw bytes into bounded content-addressed buffers without decoding;
5. monitors the whole sandbox process group/cgroup, not only its initial PID;
6. records completion, signal, timeout, overflow, and descendant state;
7. applies or invokes only a code-owned comparison contract;
8. constructs and signs the canonical observation transcript; and
9. never exposes its private key to the caller, harness, candidate, or container runtime.

The ordinary BenchAudit parent may request work and verify a signed result. It may not submit a prebuilt observation and ask the supervisor to bless it.

### B.2 What a pipe proves

If the trusted supervisor owns the receiving endpoint, captured bytes can only enter through writes to the corresponding kernel pipe by a process that holds the write endpoint. V2 therefore defines the source scope as:

```text
output_source_scope = sandbox_execution_group
```

not “initial child PID.” A descendant inheriting the file descriptor is part of the observed execution group unless the benchmark contract forbids descendants.

If a contract requires output specifically from the initial process and the supervisor cannot distinguish writers, the observation is not identifiable under V2 and must abstain.

### B.3 Descendant processes writing the same descriptor

Possible cases and handling:

| Case | Handling |
|---|---|
| Descendants are allowed and remain inside the sandbox process group/cgroup | Their writes are part of `sandbox_execution_group` output; record descendant count if observable |
| Descendants are prohibited by the frozen execution contract | Any descendant causes abstention or operational failure, never confirmation |
| Descendant survives the leader and holds a pipe open | Supervisor kills the complete group, marks incomplete/descendant-retained-pipe, and abstains |
| Writer identity cannot be bounded to the sandbox group | Abstain |

The current `_communicate_bounded` code already recognizes that descendants can retain inherited pipes. V2 does not treat that recognition as a complete trusted implementation.

### B.4 Container-runtime mediation

`ContainerRunner` launches a container engine CLI, so the host pipe receives bytes forwarded by the container runtime rather than directly from the candidate PID. The runtime and its demultiplexing behavior are therefore part of the trusted computing base.

A future implementation must bind:

- container engine name, version, executable hash, and invocation schema;
- digest-pinned container image;
- separate stdout/stderr channel behavior;
- network-disabled, read-only, non-root, capability-dropped policy;
- stdin forwarding mode (`-i`) and exact stdin hash; and
- a tested rule that no runtime prefix, multiplex header, progress output, or diagnostic text enters the semantic stdout channel.

Unknown engines or versions fail closed. A free-form engine selected by the caller is not admissible.

### B.5 Raw bytes, non-UTF-8, and normalization

Trusted capture operates on bytes. UTF-8 decoding with `errors="replace"` is not admissible evidence because different byte strings can map to the same replacement text.

The transcript binds:

- full stdout byte length and SHA-256;
- full stderr byte length and SHA-256;
- inline bytes only when under a frozen size limit, otherwise a supervisor-owned content-addressed blob;
- EOF/completeness flags; and
- exit/signal status separately.

Any whitespace, numeric, line, or token normalization happens only inside a registered comparator and never changes the raw observation hash.

### B.6 Truncation and overflow

The present `_BoundedTextCapture` preserves head/tail text after overflow. That is suitable for diagnostics but not a complete output observation.

V2 freezes this rule:

> If semantic stdout or a required file exceeds the frozen complete-capture budget, the capture is `overflow_incomplete` and confirmation is impossible. Head/tail previews may be retained as raw diagnostics only.

No truncated stream may be compared as though it were the full output. A size-only proof is allowed only if a separately registered contract explicitly concerns size and does not require missing bytes; APPS V2 does not use such a contract.

### B.7 Stdout/stderr interleaving

Stdout and stderr remain separate byte streams. The supervisor may record per-stream chunk order for diagnostics, but no semantic contract may infer a total cross-stream order unless the capture mechanism provides one and the manifest explicitly requires it.

For APPS, only complete stdout participates in the output comparator. Nonempty stderr is recorded but is not automatically failure unless the frozen execution contract says so.

### B.8 Timeout and partial output

On timeout the supervisor:

1. marks the run `timeout` before interpreting any bytes;
2. terminates the whole sandbox group/cgroup;
3. drains or closes pipes under a bounded cleanup deadline;
4. records partial byte hashes as diagnostics; and
5. produces no semantic accept/reject/equality result.

The same applies to signal death, runtime crash, pipe error, missing EOF, cleanup failure, and output overflow. Partial output can never be promoted as complete output.

### B.9 File-artifact sealing

For file protocols, the supervisor must stop the execution group before capture, then seal the output mount read-only. It enumerates entries using descriptor-relative operations, applies a code-owned path allowlist/contract, hashes raw bytes, and signs the entire inventory. Any change between enumeration and read, unsupported inode type, external link, or post-seal mutation causes abstention.

No file path supplied by benchmark text is opened outside the dedicated output root.

## C. Explicit adversary model

### C.1 Name and definition

V2's only confirmation-eligible adversary model is:

```text
harness_adversary_model = non_adaptive_pre_cutoff
```

It means:

1. the exact harness/evaluator revision is frozen in the canonical benchmark repository;
2. that revision is equal to or an ancestor of a code-owned benchmark cutoff commit;
3. the cutoff binding was committed in BenchAudit before this V2 adjudicator protocol and before target execution outcomes were inspected for V2; and
4. therefore the frozen harness cannot have been authored or revised in response to this V2 adjudication mechanism or its target outcomes.

This model excludes targeted adaptation to V2. It does not prove the harness is bug-free, benevolent, or incapable of arbitrary historical behavior. The trusted supervisor and contract remain necessary.

### C.2 Mechanical derivation

No caller-supplied `harness_adversary_model` string has authority. A future verifier must derive the model from a signed, code-owned provenance bundle containing:

- `benchmark_canonical_remote` from a nonextensible allowlist;
- `harness_revision_commit`;
- `benchmark_cutoff_commit`;
- source path/blob identities for the harness/evaluator artifacts;
- fresh verification that `harness_revision_commit` is equal to or an ancestor of `benchmark_cutoff_commit` in the pinned canonical remote;
- a code-owned cutoff-binding receipt and its SHA-256;
- `cutoff_binding_benchaudit_commit`, which must be an ancestor of the V2 protocol commit in the BenchAudit repository; and
- verification policy version and verifier identity.

Use Git object-graph ancestry, never commit dates. Verification must inherit the external-evidence protections: fresh objects from the pinned remote, no trust in local `remote -v`, no shallow history, alternates, replacement refs, grafts, caller-extended manifest, or generic-host fallback.

The pure policy layer recomputes the allowed model from verified fields. Promotion consumes only the derived policy decision and independently matches every binding to the live finding. It ignores a producer's direct model label.

### C.3 Required confirmed-record fields

A confirmation-eligible record must expose, at minimum:

```json
{
  "harness_adversary_model": "non_adaptive_pre_cutoff",
  "benchmark_canonical_remote": "<pinned canonical URL>",
  "harness_revision_commit": "<40-hex>",
  "benchmark_cutoff_commit": "<40-hex>",
  "harness_revision_is_ancestor_or_equal": true,
  "cutoff_binding_receipt_sha256": "<64-hex>",
  "cutoff_binding_benchaudit_commit": "<40-hex>",
  "ancestry_verification_attestation_sha256": "<64-hex>"
}
```

These fields are disclosure, not authority. Authority comes from successful re-derivation, signature verification, manifest/key allowlists, and live binding checks.

### C.4 Out-of-scope adversaries

The following are not covered and remain review-only:

- harness/evaluator revisions after the code-owned cutoff;
- benchmarks published or revised after the adjudicator method became available without a pre-cutoff frozen revision;
- benchmark authors actively attempting to forge this supervisor's observations or satisfy its tests while hiding a defect;
- unverifiable forks or mirrors;
- caller-controlled harness patches;
- runtime/compiler/container components not pinned in the trusted computing base; and
- any finding whose ancestry or cutoff receipt cannot be verified.

### C.5 Downgrade rule

If the non-adaptive relation is absent, unknown, malformed, or unverifiable, the maximum tier is `review`. It is not confirmed and is not silently discarded. Operational inability to run the provenance verifier is recorded separately; it does not grant or strengthen the model.

## D. Isolated adjudication contract for OS-visible data

### D.1 Allowed input

The adjudicator receives only:

- raw byte-stream descriptors/content hashes from the trusted supervisor;
- exit/signal/completeness/overflow status in closed enums;
- registered contract ID/version and canonical parameter digest;
- code-owned manifest ID and payload SHA-256;
- benchmark/item/run bindings and immutable code/input hashes;
- trusted capture supervisor build/image identity;
- verified non-adaptive provenance decision; and
- nonce/session identifiers.

It does not receive benchmark prose, harness modules, candidate instructions, Python objects, pickle, executable serialization, inline comparison code, LLM output, or network references.

### D.2 Contract authority

Comparison contracts come from a code-owned manifest allowlist and a closed adjudicator registry. For APPS, the manifest binds a versioned byte comparator that may perform frozen whitespace, line, token, and numeric normalization while retaining the raw hashes.

The caller cannot provide comparator code or expand tolerances. A contract or parameter not exactly present in the pinned manifest causes abstention.

### D.3 Isolation and attestation

The supervisor/adjudicator private key is unavailable to parent, harness, candidate, container, and report code. The signed payload binds:

- raw stream/file hashes and lengths;
- completeness/overflow/timeout status;
- stdin/input hash;
- exit status and execution-group identity;
- container engine/image/policy identity;
- manifest and comparison-contract identities;
- harness/candidate/reference/driver hashes;
- item, dataset revision, source row, nonce, and session;
- derived adversary model and its provenance-attestation hash; and
- complete transcript hash.

The caller cannot ask the adjudicator to sign arbitrary precomputed bytes. The supervisor signs only observations captured from an execution it launched and controlled.

### D.4 Fail-closed conditions

Crash, timeout, truncation, overflow, noncanonical manifest, unknown comparator, decode/parse failure, missing EOF, descendant escape, runtime mismatch, signature failure, provenance uncertainty, or control failure yields abstention/review. None is a semantic rejection.

## E. Positive-satisfiability freeze

### E.1 Pre-existing source and protocol objects

The following objects existed before V2 and are frozen without rerunning APPS:

| Object | Frozen value |
|---|---|
| Benchmark repository | `codeparrot/apps` (`https://huggingface.co/datasets/codeparrot/apps`) |
| Dataset/harness revision | `21e74ddf8de1a21436da12e3e653065c5213e9d1` |
| Dataset `test.jsonl` blob | `ce62a3228ba3463b6fffcb7079d586e1a4c75f8d` |
| Dataset bytes / SHA-256 | `1,292,436,853` / `5b003a65ac40feb47dd5eaec267a767a6fc435bdcfa68ff715fe869f948e760c` |
| Frozen harness file | `apps.py`, SHA-256 `e2483d6878a8c44c76721e77cc3f978320e135af152a7f83be4f3e713df1bf37` |
| Input receipt | `docs/experiments/apps_stdin_input_receipt_20260729.json`, SHA-256 `9d4096cf343620a2a9c6f2e9fb241ed4ef50db2e7a59417e82dc319085a028e6` |
| Original protocol | `docs/experiments/APPS_STDIN_DIFFERENTIAL_ORACLE_PROTOCOL_20260729.md`, SHA-256 `e4133731430e157e7f9c5dcda7a45bc047f96e23b781971dc9e6b3a3b8a97077` |
| Completed-pair view | `docs/experiments/apps_stdin_differential_pairs_20260729.jsonl`, SHA-256 `7b2190b71b02ccf5a26fea93857edc4fadc01253be16120ca9352a84297d5420` |
| Detailed observations | `docs/experiments/apps_stdin_differential_confirmation_detail.json`, SHA-256 `646f6774a5a25d118c99a5f3f82b9dea64704a29689dfa31ab62f4ae03f4080b` |
| Summary | `docs/experiments/apps_stdin_differential_confirmation_summary.json`, SHA-256 `3a8529641ee344e3fa6537dea826c8b3d7a75195728f368ed7dc56649372c734` |
| Container image | `sha256:9e30f4122a069ab7f626cdd70a3c11ddbbf44a9bd0cc4cc834136a2a2f08e995` |
| Execution driver | SHA-256 `b48cd74eba936838fa6a824cffa98fa34c44b544acfb1d080fd9168456774edc` |

The input receipt was committed at `d3a5233aaefd81cf1bcf89b22f572021f2698384`, before the APPS execution-result commits and before V2. It explicitly records `task_outcomes_inspected_before_receipt: false`.

### E.2 Frozen positive witness

V2 freezes one primary APPS positive opportunity and two redundant same-item opportunities:

| Item | Candidate | Candidate source SHA-256 | Pre-existing relation |
|---|---|---|---|
| `apps/1402` | `arithmetic_operator:0` | `90b0c710dc50f3bd7c567e6703a799f9f45b1a8c3e6c6104dc4c8c6d8c538a93` | canonical passes weak+strong; candidate completes, weak passes, strong rejects with `output_mismatch` |
| `apps/1402` | `boolean_operator:0` | `8f9fbc74d539f6cdb5e8caac47fe6e9866f291c4de03317eef5a69e11f655321` | same direction |
| `apps/1402` | `condition_negation:0` | `96cf26899beb8e77cefeb6c6fe74e6809a36b4d82de78cb27edd1edb7ee92255` | same direction |

The historical transcript hash recorded for these findings is `5c26c1f7b464c429106050b76adbed9d5a983c0fbfa9df0490515202a36c571f`.

The historical “confirmed” label is not accepted as a V2 attestation. These rows prove only that exact candidate identities and an OS-visible weak/strong relation were recorded before V2. A future V2 run must recapture complete raw bytes and satisfy all new trust checks.

### E.3 Non-adaptive cutoff binding frozen for implementation

For the APPS positive, V2 freezes:

```text
benchmark_canonical_remote = https://huggingface.co/datasets/codeparrot/apps
harness_revision_commit    = 21e74ddf8de1a21436da12e3e653065c5213e9d1
benchmark_cutoff_commit     = 21e74ddf8de1a21436da12e3e653065c5213e9d1
cutoff relation             = equal (bidirectional ancestry required)
cutoff binding receipt      = apps_stdin_input_receipt_20260729.json
cutoff receipt commit       = d3a5233aaefd81cf1bcf89b22f572021f2698384
```

Equality is an allowed `ancestor_or_equal` relation, not a fallback. The production verifier must still fetch/verify the exact revision and file contents against the canonical remote. The pre-existing receipt establishes that this target was frozen before V2; it does not substitute for production ancestry/content verification.

### E.4 Satisfiability conclusion

```text
pre-V2 frozen benchmark revision and harness bytes       = available
pre-V2 frozen item/candidate identities                  = available
pre-V2 completed stdout weak/strong opportunity          = available
OS pipe capture relation                                 = mechanically expressible
registered APPS byte comparator                          = mechanically expressible
non-adaptive cutoff bindings                             = exactly frozen
production trusted capture/attestation implementation    = not yet built
production canonical-remote verification                 = not yet executed for V2
protocol-level positive satisfiability                    = established
production confirmation                                  = not established
```

No target result was generated for V2, and no family/item was selected after a V2 run. If implementation cannot verify the exact remote/cutoff relation or reproduce complete raw-byte controls, its correct outcome is review/`NOT_IDENTIFIABLE`, not protocol relaxation.

## F. Frozen test inventory

Tests are specified here but not implemented or run in the protocol commit.

### F.1 Capture and process-boundary tests

1. Complete raw stdout bytes are captured and hashed without UTF-8 replacement.
2. Non-UTF-8 stdout round-trips byte-for-byte.
3. Stdout and stderr remain distinct.
4. A child emitting more than the frozen limit produces `overflow_incomplete` and cannot confirm.
5. A deliberately truncated stream produces abstention and no semantic verdict.
6. Timeout after partial stdout retains only diagnostic hashes and cannot confirm.
7. Signal/error after partial stdout cannot confirm.
8. A grandchild inheriting stdout is either included under the declared execution-group scope or causes abstention when descendants are forbidden.
9. A grandchild retaining the descriptor after the leader exits cannot keep the runner alive or create a complete observation.
10. An unexpected process outside the sandbox group cannot write to the capture pipe.
11. Unknown container engine/version or stream framing fails closed.
12. Runtime diagnostic output cannot enter semantic stdout.
13. Same raw bytes under two different exit statuses remain different typed observations.

### F.2 Contract and attestation tests retained from V1

14. Harness/candidate code is never imported into the adjudicator.
15. Inline comparator code is rejected.
16. Unknown contract ID/version/parameter hash is rejected.
17. Caller-filled `adjudicator_trust_domain` has no authority.
18. Caller-filled `verified`, `confirmation_eligible`, or adversary-model fields have no authority.
19. Missing signature, wrong key, unpinned adjudicator build, or altered signed field is rejected.
20. Transcript replay across item, candidate, test set, manifest, contract, or run is rejected.
21. Observation-byte tampering is rejected.
22. Crash, timeout, malformed payload, or unsupported serialization yields abstention.
23. LLM output remains candidate generation only.
24. Canonical-control failure prevents confirmation.
25. Identical weak/strong outcomes produce no finding.
26. Swapped direction produces no finding.
27. Corrupt/unattested evidence produces no confirmed finding.

### F.3 Adversary-model tests

28. Valid canonical-remote `revision == cutoff` derives `non_adaptive_pre_cutoff`.
29. Valid strict-ancestor revision derives the model.
30. Unverifiable ancestry limits the finding to review.
31. A fork that fabricates ancestry is rejected by the pinned-remote verifier.
32. Local `remote -v`, replacement refs, grafts, alternates, or shallow history cannot satisfy ancestry.
33. Caller self-fills `harness_adversary_model`; promotion ignores it and re-derives the model.
34. Harness revision after cutoff cannot confirm.
35. Missing cutoff-binding receipt or a receipt not ancestral to the protocol commit cannot confirm.
36. Correct commit with wrong harness blob hash cannot confirm.

### F.4 APPS positive and controls

37. `apps/1402` primary candidate reproduces complete weak-pass/strong-fail raw-byte observations and can confirm only after every V2 attestation check succeeds.
38. The two redundant item-1402 candidates follow the same gate independently; they cannot share/replay one attestation.
39. APPS canonical source passes both weak and strong sets and produces no finding.
40. A weak-pass/strong-pass completed pair produces no finding.
41. A weak-rejected pair produces no finding.
42. A timeout/error pair produces no finding.
43. Two independent executions produce the same stable signed payload hash; durations, PIDs, temporary paths, and wall-clock timestamps remain raw-only.

### F.5 Nonactivation tests

44. No CLI/report/producer imports or instantiates the V2 supervisor after the protocol commit.
45. All `DISABLED_UNATTESTED_PROOFS` entries remain unchanged.
46. No historical APPS/DS-1000 report is rewritten or retroactively reclassified.

## G. Go / no-go outcomes

### G.1 `PASS_TRUSTED_ADJUDICATOR_OS_VISIBLE`

PASS requires all of:

- trusted supervisor owns and completely captures the OS boundary;
- raw bytes are preserved without lossy decoding or truncation;
- runtime, image, execution policy, manifest, comparator, key, and adjudicator build are pinned;
- non-adaptive provenance is mechanically derived from canonical-remote ancestry and the pre-V2 cutoff binding;
- every signed field is checked against live evidence;
- all frozen tests pass from a fresh clone;
- primary APPS positive confirms under a fresh V2 attestation;
- canonical, weak-pass/strong-pass, weak-rejected, timeout/error, forged ancestry, forged transcript, and replay controls produce zero confirmed findings;
- adversarial confirmation escapes equal zero; and
- an independent reviewer accepts the implementation and receipt.

PASS is specific to the evaluated OS-visible protocol and adversary model. It does not supersede the in-memory negative conclusion.

### G.2 `FAIL_TRUSTED_ADJUDICATOR_OS_VISIBLE`

One occurrence is sufficient:

- any forged, truncated, timed-out, cross-item, wrong-contract, wrong-key, wrong-runtime, or wrong-ancestry observation confirms;
- a caller-controlled string/boolean/hash grants authority;
- a control case confirms;
- bytes are decoded/lossily normalized before raw hashing;
- the private key is accessible to parent/harness/candidate;
- a post-cutoff or unverifiable harness confirms;
- implementation changes a proof ceiling or historical result to obtain PASS.

Aggregate accuracy cannot override a safety failure.

### G.3 `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR_OS_VISIBLE`

This conclusion applies if no adversarial escape is observed but an indispensable relation cannot be established, including:

- full raw bytes cannot be captured within the frozen budget;
- runtime mediation cannot be pinned or separated;
- execution-group writers cannot be bounded;
- comparator semantics cannot be pre-registered without benchmark-specific inference;
- canonical-remote ancestry/cutoff binding cannot be verified; or
- the frozen APPS positive cannot be reproduced without changing the protocol.

An unverifiable ancestry relation yields review for the individual finding and may force this overall experimental conclusion. It is never silently promoted.

### G.4 Current status

V2 has established protocol-level positive satisfiability for APPS stdout, but has not implemented or tested the trusted supervisor. Therefore none of the three execution outcomes above has been awarded. The protocol remains frozen, pending independent review.

## H. Nonactivation boundary

This document does not authorize:

- changes to `benchcore/promotion.py` or `benchcore/evaluator_execution.py`;
- removal of any disabled proof tuple;
- implementation of the capture supervisor, signature verifier, manifest registry, or ancestry verifier;
- execution of APPS or DS-1000;
- activation of a CLI, producer, checker, or report path;
- APPS input-contract V2 or any input-domain grammar work;
- external evidence V3/Phase 2B or host-policy relaxation;
- retroactive promotion of historical APPS rows; or
- use of V1/V2 protocol prose as confirmation evidence.

Implementation requires independent review of this frozen protocol and a separate commit sequence: implementation/tests, frozen run receipt, result, and only then a separately reviewed activation decision.
