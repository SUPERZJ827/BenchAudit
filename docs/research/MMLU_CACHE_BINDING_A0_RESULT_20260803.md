# MMLU historical-cache binding A0 result

> Date: 2026-08-03
> Outcome: `PASS_V2_FEASIBLE_WITH_RESIDUAL_UNATTESTED_PROMPT_SNAPSHOTS`
> API/network attempts: 0/0
> Candidate or holdout prompts reconstructed: 0

## Result

All seven known MMLU/ranking-impact caches have a complete forward binding from
cache path to report and from report/input manifest to the possibly touched
source-item set. Their union contains exactly 1,087 source items and has
SHA-256 `f06faeb336ef5241d76ef2342a2810d3bf460671bcfdb9d2b273a4033fdd077a`.

All seven caches also pass a live reverse golden test: an initial blind-solver
prompt for a known, already-exposed item was reconstructed under the recorded
historical key formula and its SHA-256 key was found in the corresponding
cache.

The evidence grades differ:

- four caches have report-bound implementation manifests whose
  `llm_client.py` and `llm_auditor.py` hashes match the historical Git commit;
- three 2026-07-13 caches predate implementation manifests. Their golden keys
  match the recorded dirty commit, but that prompt snapshot is empirical and
  unattested.

V2 is therefore feasible only if forward run-to-item bounds remain authoritative
for all seven caches, reverse absence remains supporting evidence, and the three
early snapshots are never described as attested.

## Frozen artifacts

| Artifact | SHA-256 |
|---|---|
| A0 scanner | `7cf786946b5f4b11710902bd480ae3fe08636ab8b10467555bb708e361b66c78` |
| `availability.json` | `15b777f4049799ed8538d00bbfb11a7847b9fc32d0c48ece187307308ac6f9e1` |
| `REPORT.md` | `84c6c9e4c01b7e1c5a7fb4ee0f8445b996978a6e86d5c2f1c5cf418a052c24ff` |
| `receipt.json` | `ee2b178132191c5c81eb72322a0ca6f2f304c0e2ed351841b3039769e5c46263` |

Two independent temporary-directory runs and the final repository outputs were
byte-identical. The preflight did not select candidates, inspect candidate
labels, generate a holdout manifest, or run an auditor.

## Consequence for V2

The V2 contamination protocol may now be frozen once. It must scope evidence to
artifacts capable of causing recorded development exposure, use the seven
forward bindings as the upper bound, and use reconstructable initial cache keys
only as a lower-bound cross-check. Any additional relevant cache discovered by
V2 that is absent from this A0 case manifest is fail-closed.
