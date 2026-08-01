# BenchAudit Trusted Adjudicator Protocol V1

> Status: **frozen before implementation; pending independent review**
>
> Protocol date: 2026-08-02
>
> Current protocol conclusion: **NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR**
>
> Scope: protocol and gate specification only. This document does not activate a producer, CLI path, proof family, or promotion path.

## 0. Problem statement

BenchAudit's three execution-derived confirmation families are intentionally disabled because the current executor and benchmark harness share an untrusted interpreter, while the apparent trust marker `adjudicator_trust_domain = "separate_process_v1"` and the surrounding hashes are caller-supplied evidence rather than independently verifiable proof of an isolated adjudication.

The affected proof tuples are:

| Method | Evidence level | Defect type |
|---|---|---|
| `execution_replay` | `executed_harness` | `gold_rejected_by_evaluator` |
| `execution_differential` | `executed_differential_confirmed` | `overstrict_evaluator` |
| `execution_kill_matrix` | `executed_kill_matrix_confirmed` | `evaluator_mutation_survived` |

V1 asks whether a separate adjudicator can make those proofs independently attestable without seeing or executing benchmark-controlled code. It does not assume that process separation alone establishes such a fact.

## 1. Threat model

### 1.1 Protected claim

The protected claim is not merely that a comparison function returned a particular boolean. It is the conjunction that:

1. the named benchmark item and frozen code artifacts were executed;
2. the comparison inputs are the observations actually produced by that execution;
3. a pre-registered comparison contract was applied to those exact observations;
4. the resulting relation, verdicts, and failures were bound to one item and one run;
5. no benchmark-controlled process could forge the adjudicator's attestation; and
6. timeout, crash, serialization failure, or unsupported semantics caused abstention rather than a semantic finding.

### 1.2 Adversaries and mandatory rejection behavior

| Threat | Required rejection behavior |
|---|---|
| Harness monkeypatches a comparator such as `numpy.allclose`, equality helpers, serializers, imports, or global state | The trusted comparison must not import or call harness-controlled objects. A harness-side comparator result is untrusted input and cannot establish confirmation. |
| Harness constructs a well-shaped, favorable transcript | The parent must not accept a transcript without a valid adjudicator signature over all bound fields. A signature over caller-authored observations is still insufficient unless observation provenance is independently established. |
| Caller sets `adjudicator_trust_domain = "separate_process_v1"` | The string is informational only. Promotion must ignore it as an authorization signal. |
| Transcript is replayed across items, rows, probes, contracts, manifests, or runs | Item identity, row identity, code hashes, contract identity, manifest hash, observation hashes, session identifier, and nonce must be signed and checked against the live finding. |
| Adjudicator is fed observations that were changed after execution | Observation envelopes and their byte hashes must be signed. More importantly, an independent trusted capture path must bind the envelopes to execution. Without that path, the proof is not identifiable. |
| Adjudicator crashes, times out, is killed, returns partial output, or emits malformed output | Produce no semantic finding and no reusable attestation. Record an operational outcome only. |
| Parent or harness forges an attestation | The private signing key must be absent from both. Unknown keys, bad signatures, unpinned builds, and altered payloads fail closed. |
| Executable data is smuggled through serialization | Reject pickle, object dtype, arbitrary class tags, import references, reducers, callbacks, code objects, archives, and unknown tags before parsing their contents. |
| LLM proposes a probe or labels two values as different | Treat the LLM output only as candidate generation. It cannot select the comparison contract, authenticate observations, sign an attestation, or make a proof confirmation-eligible. |
| Official gold execution itself errors or violates its materialization contract | Abstain. A mutant/probe outcome cannot be interpreted without a valid canonical control. |
| A benchmark admits multiple valid outputs but a unique-output comparator is selected | Abstain unless a trusted manifest has pre-registered a relation that is sound for that benchmark item. |

### 1.3 Trusted computing base contemplated by V1

If V1 were satisfiable, the minimum trusted computing base would contain:

- a code-owned manifest allowlist and manifest hash validator;
- a non-benchmark-controlled typed-value parser;
- a fixed registry of comparison-contract implementations;
- an isolated adjudicator executable and pinned executable/image hash;
- a signing key available only to that adjudicator;
- promotion-side signature and binding verification; and
- a trusted observation-capture boundary.

The last component is not currently available for DS-1000 in-memory Python values. That absence determines the current V1 conclusion.

## 2. Trust-domain split and data contract

### 2.1 What the adjudicator may see

The adjudicator may receive only:

- protocol and schema versions;
- a code-owned manifest ID and manifest payload SHA-256;
- item identity and immutable source-row identity;
- a registered comparison-contract ID, version, and canonical parameter hash;
- canonical typed-value envelopes for the reference and candidate observations;
- hashes of those exact envelopes;
- execution-control facts represented as closed enums, such as `completed`, `timeout`, `crash`, or `serialization_rejected`;
- hashes of the frozen driver, reference, candidate/probe, and code context;
- a fresh parent request nonce and an adjudicator-generated session identifier; and
- size/version bounds needed to parse the envelope safely.

The adjudicator may not use a caller-supplied free-form comparator, Python expression, import path, module, callback, or natural-language instruction.

### 2.2 What the adjudicator must never see or execute

The adjudicator must not receive or execute:

- benchmark raw records, problem statements, rubrics, or hidden tests;
- harness, evaluator, reference-solution, candidate, or probe source code;
- Python pickles, marshal payloads, object arrays, reducers, bytecode, shared libraries, notebooks, shell commands, or archives;
- caller-defined serialization logic;
- LLM reasoning, LLM verdicts, or arbitrary textual comparison instructions; or
- network resources or filesystem paths supplied by the benchmark process.

The restriction is semantic, not merely a process boundary: benchmark-controlled code must not run in the adjudicator process before or during adjudication.

### 2.3 Safe typed-value serialization

A future implementation would need a versioned `benchaudit-typed-value-v1` envelope with a small closed tag set. V1 freezes the following requirements but does not implement the format:

1. The outer envelope is canonical UTF-8 JSON with sorted keys, no duplicate keys, bounded nesting, bounded total bytes, and integers represented without exponent or leading-zero variants.
2. Supported scalar tags are limited to null, boolean, bounded integer, finite IEEE-754 float, normalized text, and byte strings represented by length plus SHA-256 and canonical base64.
3. Supported array tags must state rank, shape, numeric dtype, endianness, byte length, and a content digest. Object dtype and structured objects are forbidden.
4. Timestamp-like values must state unit and timezone metadata explicitly. Naive and timezone-aware values are never silently coerced.
5. NaN, signed zero, infinity, string normalization, row ordering, and missing values have contract-specific, pre-registered handling. The serializer must not invent equivalence.
6. Unknown tags, unsupported dtypes, oversize values, inconsistent lengths, duplicate fields, or non-canonical encodings cause abstention.
7. Pickle and any format with executable deserialization semantics are prohibited.

### 2.4 Required observation transfer property

The comparison envelopes must be produced or captured inside a trust boundary that the benchmark-controlled process cannot forge. A pipe from an untrusted child is not sufficient: a process can emit arbitrary bytes. A separate process that merely signs those bytes proves only that it compared the supplied payload.

For OS-visible protocols, a future trusted supervisor might capture stdout, exit status, or file artifacts directly. For DS-1000, the relevant Python values exist only inside the interpreter running the untrusted harness. The current architecture has no independent channel that proves a serialized envelope is the actual in-memory `result` rather than attacker-chosen bytes.

## 3. Semantic circularity and comparison-contract authority

### 3.1 The circular dependency

Determining whether two outputs are equivalent requires task semantics. Task semantics live in benchmark-controlled data and harness logic. Allowing the adjudicator to infer semantics from those materials would expand the trusted computing base to the object under audit. Preventing it from seeing those materials leaves it unable to choose a sound relation ad hoc.

Therefore V1 permits no adjudicator-side semantic inference.

### 3.2 Only admissible semantic authority: trusted manifest plus registered contract

The only admissible V1 route is a code-owned, hash-pinned adjudication manifest. It must:

- be named in a code-owned allowlist that callers cannot extend;
- have a canonical payload SHA-256 verified before use;
- bind benchmark revision, item ID, immutable row ID, protocol family, and comparison-contract ID;
- contain canonical contract parameters rather than executable comparison code;
- state whether the task is unique-output, relation-based, or not identifiable under registered contracts;
- be frozen before candidate/probe outcomes are inspected; and
- select only a contract implemented in the adjudicator's closed registry.

Illustrative registered contracts include:

- exact typed equality;
- shape- and dtype-strict numeric approximate equality with frozen tolerances;
- timezone-aware timestamp equality with no naive/aware coercion;
- unordered row-set equality under a frozen scalar normalization; and
- an explicitly registered relation checker for a benchmark family, provided the relation itself is trusted and non-executable.

A manifest cannot be generated from the same LLM or harness output being adjudicated and then treated as a trust root.

### 3.3 Why a trusted manifest is necessary but not sufficient

The manifest breaks the semantic-selection circularity: it decides the relation before the candidate outcome is seen. It does not solve observation authenticity. A correct contract applied to forged values remains a forged proof.

For DS-1000, V1 can pre-register a shape-strict or timezone-strict relation, but it cannot independently bind the operands to the actual in-memory values produced by the official harness. The relation is therefore semantically specified but observationally unauthenticated.

### 3.4 V1 conclusion

Under the current project constraints, the required trusted observation-capture boundary for DS-1000 is absent. Adding an item-specific trusted extractor, reimplementing each harness in the trusted process, accepting harness-supplied serialized values, or trusting a caller assertion would reintroduce the same circularity or create a benchmark-specific proof verifier.

Accordingly, V1 concludes:

> **NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR** — the project can specify and attest an independent comparison, but cannot currently prove that the comparison operands are the observations produced by DS-1000's benchmark-controlled in-memory execution.

This is not a claim that trusted adjudication is impossible in general. A future protocol may become identifiable for OS-visible stdout/files, a separately attested VM/TEE capture boundary, or a benchmark that natively emits signed/canonical observations. Such a protocol requires a new freeze and independent review; it is not a V1 amendment.

## 4. Attestation contract if observation provenance becomes identifiable

This section freezes requirements for a future admissible attestation. It does not authorize implementation while §3.4 holds.

### 4.1 Key custody

- Use an asymmetric signature scheme with a project-approved implementation, such as Ed25519.
- Generate the private key outside the parent, harness, candidate, and report processes.
- Make the private key accessible only to the pinned adjudicator executable or isolated runtime.
- Never mount, serialize, log, cache, or return the private key to the parent or benchmark environment.
- Pin the public key fingerprint, key ID, adjudicator build/image digest, and accepted protocol version in code-owned policy.
- Key rotation requires an explicit policy update and regression review. An unknown key fails closed.

### 4.2 Signed payload

The adjudicator must sign one canonical payload binding at least:

- attestation protocol/schema version;
- public-key ID;
- adjudicator executable/image digest;
- manifest ID and manifest payload SHA-256;
- benchmark revision, item ID, immutable row ID, and source digest;
- comparison-contract ID, version, and parameter digest;
- driver, harness-context, reference, candidate/probe, and original-answer hashes;
- input-materialization digest;
- reference and candidate typed-envelope SHA-256 values;
- execution status for canonical and candidate paths;
- official evaluator verdicts;
- adjudicator relation result and closed reason code;
- complete canonical transcript SHA-256;
- parent request nonce and adjudicator session ID; and
- explicit `confirmation_eligible` boolean derived by the adjudicator, never accepted from the caller.

Every signed field must be recomputed or matched by promotion against live evidence. Unrecognized extra authorization fields are ignored; conflicting fields reject the proof.

### 4.3 Attestation is not observation provenance

A valid signature authenticates the adjudicator's statement. It cannot transform unauthenticated operands into genuine execution observations. The signer must refuse to sign confirmation-eligible output unless its trusted runtime obtained the operands through an independently authenticated observation channel.

Signing caller-provided values is expressly prohibited for confirmation, even if their hashes match a parent transcript.

## 5. Future promotion-side verification conditions

No condition in this section is active under V1. If a later protocol resolves observation provenance, promotion must require all of the following:

1. The proof tuple is explicitly registered and is no longer in the disabled-unattested set under a separately reviewed change.
2. A supported attestation protocol and schema are present.
3. The signature verifies against a pinned public key associated with the pinned adjudicator build/image digest.
4. The key, build, manifest, and contract versions are code-owned and caller-nonextensible.
5. The signed payload digest matches canonical reserialization of all signed fields.
6. Item ID, immutable row identity, benchmark revision, source digest, and manifest binding match the live item.
7. Driver, code-context, reference, candidate/probe, and original-answer hashes match live evidence.
8. Contract ID, contract version, and parameter digest match the trusted manifest; no inline comparator is accepted.
9. Typed observation envelope hashes match the signed values, and their origin is backed by an accepted trusted capture protocol.
10. Canonical execution completed and passed the required control. Candidate execution completed. Crash, timeout, partial output, serialization rejection, or infrastructure error cannot become a semantic verdict.
11. The adjudicator's closed relation result is consistent with the proof family's required direction.
12. The nonce/session binding is fresh for the item and cannot be replayed across item, candidate, run, or contract.
13. The entire transcript hash matches the signed transcript binding.
14. `review_only`, `_originating_review_only`, and all existing proof-family safety ceilings remain independently enforced.

`adjudicator_trust_domain` may be retained as a diagnostic label but must not grant detection or confirmation authority. Likewise, a caller-supplied `verified: true` or `confirmation_eligible: true` has no authority.

If any required check is absent, false, malformed, unknown, or internally inconsistent, promotion returns review or no semantic finding according to the existing proof-family policy. It must never infer trust from a well-shaped mapping.

## 6. Frozen test inventory

These tests are frozen before any implementation. They are specifications, not current test results.

### 6.1 Threat and binding tests

1. A harness monkeypatches `numpy.allclose`; the adjudicator's registered comparator is unaffected, or the run abstains if observation provenance is unavailable.
2. A harness monkeypatches the serializer; non-canonical or unauthenticated observations cannot confirm.
3. A caller supplies a fully shaped transcript without a signature; confirmation is rejected.
4. A caller sets `adjudicator_trust_domain = "separate_process_v1"`; the result remains ineligible without independently verified attestation.
5. A caller supplies `verified: true` and a syntactically valid payload hash; the result remains ineligible.
6. A signature made by an unknown key is rejected.
7. A valid signature with one transcript field changed is rejected.
8. A valid transcript replayed for another item or immutable row ID is rejected.
9. A valid transcript replayed for another candidate/probe hash is rejected.
10. A valid transcript replayed under another contract ID, version, or parameter digest is rejected.
11. A valid transcript replayed under another manifest or benchmark revision is rejected.
12. A valid transcript with modified observation bytes is rejected.
13. A signed comparison of caller-supplied observations without trusted-origin evidence is not confirmation-eligible.
14. Pickle, object dtype, duplicate JSON keys, unknown tags, oversize payloads, inconsistent shape/length, and executable references all fail closed.
15. Adjudicator crash, timeout, signal termination, truncated output, or malformed signature produces no semantic finding.
16. Canonical execution timeout/error/failure prevents candidate confirmation.
17. Candidate timeout/error is not interpreted as semantic rejection or inequality.
18. LLM-generated probes remain candidate inputs; an LLM verdict cannot select a trusted contract or sign a proof.
19. A task permitting multiple outputs cannot use unique-output equality unless the trusted manifest registers a sound relation.
20. Repeated runs with the same frozen inputs produce identical stable attestation payloads apart from explicitly excluded operational metadata.

### 6.2 Required positive and negative controls

21. DS-1000 id 11 must reach `confirmed` only if a trusted capture proves the actual timezone-aware and timezone-naive observations and the registered timezone/type contract distinguishes them.
22. DS-1000 id 300 must reach `confirmed` only if a trusted capture proves the actual shapes/values and the registered shape-strict numeric contract distinguishes the broadcasting-accepted result.
23. DS-1000 id 308 must not reach `confirmed`; the task permits multiple valid outputs and its property-based checker does not establish unique expected value equality.
24. A clean control satisfying the registered relation produces no defect finding, demonstrating that the mechanism does not pass merely by rejecting everything.

### 6.3 Nonactivation tests

25. No CLI, report, producer, or main checker instantiates the adjudicator after the protocol-only commit.
26. All three execution proof tuples remain disabled and existing review ceilings remain unchanged.

## 7. Go / no-go outcomes

### 7.1 PASS

`PASS_TRUSTED_ADJUDICATOR` requires every condition below:

- the trusted observation-capture mechanism is specified and implemented without benchmark/item-specific proof logic;
- the trusted manifest and contract registry are code-owned, hash-pinned, and nonextensible by callers;
- key separation and signature verification are independently demonstrated;
- every frozen threat test passes with zero adversarial confirmation escapes;
- ids 11 and 300 confirm through independently authenticated observations;
- id 308 and the clean control do not produce false confirmation;
- crash/timeout/unsupported serialization produce abstention;
- fresh-clone tests reproduce deterministically;
- no production path is activated by the protocol/evaluator implementation commit; and
- independent review accepts the trust split and its positive satisfiability evidence.

### 7.2 FAIL

`FAIL_TRUSTED_ADJUDICATOR` is mandatory if any of the following occurs:

- any adversarial test obtains confirmation;
- caller-controlled strings, booleans, manifests, keys, contracts, or observations can grant authority;
- id 308 confirms under the proposed contract;
- an operational failure is converted into a semantic result;
- executable serialization reaches the trusted process;
- key material is reachable from the parent or harness; or
- the implementation weakens an existing review/confirmation ceiling to obtain a positive result.

One adversarial escape is sufficient; aggregate accuracy cannot override it.

### 7.3 NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR

This conclusion is required if the comparison relation can be specified but any indispensable fact cannot be independently established, including:

- actual in-memory observations cannot be authenticated independently of the untrusted harness;
- no trusted manifest can soundly choose an output relation for the target item;
- key/build isolation cannot be established in the available execution environment; or
- the required positive controls cannot satisfy the frozen trust relation without item-specific trusted code.

**Current V1 outcome:** `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR`, because DS-1000's relevant result values are constructed and compared inside the shared, benchmark-controlled Python interpreter, and no trusted observer can distinguish the actual value from arbitrary bytes emitted by that interpreter.

This outcome prohibits implementation under V1. It must not be renamed to PASS, treated as an infrastructure-only success, or used to remove any disabled proof tuple.

## 8. Nonactivation boundary

This protocol does not authorize:

- implementation of an adjudicator, serializer, signature verifier, or manifest registry;
- modification of `benchcore/promotion.py` or `benchcore/evaluator_execution.py`;
- removal of any `DISABLED_UNATTESTED_PROOFS` entry;
- construction of a producer or addition of a CLI/report path;
- retroactive promotion of existing DS-1000 findings;
- use of LLM output as confirmation evidence; or
- replacement of a trusted observation channel with a caller assertion.

No code or test is included in this commit. Any future work requires an independently reviewed V2 protocol that resolves the observation-origin issue and repeats positive-satisfiability freezing before implementation.

## 9. Positive-satisfiability freeze

### 9.1 Frozen candidate objects

These objects existed before this protocol and were not produced for it:

| Role | Frozen object | SHA-256 / binding | Pre-existing observation |
|---|---|---|---|
| Required positive candidate | `/home/zhoujun/llmdata/after623/reports/ds1000_exec_pilot200/11.json` | file SHA-256 `9473dbeee8812ec5eee9a8c5b048d303ed2b26787591f0c802db2f3c8d670818`; run signature `0beab5938cb1bd36784bd3f25d8af4f7e0ffa79243d81d0f561d675364944e55` | candidate for a timezone-aware versus timezone-naive comparison blind |
| Required positive candidate | `/home/zhoujun/llmdata/after623/reports/ds1000_exec/300.json` | file SHA-256 `083016c887d81aff3c6965ffb88d29609837b8cf95ae1e3feb6eeb589aaad75d` | candidate for an `assert_allclose` broadcasting/shape blind |
| Required negative control | `/home/zhoujun/llmdata/after623/reports/ds1000_exec_pilot200/308.json` | file SHA-256 `d6b88881a9ad3bfabcb95d12a550662307c5bc326cc91bc47878cf769dcdbe58`; same pilot run signature | property-based checker ignores `ans`, but the task admits multiple valid outputs; must not confirm |

These are historical untrusted execution reports. Their hashes freeze the candidate claims and prevent later case substitution. They do not authenticate the reported in-memory operands and therefore are not positive proof receipts.

### 9.2 Exact relationships required for a satisfiable positive

For id 11, a future positive would require all of:

1. a frozen manifest selecting a timezone/type-sensitive registered relation before observing the mutant outcome;
2. trusted capture of the official and mutant result objects, including timezone metadata and type/shape information;
3. a valid canonical control;
4. official harness acceptance of the mutant under the frozen run; and
5. an adjudicator-signed inequality under the registered contract, bound to item 11 and the exact code hashes.

For id 300, a future positive would require all of:

1. a frozen manifest selecting shape-strict numeric approximate equality before observing the mutant outcome;
2. trusted capture of both actual numeric arrays, including rank, shape, dtype, and values;
3. a valid canonical control;
4. official evaluator acceptance attributable to broadcasting; and
5. an adjudicator-signed inequality under the shape-strict contract, bound to item 300 and the exact code hashes.

For id 308, the manifest must not register unique-output equality merely because one reference value is present. Unless a sound relation for all permitted outputs is pre-registered, adjudication must abstain and confirmation must remain unreachable.

### 9.3 Satisfiability check performed before implementation

The candidate behavior and desired relations were known before implementation from the frozen historical reports and prior review. However, the indispensable relation

> `typed envelope == actual in-memory value produced by the official DS-1000 harness execution`

is not mechanically verifiable in the current architecture. The same untrusted interpreter controls the value, comparator context, and any serializer that could emit it. Process separation after serialization does not repair that provenance gap.

Therefore:

```text
candidate cases available                         = true
registered comparison semantics conceivable       = true
trusted observation channel available             = false
positive trust relation satisfiable under V1      = false
implementation authorized                         = false
protocol outcome                                  = NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR
```

This check is frozen before implementation. It cannot be repaired by accepting self-reported observations, adding item-specific trusted extractors for ids 11/300, or weakening confirmation. A materially different trusted observation mechanism requires a new protocol version and a new pre-implementation satisfiability receipt.
