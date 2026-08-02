# BenchAudit Trusted Adjudicator Protocol V4

> Status: **frozen**
>
> Freeze date: 2026-08-02
>
> Scope: disclosure and machine-readable containment of the Phase 2A
> symmetric-attestation deviation. This protocol does **not** activate the
> trusted adjudicator and does not authorize a production manifest, producer,
> checker, CLI, report, promotion, or evaluator integration.

## 0. Decision and narrow scope

V4 supersedes exactly one requirement of the inherited protocol chain:

- V1 §4.1 required an asymmetric project-approved signature scheme such as
  Ed25519. V4 permits HMAC-SHA256 for the non-activated Phase 2A implementation
  as an **internal symmetric integrity mechanism**.

Every other V1, V2, and V3 requirement remains in force unless an earlier
protocol already superseded it. In particular, V4 does not relax raw-capture
completeness, provenance, runtime identity, nonce separation, comparison,
fail-closed behavior, review ceilings, production activation, or replay
requirements.

This is a protocol correction for an implementation deviation. It is not a
claim that the adjudicator has passed its production or OS-visible gate.

## 1. Immutable parent protocols

The parent documents are immutable inputs to V4:

| Protocol | SHA-256 |
|---|---|
| `docs/TRUSTED_ADJUDICATOR_PROTOCOL_V1_20260802.md` | `9cbe5b1badf62540bd113b8822a1a584d8bcd3d9995a602fb14c7b7ad020cb0f` |
| `docs/TRUSTED_ADJUDICATOR_PROTOCOL_V2_20260802.md` | `57092a96c6b47d0ff23a9be4dad3f7829aade5a39e7f5f8e002deae4a570cd7e` |
| `docs/TRUSTED_ADJUDICATOR_PROTOCOL_V3_20260802.md` | `70ea07afeae0ec34673441eba882c5a2e0b94fa31ef2d825317eeacb51048e92` |

Implementations and receipts must verify these hashes before claiming V4
conformance. V1, V2, and V3 must not be edited to make the implementation look
retrospectively conformant.

## 2. Superseded signature requirement

### 2.1 Actual choice

The Phase 2A implementation may use:

```text
signature_scheme = hmac-sha256-internal-integrity-v1
attestation_class = internal_integrity_symmetric
verification_implies_forgery_capability = true
```

This supersedes V1 §4.1 only with respect to its asymmetric/Ed25519 signature
scheme requirement. It does not supersede transcript binding, key non-disclosure
to harness/candidate/container/benchmark-controlled code, nonce binding, or
fail-closed verification.

### 2.2 Reason

Python's standard library does not provide Ed25519. Introducing an additional
cryptographic dependency solely for the non-activated Phase 2A core would
conflict with the project's dependency discipline. V3 §2.3 already assigns
third-party confidence to deterministic replay of frozen inputs and code, not
to the attestation signature itself.

The accepted engineering purpose of HMAC here is therefore narrow: detect
accidental or unauthorized transcript mutation inside the trusted local
pipeline. It is not public-key attestation.

### 2.3 Exact security loss

The loss relative to an asymmetric signature is explicit and permanent for
this attestation class:

1. Verification capability implies forgery capability because the same secret
   material is sufficient to verify and to sign.
2. The parent process cannot be structurally excluded from forgery capability.
   Separation depends on trusted-computing-base discipline, not cryptographic
   key separation.
3. An `internal_integrity_symmetric` attestation can never be external proof,
   even when its signature verifies and every other observation is complete.
4. Sharing a verification key with an external reviewer would also share
   signing capability; it cannot create third-party verifiability.

No report may shorten these losses to merely "HMAC is internal." The exact
forgery implication must remain machine-readable with the attestation.

## 3. V3 §5.2 clarification

V3 §5.2's generic-signing failure condition is superseded only as follows:

> The adjudicator fails when harness-controlled, candidate-controlled,
> container-controlled, or benchmark-controlled code can cause an arbitrary
> parent-supplied byte string to be signed as supervisor-captured evidence.

The parent remains inside the V3 trusted computing base. Under the symmetric
scheme, parent access to signing capability is an explicit limitation governed
by §2.3, not a claim of structural exclusion. This clarification must not be
read as allowing untrusted execution code to select signed bytes or bypass the
supervisor's raw capture.

## 4. Machine-readable attestation contract

Every V4-conformant Phase 2A attestation must bind and expose:

```json
{
  "attestation_class": "internal_integrity_symmetric",
  "verification_implies_forgery_capability": true
}
```

Both fields are signed attestation metadata. Verification must fail closed when
either field is missing, changed, or inconsistent with the code-owned signature
scheme.

### 4.1 External-proof consumer rule

A consumer may treat an attestation as external proof only when all of the
following are true:

1. `attestation_class == "third_party_verifiable"`;
2. `verification_implies_forgery_capability == false`;
3. a separately frozen protocol authorizes that class and verifier;
4. all inherited proof and provenance checks pass.

The current V4 implementation satisfies neither item 1 nor item 2. A valid HMAC
must therefore return false from any external-proof eligibility predicate.
Changing only the class string while retaining the forgery flag must also
return false.

## 5. Key identifier contract

The key identifier must not be the bare SHA-256 of secret key material. Phase
2A uses the code-owned domain separator:

```text
SHA256("benchaudit-adjudicator-keyid-v1" || key_bytes)
```

This domain separation removes the bare-key hash oracle from the attestation.
It does not make the identifier opaque and does not change the symmetric trust
model. Tests must prove that the emitted identifier differs from
`SHA256(key_bytes)` for the same fixture key.

## 6. Incomplete-capture reason contract

The stable raw observation must carry an explicit `incomplete_reason` whenever
capture is incomplete. At minimum:

- `timeout`: the process leader has not exited when the deadline is reached;
- `descendant_retained_pipe`: the process leader has exited but stdout or
  stderr has not reached EOF at the deadline because a descendant may retain
  an inherited pipe;
- `stdout_overflow` or `stderr_overflow`: the corresponding byte limit was
  exceeded.

`descendant_retained_pipe` and ordinary `timeout` are distinct evidence. Both
remain incomplete, confirmation-ineligible observations. Recording a more
specific reason must never relax the review ceiling.

## 7. Protocol-deviation disclosure rule

Every implementation receipt governed by a frozen protocol must contain a
top-level `protocol_deviations` list. Each entry must contain:

1. the deviated protocol and exact clause;
2. the protocol-required choice;
3. the actual implementation choice;
4. the reason for the different choice;
5. the exact capability or assurance lost;
6. whether a newer frozen protocol has re-frozen the choice;
7. when re-frozen, the new protocol path and SHA-256.

`known_unimplemented_or_unverified_boundaries` is reserved for work not yet
implemented or verified. It must not carry an implemented-but-different
protocol choice. Mixing those concepts hides deviations and is non-conformant.

If an existing receipt is immutable, the deviation must be recorded in a new
hash-bound addendum that includes the original receipt path and SHA-256. The
addendum must not rewrite the historical receipt, decision, test counts, or
experimental outputs.

## 8. Required tests before V4 delivery

At minimum, tests must establish:

1. V1/V2/V3 hashes remain exactly those in §1;
2. emitted attestations carry both V4 limitation fields;
3. either limitation field being tampered causes verification failure;
4. an internal symmetric attestation is ineligible as external proof;
5. a forged `third_party_verifiable` class with the symmetric forgery flag is
   still ineligible as external proof;
6. `key_id != SHA256(key_bytes)` for the fixture key;
7. an ordinary leader timeout records `timeout`;
8. a leader-exited descendant-retained-pipe case records
   `descendant_retained_pipe`;
9. both cases remain capture-incomplete and confirmation-ineligible;
10. production manifest registration and CLI/checker/producer/report/promotion
    integration remain absent.

## 9. Delivery status and prohibition

The only permitted delivery state for this phase is:

```text
IMPLEMENTED_NOT_ACTIVATED
```

The following claims remain prohibited:

- `PASS_TRUSTED_ADJUDICATOR_OS_VISIBLE`;
- third-party-verifiable or external-proof attestation;
- production readiness;
- confirmation of the two APPS positives;
- activation of a production manifest or promotion proof path.

Production Git provenance verification, a digest-pinned container manifest,
and independent review remain future gates. V4 does not authorize work on
those gates in this phase.
