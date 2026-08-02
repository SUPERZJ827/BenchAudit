# Trusted Adjudicator Protocol V3: Key-Custody Semantics and Positive-Witness Diversity

Status: **frozen before implementation; pending independent review**  
Date: 2026-08-02  
Scope: protocol amendment only; no implementation or proof activation is authorized

## 0. Decision and amendment boundary

V3 does not replace or rewrite V1 or V2. It amends only three V2 claims:

1. which components must be unable to access the supervisor signing key;
2. which repository history actually warrants `non_adaptive_pre_cutoff` for the equal-commit APPS positive; and
3. the concentration of the frozen positive opportunity on one APPS item.

All V2 capture, truncation, runtime, comparator, provenance, downgrade, nonactivation, and disabled-proof requirements remain in force unless this document explicitly amends them.

V3 remains a protocol. It does not implement a supervisor, activate a producer, alter promotion, or change a historical finding.

## 1. Immutable parent protocols

| Parent | Path | Immutable SHA-256 |
|---|---|---|
| V1 | `docs/TRUSTED_ADJUDICATOR_PROTOCOL_V1_20260802.md` | `9cbe5b1badf62540bd113b8822a1a584d8bcd3d9995a602fb14c7b7ad020cb0f` |
| V2 | `docs/TRUSTED_ADJUDICATOR_PROTOCOL_V2_20260802.md` | `57092a96c6b47d0ff23a9be4dad3f7829aade5a39e7f5f8e002deae4a570cd7e` |

V1 retains the narrowed in-memory conclusion recorded by V2:

```text
NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR_IN_MEMORY
```

V2 remains the parent protocol for OS-visible observations. V3 does not expand its evaluated observation classes.

## 2. Amendment R1: feasible key custody and signature semantics

### 2.1 Correct protected boundary

V2 D.3 is superseded only where it says that the signing key must be unavailable to the ordinary BenchAudit parent and report code.

The V3 key-custody requirement is:

```text
signing_key_unavailable_to = {
  harness,
  candidate,
  container,
  benchmark-controlled code
}
```

The harness, candidate, container, and all benchmark-controlled code must be unable to read, derive, mount, inherit, request use of, or cause disclosure of the signing key. They must also be unable to submit precomputed observations for signing.

The trusted supervisor signs only a transcript captured from an execution that it launched and controlled under the frozen manifest.

### 2.2 Trusted computing base

The following components are explicitly in the trusted computing base (TCB):

- the trusted supervisor/adjudicator build;
- the ordinary BenchAudit parent that launches or communicates with the supervisor;
- the report process that verifies and serializes the signed result;
- the code-owned manifest and closed comparator registry;
- the pinned container engine/runtime and host kernel boundary used by the frozen implementation; and
- the provenance verifier used to derive `non_adaptive_pre_cutoff`.

Parent and report processes may run under the same host UID as the supervisor. V3 therefore does not claim that the key is inaccessible to them. A same-UID parent may be able to inspect supervisor memory or key material through host facilities unless stronger operating-system isolation is separately implemented and tested.

This is not a hidden limitation: compromise or unauthorized modification of any TCB component invalidates the attestation and prevents confirmation.

### 2.3 Signature semantics

The supervisor signature is an **internal integrity boundary**, not third-party attestation.

BenchAudit controls the signing key. The signature therefore does not, by itself, prove to an external party that an observation is true. It only lets the trusted BenchAudit components distinguish a supervisor-captured transcript from an unsigned or harness-supplied assertion and detect post-capture modification or cross-run replay.

Third-party confidence must come from deterministic replay:

1. obtain the frozen source, manifest, comparator, harness, candidate, and container identities;
2. run the same execution in the pinned environment;
3. independently capture the same OS-visible byte relation; and
4. re-evaluate the closed proof contract locally.

The signature is neither a substitute for replay nor authority to turn caller-supplied bytes into confirmed evidence.

### 2.4 Attested payload and signing restrictions

The V2 D.3 signed fields remain required. In addition, the signed payload must bind:

- supervisor/adjudicator build identity;
- key identifier and signature-scheme version, but never key material;
- parent/report implementation identities included in the TCB receipt;
- proof that the observation originated from a supervisor-launched execution session; and
- a nonce preventing a signed transcript from being accepted for another session.

The signing interface must not expose a generic `sign(bytes)` operation to the parent, report code, harness, candidate, container, or benchmark-controlled code. A TCB component capable of misusing host access is handled as TCB compromise, not claimed to be cryptographically impossible.

### 2.5 R1 test amendments

The V2 test inventory is amended as follows:

1. signing-key access by harness, candidate, container, or benchmark-controlled code is a safety failure;
2. the harness cannot request a signature over prebuilt observations;
3. an unsigned, wrong-key, altered, cross-item, or cross-session transcript is rejected;
4. a parent-produced signature alone does not establish confirmation without a supervisor-owned execution transcript and complete replay bindings;
5. parent/report membership in the TCB is disclosed in the receipt;
6. changing the parent or report implementation identity invalidates an existing attestation unless the frozen manifest permits that exact build;
7. deterministic third-party replay does not require possession of BenchAudit's private signing key; and
8. no test claims that same-UID parent inaccessibility has been established unless a future protocol separately freezes and verifies an OS isolation mechanism.

## 3. Amendment R2: equal-commit ancestry and the actual non-adaptive warrant

### 3.1 Equal-commit relation is tautological ancestry

V2 freezes:

```text
harness_revision_commit = 21e74ddf8de1a21436da12e3e653065c5213e9d1
benchmark_cutoff_commit  = 21e74ddf8de1a21436da12e3e653065c5213e9d1
relation                 = equal
```

For this positive, `harness_revision_commit` is necessarily both an ancestor of and a descendant of `benchmark_cutoff_commit`, because they are the same Git object. The benchmark-repository ancestry check therefore does not, for this equal-commit case, prove that the harness predates the adjudication method.

It still performs two useful checks:

- the exact revision comes from the pinned canonical remote rather than a caller-controlled fork; and
- the harness/content hashes are bound to that exact frozen revision.

Those checks establish canonical revision and content identity. They do not independently establish non-adaptivity.

### 3.2 Actual warrant for the frozen APPS positive

For the equal-commit APPS positive, the non-adaptive warrant comes from the BenchAudit repository history:

```text
cutoff_binding_receipt = docs/experiments/apps_stdin_input_receipt_20260729.json
cutoff_binding_benchaudit_commit = d3a5233aaefd81cf1bcf89b22f572021f2698384
```

The future production verifier must establish in the canonical BenchAudit repository that `d3a5233aaefd81cf1bcf89b22f572021f2698384` is an ancestor of this V3 protocol commit and of the implementation protocol/manifest commit used by a run.

The receipt records `task_outcomes_inspected_before_receipt: false`. Together, the receipt and repository ordering establish the precise claim:

> The APPS harness revision and target identities were frozen in BenchAudit before this trusted-adjudicator adaptation and before its target outcomes were inspected for this adaptation; therefore the harness could not have been authored or revised to target this adaptation mechanism or its selected result.

This warrant does **not** claim that:

- the harness predates all BenchAudit work;
- the harness is nonmalicious for every possible future audit method;
- the benchmark-repository equal-commit ancestry itself proves temporal precedence; or
- a post-cutoff harness revision is covered.

### 3.3 Future strict-ancestor positives

If a future frozen positive uses `harness_revision_commit != benchmark_cutoff_commit` and proves that the harness revision is a strict ancestor of the cutoff in the canonical benchmark remote, benchmark-repository ancestry begins to carry substantive non-adaptive evidence.

Such a future protocol must restate the warrant and test the strict-ancestor path. It may not silently reuse the equal-commit explanation.

### 3.4 R2 test amendments

1. Equal commits with canonical content may satisfy revision identity, but the decision must record that benchmark-side ancestry is tautological for that positive.
2. Equal commits without a valid pre-V3 BenchAudit cutoff-binding receipt cannot derive `non_adaptive_pre_cutoff`.
3. A cutoff-binding receipt commit that is not ancestral to the V3 protocol/implementation commit cannot confirm.
4. Caller-filled timestamps or adversary labels provide no authority.
5. Strict-ancestor and equal-commit receipts remain distinguishable in the derived decision and disclosure record.

## 4. Amendment R3: independent positive item from frozen records

### 4.1 Frozen source record

V3 performs no APPS execution and reads no new benchmark data. It uses the pre-existing object:

| Object | Frozen value |
|---|---|
| Source branch | `research/apps-official-survivor-confirmation-20260729` |
| Detailed observations | `docs/experiments/apps_stdin_differential_confirmation_detail.json` |
| Detailed observations SHA-256 | `646f6774a5a25d118c99a5f3f82b9dea64704a29689dfa31ab62f4ae03f4080b` |
| Existing record count | 30 tasks |
| Existing weak-pass/strong-fail findings | 7 candidates across 4 tasks |

The source summary already identifies affected tasks `1402`, `1785`, `1849`, and `4352`. These records predate V2 and V3.

### 4.2 Additional independent-item positive opportunity

V3 adds one independent-item opportunity to the three V2 same-item opportunities:

| Item | Candidate | Candidate source SHA-256 | Transcript SHA-256 | Pre-existing relation |
|---|---|---|---|---|
| `apps/4352` | `numeric_constant:0` | `9151bcf04668e8c58c73a1cd410b38f09543a1dd987e4bf5ad2b65c889d5670c` | `ca591e3be47431f080f57eb4c8cf7ed078d7877f2d99840c9bd7fafb2d73d8ae` | canonical passes weak+strong; candidate completes, weak passes, strong rejects with `output_mismatch` |

This opportunity is independent of `apps/1402` at the item level and uses a mutation family that does not produce a V2 positive on item 1402.

The historical `confirmed` tier is not accepted as V3 attestation. The record proves only that the exact candidate identity and direction existed before V3. A future implementation must recapture complete raw bytes and satisfy every V2/V3 trust check.

### 4.3 Selection disclosure

The additional item was selected after V2 review from frozen records whose outcomes were already known. It is not a blind holdout, an unbiased yield estimate, or evidence of cross-item generalization by itself.

Its role is narrower: prevent the implementation's positive path and integration test from depending exclusively on item 1402.

```text
positive_witness_concentrated_on_single_item = false
frozen_positive_item_count = 2
frozen_positive_items = [apps/1402, apps/4352]
```

### 4.4 R3 test amendments

1. Item 1402 and item 4352 must receive separate supervisor executions, nonces, transcripts, and signatures.
2. No attestation, raw observation, or comparison result may be reused across the two items.
3. Item 4352 `numeric_constant:0` may confirm only under complete V2/V3 gates.
4. Failure of all item-1402 positives does not authorize changing item 4352 or selecting a new positive.
5. Failure of item 4352 does not authorize selecting another known record after implementation.
6. The report must disclose that the second item was selected from known pre-existing outcomes.

## 5. Amended implementation outcomes

### 5.1 PASS

V2 G.1 remains in force with these amendments:

- key isolation is required from harness, candidate, container, and benchmark-controlled code;
- parent and report code are explicitly measured/pinned TCB components, not claimed to be unable to access host key material;
- signature validity establishes an internal integrity boundary only;
- reproducibility for third parties comes from deterministic local replay;
- the equal-commit APPS positive derives non-adaptivity from the pre-V3 BenchAudit cutoff-binding history, not tautological benchmark-side ancestry; and
- both frozen positive items must be attempted without changing the protocol, while at least the primary V2 positive remains required to confirm exactly as V2 specifies.

### 5.2 FAIL

V2 G.2 remains in force, except that parent access to key material is not by itself a failure under V3. One of the following is a failure:

- harness, candidate, container, or benchmark-controlled code can access or use the key;
- a generic parent-supplied byte string can be signed as if supervisor-captured;
- a signature is presented as third-party proof without deterministic replay artifacts;
- an equal-commit positive derives non-adaptivity without the valid pre-V3 BenchAudit cutoff-binding history;
- a TCB build changes without invalidating or reissuing its attestation; or
- any existing V2 safety failure occurs.

### 5.3 NOT IDENTIFIABLE

V2 G.3 remains in force. In addition, the correct result is `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR_OS_VISIBLE` if:

- the parent/report/supervisor TCB cannot be pinned and disclosed;
- the execution transcript cannot be independently replayed without relying on the private key; or
- the BenchAudit cutoff-binding ancestry required for the equal-commit positive cannot be verified.

## 6. Nonactivation and forbidden actions

This V3 protocol does not authorize:

- implementation of the trusted supervisor, signer, provenance verifier, or manifest registry;
- activation of a CLI, producer, checker, report path, or promotion proof;
- modification of `benchcore/promotion.py` or `benchcore/evaluator_execution.py`;
- removal of any `DISABLED_UNATTESTED_PROOFS` entry;
- rerunning APPS or generating/selecting a new positive after an implementation result;
- rewriting V1, V2, or any historical APPS/DS-1000 report; or
- treating signatures held by BenchAudit as independent third-party attestation.

## 7. Frozen conclusion

V3 corrects the key-custody claim, assigns the equal-commit non-adaptive warrant to the correct repository history, and expands the frozen positive opportunity from one item to two using only pre-existing records.

It does not award `PASS`, `FAIL`, or `NOT_IDENTIFIABLE` for an implementation. The implementation status remains:

```text
PROTOCOL_FROZEN_PENDING_INDEPENDENT_REVIEW
```
