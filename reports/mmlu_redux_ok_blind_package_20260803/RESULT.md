# MMLU-Redux `ok` disagreement: mechanical routing and blind-package result

Date: 2026-08-03  
Branch: `research/iclr-measurement-study-20260803`

## Outcome

The review-level 2×2 population was recomputed after excluding operational and
unknown findings:

| Redux label | system substantive review | system no substantive review |
|---|---:|---:|
| explicit defect | 196 | 142 |
| `ok` | 86 | 544 |

The 32 Redux `expert` rows (10 reviewed, 22 not reviewed) are abstentions and
are excluded from both positive-control pools.

The frozen mechanical router evaluated all 86 Redux-`ok` disagreement items.
It confirmed one exact duplicate-choice defect and routed the remaining 85
items to blind semantic adjudication. A four-arm public package was then built:

| Arm | Rows | Purpose |
|---|---:|---|
| disagreement | 85 | system review, Redux `ok`, not mechanically confirmed |
| positive agreement | 40 | system review and explicit Redux defect |
| positive missed | 40 | no system review and explicit Redux defect |
| negative agreement | 40 | no system review and Redux `ok` |
| **Total** | **205** | |

The two positive controls are deliberately separate. Their sensitivity gap
measures how adjudication behaves on mutually recognized defects versus defects
the system missed.

## Mechanically confirmed item

- Item: `mmlu-redux-public_relations-36`
- Frozen system finding: `static_rule / duplicate_choices`
- Rule: `M-DUP-V1`
- Duplicate choice indices: `[2, 3]`
- Evidence level: deterministic, locally replayable for the frozen artifact

This single item may support a mechanically confirmed statement. It does not
generalize to the other 85 disagreement items.

## Blindness boundary

The public package contains only:

- `blind_id`
- `question`
- `choices`
- `declared_gold`
- `evaluator`

It contains no source arm, original item ID, system finding, Redux label,
aggregate arm count, or sealed-map path. The mapping and HMAC salt are stored
outside the repository with mode `0600`. This conversation has seen the source
counts and must not perform the adjudication. Adjudication must occur in a new,
history-free session and be committed before unsealing.

## Verification

- Targeted tests: `14 passed`
- Full tests in the source worktree: `585 passed`
- Fresh clone at commit `e534c03`: `583 passed, 2 skipped`
- The two skips are source-artifact integration checks; the frozen dataset is
  intentionally external to Git.
- The fresh clone still verifies the package builder with a 1,000-row
  constructive fixture and independently checks the committed 205-row package
  and receipt.

The first fresh-clone attempt exposed that the original integration tests
depended on the untracked frozen dataset. No success was claimed from that
attempt. The tests were made self-contained in commit `e534c03` and the
fresh-clone verification was rerun.

## Artifact hashes

| Artifact | SHA-256 |
|---|---|
| V2 protocol | `e6c004f1f600159716a187ea32f48234ca40b521be8df23b39c44e3c1aa9c846` |
| mechanical verifier | `6a3049abab99f2021a63cafa05ba1f3d11e94a565247dcc18998e7f5b159f7f3` |
| mechanical receipt | `2634748bb9cbbf67efeac9bf9cd94166709c0ef390c8546052b4063f67a92365` |
| blind-package builder | `156262eefeda98ee480db95e548b5add55e6c8abf0b232d1bdc26002acc0e264` |
| public package | `4ec29152bb30f69de3f0c9ed2f70c4d561b1eba2ff9c2cd1cb62ac670840b510` |
| package receipt | `e6eeb631cd0b2994916ae60f7302b1555c1c66302aa8b26beb45ea57d8788188` |
| adjudicator instructions | `ba2811db15e6a1dc88d06a4f8190daa4af0aa281b3f49fd7f76d646b426d3373` |

## Claim boundary

Before blind adjudication, the defensible result is:

> BenchAudit mechanically confirmed one duplicate-choice defect among 86
> substantive review findings that MMLU-Redux labeled `ok`; 85 disagreements
> remain unadjudicated.

It is not yet defensible to call any of those 85 items a human-annotation miss.
Agent adjudication can provide blind-agent-supported evidence; a claim about
human reannotation omissions requires independent human expert adjudication.
