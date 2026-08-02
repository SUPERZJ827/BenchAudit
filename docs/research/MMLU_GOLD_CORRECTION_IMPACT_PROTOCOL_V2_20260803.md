# MMLU-Redux gold-correction impact: frozen reanalysis protocol V2

> Frozen: 2026-08-03 (Asia/Singapore)  
> Phase: P0 of the ICLR measurement-study plan  
> API budget: 0  
> Outcome inspected before freeze: **true**  
> Reanalysis output inspected before this correction: **false**

## 0. Status and inheritance

This protocol supersedes only one mistyped input hash in the immutable V1
protocol. All formulas, gates, bootstrap parameters, interpretation limits,
outputs, tests, and stop conditions in V1 remain unchanged.

| Frozen object | Value |
|---|---|
| V1 protocol commit | `9f3e800` |
| V1 protocol SHA-256 | `0ba27bd590e763bbdfee0332b87193e8263cb0d2368d612309c4747cb991ad4b` |
| First implementation commit | `2d70199` |

V1 and the failed implementation commit remain immutable.

## 1. Failure observed before V2

Two independent replay attempts stopped at the same input-integrity gate before
writing `analysis.json`, `REPORT.md`, or `receipt.json`:

```text
NOT_IDENTIFIABLE_INPUT: SHA-256 mismatch for
reports/ranking_impact/answers/google__gemini-2.5-flash.jsonl:
observed 2bc96f33b908d22b4703f91e33c598eafa03b3be6a3516ca9c92fdd8fb400ec9
expected 2bc96f33b908d22b4703f91e33c598eafa03b6be6a3516ca9c92fdd8fb400ec9
```

Thus the fail-closed gate worked. No numerical reanalysis result was produced or
inspected before this correction.

## 2. Frozen correction

The V1 Gemini hash contains one transcribed character error (`b6` instead of
`b3`). V2 freezes the locally measured file hash as:

| Input | Correct SHA-256 |
|---|---|
| `reports/ranking_impact/answers/google__gemini-2.5-flash.jsonl` | `2bc96f33b908d22b4703f91e33c598eafa03b3be6a3516ca9c92fdd8fb400ec9` |

Before V2 was written, all 17 frozen inputs were rehashed. The other 16 hashes
matched V1 exactly. No input was edited or replaced.

## 3. Implementation rule

The implementation may change only:

1. the expected Gemini hash from the V1 mistyped value to the V2 value; and
2. the protocol path recorded in the receipt from V1 to this V2 file.

Any other formula, parameter, input, output, test, or interpretation change
requires a separate protocol. The two deterministic replays must start only
after this V2 file is committed and the two implementation-only changes are
committed.
