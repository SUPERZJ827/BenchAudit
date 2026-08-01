# GDPVal clean rerun discrepancy

Date: 2026-08-02

Decision: `DISCREPANCY`. No code or cache was changed to force agreement.

## Frozen input and code

- Clean commit: `a4d5faee7df83be73264904dfd8a1af2322a9cf1`
- Input SHA-256: `f8422fab9b21d90c0ee5f0659842ab666d418cb8940842918f9f4b0df7ae0202`
- The independently computed digest matches the digest embedded in the filename.
- Dataset revision: `11e7900cdcac61bc4daf59e65feb238acda98fbf`
- Artifact downloads were disabled. The historical private cache was used read-only.
- LLM/API use: none.

## Count discrepancy

| Run | Items | Violations | Confirmed | Review | Unknown |
|---|---:|---:|---:|---:|---:|
| Historical 2026-07-16 | 220 | 18 | 7 | 11 | 0 |
| Clean run 1 | 220 | 16 | 5 | 11 | 0 |
| Clean run 2 | 220 | 16 | 5 | 11 | 0 |

Confirmed type differences:

| Defect type | Historical | Clean rerun |
|---|---:|---:|
| `task_artifact_contract_mismatch` | 4 | 3 |
| `rubric_artifact_contract_mismatch` | 2 | 1 |
| `rubric_reference_contract_mismatch` | 1 | 1 |

## Missing findings

Both missing confirmed findings belong to item
`83d10b06-26d1-4636-a32c-23f92c57f30b` (`source-row-00000000`):

1. `task_artifact_contract_mismatch` — task spreadsheet-column claims versus the
   Population/Sample workbook headers.
2. `rubric_artifact_contract_mismatch` — rubric spreadsheet-column claims versus
   the same workbook headers.

The current run recorded the corresponding `gdpval_workbook_replay` check as
`operational_failed`: `GDPvalArtifactNotCached` for
`reference_files/cc781e4dc0985c8eb327a53ec03b5900/Population v2.xlsx`.
The historical run therefore depended on artifact-cache state that is not
reproducible from the present cache snapshot.

## Two-run determinism

- Run 1 audit SHA-256: `0dba5fc79a4e812ee62f9e1b8002b6316fccb9d00a08f00b12fedcb6234ed7dc`
- Run 2 audit SHA-256: `5a56797539a8e4980ac124b5518f40e462a43e0d601aad79eefe78a7a638b5bc`
- Exact byte determinism: false.
- The only JSON difference is `run_metadata.elapsed_seconds` (`8.818448` versus
  `4.504578`). After removing that runtime field, the JSON payloads are equal.

This is still a failure of the preregistered exact-SHA determinism gate. The
result must not be relabeled as a pass merely because the semantic payloads
match after normalization.

