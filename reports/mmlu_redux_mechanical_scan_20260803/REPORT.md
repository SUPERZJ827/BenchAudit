# MMLU-Redux deterministic mechanical-defect full scan

Outcome: **SCAN_COMPLETE**

## Main table

| Rule | Tier | Distinct items | Redux `ok` | Explicit defect | `expert` abstention |
|---|---|---:|---:|---:|---:|
| R1 duplicate choices | T1 | 7 | 6 | 1 | 0 |
| R1 duplicate choices | T2 | 8 | 6 | 2 | 0 |
| R1 duplicate choices | T3 | 23 | 19 | 4 | 0 |
| R2 unresolvable gold | — | 0 | 0 | 0 | 0 |
| R3 empty choice | — | 0 | 0 | 0 | 0 |

R1 tiers are cumulative. Disjoint increments:

| Increment | Distinct items | Redux `ok` | Explicit defect | `expert` abstention |
|---|---:|---:|---:|---:|
| T1 | 7 | 6 | 1 | 0 |
| T2_only | 1 | 0 | 1 | 0 |
| T3_only | 15 | 13 | 2 | 0 |

## Distinct-item union

The R1(T3) ∪ R2 ∪ R3 union contains **23** distinct items: 19 Redux `ok`, 4 explicit defect, and 0 `expert` abstention.

Rule-overlap counts: `{"R1": 23}`.

## Frozen partitions

| Partition | Population | R1 T1 | R1 T2 | R1 T3 | R2 | R3 | Union |
|---|---:|---:|---:|---:|---:|---:|---:|
| development_1087 | 1087 | 2 | 3 | 6 | 0 | 0 | 6 |
| remaining_4613 | 4613 | 5 | 5 | 17 | 0 | 0 | 17 |

## Itemized Redux-`ok` findings

### `mmlu-redux-abstract_algebra-17`

- Subject: `abstract_algebra`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T3`: indices `[1, 2]`
  - Raw implicated choices: `["1","-1"]`

### `mmlu-redux-abstract_algebra-49`

- Subject: `abstract_algebra`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T3`: indices `[0, 1, 2, 3]`
  - Raw implicated choices: `["1","-1","i","-i"]`

### `mmlu-redux-business_ethics-22`

- Subject: `business_ethics`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T1`: indices `[0, 1]`
  - Raw implicated choices: `["Employee rights","Employee rights"]`
- `R1_duplicate_choices/T2`: indices `[0, 1]`
  - Raw implicated choices: `["Employee rights","Employee rights"]`
- `R1_duplicate_choices/T3`: indices `[0, 1]`
  - Raw implicated choices: `["Employee rights","Employee rights"]`

### `mmlu-redux-college_mathematics-41`

- Subject: `college_mathematics`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T3`: indices `[1, 3]`
  - Raw implicated choices: `["1","-1"]`

### `mmlu-redux-college_mathematics-60`

- Subject: `college_mathematics`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T3`: indices `[0, 3]`
  - Raw implicated choices: `["-2","2"]`

### `mmlu-redux-electrical_engineering-74`

- Subject: `electrical_engineering`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T1`: indices `[0, 2]`
  - Raw implicated choices: `["0.015 joule.","0.015 joule."]`
- `R1_duplicate_choices/T2`: indices `[0, 2]`
  - Raw implicated choices: `["0.015 joule.","0.015 joule."]`
- `R1_duplicate_choices/T3`: indices `[0, 2]`
  - Raw implicated choices: `["0.015 joule.","0.015 joule."]`

### `mmlu-redux-elementary_mathematics-26`

- Subject: `elementary_mathematics`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T3`: indices `[0, 2]`
  - Raw implicated choices: `["–7","7"]`

### `mmlu-redux-high_school_mathematics-22`

- Subject: `high_school_mathematics`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T3`: indices `[0, 1, 2, 3]`
  - Raw implicated choices: `["1","-1","-3","3"]`

### `mmlu-redux-high_school_mathematics-28`

- Subject: `high_school_mathematics`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T3`: indices `[1, 2]`
  - Raw implicated choices: `["2","-2"]`

### `mmlu-redux-high_school_mathematics-34`

- Subject: `high_school_mathematics`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T3`: indices `[2, 3]`
  - Raw implicated choices: `["1","-1"]`

### `mmlu-redux-high_school_mathematics-41`

- Subject: `high_school_mathematics`
- Partition: `development_1087`
- `R1_duplicate_choices/T3`: indices `[0, 1, 2, 3]`
  - Raw implicated choices: `["(3, 2)","(–3, 2)","(3, –2)","(–3, –2)"]`

### `mmlu-redux-high_school_mathematics-42`

- Subject: `high_school_mathematics`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T3`: indices `[2, 3]`
  - Raw implicated choices: `["-1","1"]`

### `mmlu-redux-high_school_mathematics-5`

- Subject: `high_school_mathematics`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T3`: indices `[1, 3]`
  - Raw implicated choices: `["(–1, 5)","(1, 5)"]`

### `mmlu-redux-high_school_mathematics-9`

- Subject: `high_school_mathematics`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T3`: indices `[1, 2]`
  - Raw implicated choices: `["-2","2"]`

### `mmlu-redux-high_school_physics-25`

- Subject: `high_school_physics`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T3`: indices `[0, 1, 2, 3]`
  - Raw implicated choices: `["99m","-99m","36m","-36m"]`

### `mmlu-redux-high_school_physics-54`

- Subject: `high_school_physics`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T1`: indices `[0, 1]`
  - Raw implicated choices: `["0.16 N","0.16 N"]`
- `R1_duplicate_choices/T2`: indices `[0, 1]`
  - Raw implicated choices: `["0.16 N","0.16 N"]`
- `R1_duplicate_choices/T3`: indices `[0, 1]`
  - Raw implicated choices: `["0.16 N","0.16 N"]`

### `mmlu-redux-international_law-25`

- Subject: `international_law`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T1`: indices `[0, 1]`
  - Raw implicated choices: `["All the members of the arbitral tribunal are appointed by the parties","All the members of the arbitral tribunal are appointed by the parties"]`
- `R1_duplicate_choices/T2`: indices `[0, 1]`
  - Raw implicated choices: `["All the members of the arbitral tribunal are appointed by the parties","All the members of the arbitral tribunal are appointed by the parties"]`
- `R1_duplicate_choices/T3`: indices `[0, 1]`
  - Raw implicated choices: `["All the members of the arbitral tribunal are appointed by the parties","All the members of the arbitral tribunal are appointed by the parties"]`

### `mmlu-redux-public_relations-36`

- Subject: `public_relations`
- Partition: `development_1087`
- `R1_duplicate_choices/T1`: indices `[2, 3]`
  - Raw implicated choices: `["manipulative","manipulative"]`
- `R1_duplicate_choices/T2`: indices `[2, 3]`
  - Raw implicated choices: `["manipulative","manipulative"]`
- `R1_duplicate_choices/T3`: indices `[2, 3]`
  - Raw implicated choices: `["manipulative","manipulative"]`

### `mmlu-redux-sociology-13`

- Subject: `sociology`
- Partition: `remaining_4613`
- `R1_duplicate_choices/T1`: indices `[2, 3]`
  - Raw implicated choices: `["debt repayments with interest can be greater than the amount of money received","debt repayments with interest can be greater than the amount of money received"]`
- `R1_duplicate_choices/T2`: indices `[2, 3]`
  - Raw implicated choices: `["debt repayments with interest can be greater than the amount of money received","debt repayments with interest can be greater than the amount of money received"]`
- `R1_duplicate_choices/T3`: indices `[2, 3]`
  - Raw implicated choices: `["debt repayments with interest can be greater than the amount of money received","debt repayments with interest can be greater than the amount of money received"]`

## Claim boundary

This scan covers only duplicate choices, unresolvable declared labels, and empty choices. It does not estimate the total MMLU-Redux defect rate, establish score impact, or show that human annotation quality is poor. R1 was partially informed by one previously known development-subset positive; R2 and R3 were declared unrun before freezing.
