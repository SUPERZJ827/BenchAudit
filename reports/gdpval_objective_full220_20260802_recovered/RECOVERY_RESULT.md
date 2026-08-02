# GDPVal artifact recovery result

## Decision

`RECOVERED_WITH_UNKNOWN_AT_FREEZE_ARTIFACTS`

The final checker execution emitted 7 confirmed evidence records after two artifacts were restored from their exact declared paths at dataset revision `11e7900cdcac61bc4daf59e65feb238acda98fbf`.

**This does not replace the externally reportable headline of `5 confirmed + 2 coverage unknown`.** Both restored artifacts had `expected_sha256: null` and `unknown_at_freeze: true`. The deliverable dependency was additionally masked by the initially missing reference workbook and was only discovered during the first recovery rerun.

## Freeze-before-fetch sequence

| Stage | Commit | Manifest SHA-256 | Outcome known? | Expected artifact hash known? |
|---|---|---|---|---|
| Initial recovery manifest, before any artifact lookup/fetch | `9231580` | `c364ca15d935c2bbf8bfcf2577d00767cae4d885e5bbee2523890a49c0808fbe` | Yes | No |
| Reference bytes bound before first rerun | `6f58d33` | `2016d99ba5dfa1f17f6267fbdfe581a4193cdbf27448782100568c123c386c53` | Yes | No |
| Newly exposed deliverable dependency frozen before its fetch | `8ff05f8` | `ab513e40c2b24c4e167f74c1c7ea10354585bf8172ede80a8b2863f3b29b2397` | Yes | No |
| Both observed artifact digests bound before final reruns | `af685b9` | `286053be53f0dd7ca6033b0bd1a6c0e4900ac05bb51402b13c475f727ab752dd` | Yes | No |

No artifact was fetched before its corresponding unknown-hash manifest entry had been committed. The second dependency was not known at the initial freeze; that limitation is part of the result rather than being rewritten away.

## Artifact observations

| Role | Declared path | Observed SHA-256 | Bytes | Receipt SHA-256 |
|---|---|---|---:|---|
| reference | `reference_files/cc781e4dc0985c8eb327a53ec03b5900/Population v2.xlsx` | `e64a9d3ba60bbaecef0e6685a57b618e9b321bcd813c79e4460be36bf8c79fb7` | 61,470 | `a8613f92b01e06c1d45cffc4c58a96758851c3b301b139309ae60f6c6aa27c2d` |
| deliverable | `deliverable_files/2837faa0a7a6a95f40dfbe45bf66c7fb/Sample v2.xlsx` | `72b74484e2eeb6bd1a5b5391220a6dea142f3b7fbd6c218490b1aa633dbafcbb` | 79,328 | `b8880edddbc3ff4e3e8abf7f04c1c1796deec4e6ab8b017e51389a54b9659029` |

The resolver reports `unverified_without_external_digest` for both objects because no independent expected digest was available at freeze time. Repository revision pinning and the resolver receipts bind where the bytes came from; they do not retroactively create a pre-registered content digest.

## Final reruns

| Run | Items | Violations | Confirmed | Review | Unknown findings | Coverage unknown | Operational failed | Raw audit SHA-256 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 220 | 18 | 7 | 11 | 0 | 0 | 0 | `66df8e414adfc766e18f60728536f14b05561bb36005b67c5a3dbaffbfa4641c` |
| 2 | 220 | 18 | 7 | 11 | 0 | 0 | 0 | `858b1b6e230f137831ae4c5290631d9ecaed753febc28ad33acfde1b7cec8962` |

Both runs have stable semantic payload SHA-256:

`1ef7d44c197ba73de8a0bcfb4844ee33356ce74dc89575c1f906bf47fe268815`

The raw JSON hashes differ because raw run metadata contains different elapsed times. Violation payloads and coverage ledgers are exactly equal.

Confirmed breakdown observed by the checker:

- `task_artifact_contract_mismatch`: 4
- `rubric_artifact_contract_mismatch`: 2
- `rubric_reference_contract_mismatch`: 1

## Claim boundary

The recovery shows that the historical count difference is fully explained by missing local artifact coverage. It does not establish that the artifact bytes were independently precommitted before the recovery question was known.

For external reporting, continue to state:

> GDPVal 220: **5 confirmed + 2 coverage unknown** in the clean, pre-recovery rerun. A subsequent pinned-revision recovery reproduced checker output of 7, but the two restored records depend on artifacts whose expected hashes were unknown at freeze time.

The historical dirty-worktree result is not reinstated as the primary result.
