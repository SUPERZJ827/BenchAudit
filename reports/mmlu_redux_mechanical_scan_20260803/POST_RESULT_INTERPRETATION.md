# MMLU-Redux mechanical scan: post-result interpretation

This addendum does not modify the frozen protocol, scanner, findings, receipt,
or generated report. It binds them by SHA-256 and records the evidentiary limit
revealed by the preregistered normalization ladder.

## Correct result

The scan executed completely over all 5,700 rows, and two independent runs
produced byte-identical `findings.jsonl`, `REPORT.md`, and `receipt.json`.

The defensible confirmed result is the T1 row, not the T3 union:

| Evidence class | Items | Redux `ok` | Interpretation |
|---|---:|---:|---|
| R1/T1 byte-identical duplicate choices | 7 | 6 | Confirmation eligible |
| R1/T2-only | 1 | 0 | Not independently confirmation eligible |
| R1/T3-only | 15 | 13 | Invalid for confirmation |
| R2 unresolvable gold | 0 | 0 | No finding |
| R3 empty choice | 0 | 0 | No finding |

Of the six Redux-`ok` T1 findings, one was the previously known development
positive (`mmlu-redux-public_relations-36`) and five are newly surfaced in the
4,613-item remaining partition.

## Why T3 failed

The protocol froze T3 as T2 followed by removal of boundary Unicode `P*`
characters. Unicode classifies ASCII hyphen-minus and en dash as punctuation.
Consequently T3 erased semantically meaningful signs and collapsed examples
such as:

- `1` and `-1`;
- `2` and `-2`;
- `80%` and `-80%`;
- `(3, 2)` and `(–3, 2)` after parentheses exposed the sign.

Those are not duplicate choices. The 15-item T3-only increment is therefore a
negative result about the normalization rule, not evidence of 15 construction
defects. The frozen result remains useful because all three tiers were reported
instead of selecting the largest count after inspection.

## Why the T2 extension is capped

The sole T2-only item is `mmlu-redux-formal_logic-33`, where case folding maps
`Sc ≡ Ej` and `sC ≡ eJ` to the same text. Case can be semantically meaningful in
formal notation. The item is already labeled `multiple_correct_answers` by
Redux, but this normalization alone does not independently confirm why.

The six Redux-`ok` items in the cumulative T2 count are all already T1
byte-identical findings. Therefore capping the T2-only extension loses no new
Redux-`ok` mechanical discovery.

## Defensible wording

> In the frozen 5,700-item MMLU-Redux artifact, seven items contain
> byte-identical duplicate choices. Six carry the Redux label `ok`; one of those
> six was previously known, while five occur in the 4,613-item remaining
> partition. The preregistered looser normalization tiers did not add defensible
> `ok` findings: T2 added only an already-labeled item, and T3 was invalidated by
> sign erasure. No unresolvable gold label or empty choice was found.

This does not estimate total benchmark error, prove score impact, criticize
human annotation quality, or activate these rules in production BenchAudit.

## Bound artifacts

| Artifact | SHA-256 |
|---|---|
| Frozen protocol | `b974fef9962653c99f4787c820258d45d7c2cc0f32225539e0216fcde4e08bc4` |
| Findings | `f0e14a95cf2d6d26c52af2e53d39875f1d019865d1dc58f783128b44df2e60a4` |
| Generated report | `00fc8f12117b04e76b68de1f14aeb10732b83c15a49614fedec571507e34c276` |
| Stable receipt | `3820f3bb1f3ddaa5ac638ec19b6357e2a9af7be6242d6312add0d4e0d37617f7` |
