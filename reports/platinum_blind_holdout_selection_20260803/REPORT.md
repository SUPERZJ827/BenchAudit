# Platinum blind holdout selection result

- Outcome: **PASS_BLIND_HOLDOUT_MANIFEST_897**
- Public manifest items: **897**
- Truth fields in public manifest: **false**
- Truth unsealed: **false**
- Auditor/API/network execution: **zero**

## Frozen composition

| Layer | Rows | Revised | Rejected | Positive | Negative |
|---|---:|---:|---:|---:|---:|
| A arithmetic | 442 | 3 | 22 | 25 | 417 |
| B text QA | 300 | 85 | 85 | 170 | 130 |
| C reasoning/coreference | 155 | 0 | 15 | 15 | 140 |

VQA and TabFact are absent from the public manifest under the pre-registered
out-of-modality and non-identifiable-identity exclusions.

## Artifacts

- Public manifest SHA-256:
  `37637b8e4d19e66f002d9b766180b57c7076b31123b7139b28441ec6beaabe32`
- Selection receipt SHA-256:
  `e62acd45f95c0cac00582207d2f02e6618444bb2c3168e595ffc0317e4287f7c`
- Sealed truth commitment SHA-256:
  `8e09ebc36684b24d291902e5942daa40a20bb69994d2a5cd2ad9e96a02ddfe0a`
- Sealed truth file mode: `0600`
- The sealed truth path is intentionally not recorded in public artifacts.

Two independent output paths produced byte-identical public manifests, sealed
truth artifacts, and receipts. The replay compared bytes only; truth content was
not printed or inspected.

## Verification

- Selector tests before generation: **9 passed**
- Fresh-clone relevant tests: **14 passed**
- Fresh-clone direct CLI import/help probe: **passed**
- Item keys in public manifest: exactly `config`, `layer`, `opaque_id`
- NumPy RNG instantiated: **false**

## Pre-publication correction

The first direct CLI probe failed before opening any dataset because the script
could be imported as a module but not executed directly from `scripts/`. No
manifest, truth, or receipt existed after that failure. Commit `6eb60ee` fixed
the import path and added a direct-entrypoint regression test; a new fresh clone
then passed before selection was executed.

## Boundary

This commit proves deterministic selection and a public commitment to the sealed
truth before any holdout audit. It does not prove that a Byzantine operator with
source-dataset access could not inspect labels out of band. No detection metric
or model-impact claim is produced in this phase.
