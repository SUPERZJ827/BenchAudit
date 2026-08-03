# Untouched Platinum detection-holdout availability preflight

- Detection source: **PASS_DETECTION_HOLDOUT_SOURCE_AVAILABLE**
- Model-output matrix: **NOT_IDENTIFIABLE_MODEL_OUTPUT_LINKAGE**
- Configs/rows: **12 / 2434**
- Natural positives / negative controls: **825 / 1609**
- Identity-eligible positives / negatives: **791 / 1443**
- Identity-eligible configs: **11**
- Mixed-label configs: **9**
- Identity-eligible mixed-label configs: **8**
- Paper-cache bytes inspected: **73999521**
- Item content or item-label mapping emitted: **false**
- LLM/API/auditor execution: **zero**

## Per-config aggregates

| config | rows | consensus | verified | revised | rejected | positive | negative | duplicate IDs | identity outcome |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| bbh_logical_deduction_three_objects | 200 | 159 | 41 | 0 | 0 | 0 | 200 | 0 | AVAILABLE |
| bbh_navigate | 200 | 118 | 82 | 0 | 0 | 0 | 200 | 0 | AVAILABLE |
| bbh_object_counting | 200 | 57 | 133 | 0 | 10 | 10 | 190 | 0 | AVAILABLE |
| drop | 250 | 27 | 3 | 179 | 41 | 220 | 30 | 0 | AVAILABLE |
| hotpotqa | 250 | 48 | 45 | 88 | 69 | 157 | 93 | 0 | AVAILABLE |
| multiarith | 174 | 164 | 3 | 3 | 4 | 7 | 167 | 0 | AVAILABLE |
| singleop | 159 | 142 | 8 | 0 | 9 | 9 | 150 | 0 | AVAILABLE |
| singleq | 109 | 87 | 13 | 0 | 9 | 9 | 100 | 0 | AVAILABLE |
| squad | 250 | 69 | 49 | 43 | 89 | 132 | 118 | 0 | AVAILABLE |
| tab_fact | 200 | 56 | 110 | 3 | 31 | 34 | 166 | 17 | NOT_IDENTIFIABLE_ITEM_IDENTITY |
| vqa | 242 | 0 | 0 | 242 | 0 | 242 | 0 | 0 | AVAILABLE |
| winograd_wsc | 200 | 77 | 118 | 0 | 5 | 5 | 195 | 0 | AVAILABLE |

## Pre-publication implementation correction

An initial uncommitted run incorrectly treated `tab_fact`'s 17 duplicate native IDs as a global identity failure. The frozen protocol requires at least three identity-valid configs, not all twelve. The implementation was aligned to that existing gate before this result was committed; no threshold or config scope changed.

## Boundary

A PASS on the dataset axis only establishes that a future, separately frozen detection-holdout protocol is feasible. The cache axis stops because the published primitive cache keys expose generated prompt text and model/configuration fields but no explicit item identity; policy forbids treating prompt-text matching as an exact item join.
