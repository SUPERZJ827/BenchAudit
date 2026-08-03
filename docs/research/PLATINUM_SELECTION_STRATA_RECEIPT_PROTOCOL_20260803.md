# Platinum Selection Strata 聚合 Receipt 协议

> Freeze date: 2026-08-03  
> Input: committed aggregate-only availability JSON  
> Dataset/item-label mapping access: forbidden  
> Network/API/auditor execution: forbidden

## 0. 目的

为 selection protocol 提供一份专门、可机械复算的 layer × config × status 聚合
receipt，证明 revised/rejected 配额可满足，并避免依赖人从报告表格誊写数字。

## 1. 唯一输入

`reports/platinum_untouched_holdout_availability_20260803/availability.json`

- commit: `bb48a96e53c211a8e552b783f942b28293c21809`
- SHA-256: `2a1b1164f1e9831e5554abfcac14df44cf78963957cce219ecc9381f2d3e7f77`
- schema: `platinum-untouched-availability-v1`

该输入的 `config_aggregates[].status_counts` 已含
`consensus/verified/revised/rejected` 聚合数。本轮不得重新打开 parquet、缓存或任何
item-level 文件。

## 2. 冻结层定义

- Layer A: `multiarith`, `singleop`, `singleq`
- Layer B: `drop`, `hotpotqa`, `squad`
- Layer C: `bbh_logical_deduction_three_objects`, `bbh_navigate`,
  `bbh_object_counting`, `winograd_wsc`
- Layer X: `vqa`
- Identity-excluded: `tab_fact`

每个 config 必须恰好出现一次；未知或重复 config fail closed。

## 3. 冻结 Layer B 配额

| Config | Revised | Rejected | Negative |
|---|---:|---:|---:|
| drop | 40 | 30 | 30 |
| hotpotqa | 25 | 25 | 50 |
| squad | 20 | 30 | 50 |

`negative = consensus + verified`。每一格 source count 必须大于等于 quota。

## 4. Stable 输出

只输出：

- input hash/schema；
- 每 config 四状态计数；
- 每 layer 四状态合计、positive/negative/rows；
- Layer B 每格 source count、quota、headroom 与 gate；
- Layer A `revised=3/rejected=22` gate；
- VQA `positive=242/negative=0` gate；
- TabFact identity outcome；
- API/network/dataset access 均为零；
- analyzer 与 receipt hash。

不得输出 item ID、题面、gold、target、prompt、cache response 或 item↔label mapping。

## 5. 结局

- `PASS_SELECTION_STRATA_AVAILABLE`
- `SOURCE_HASH_MISMATCH`
- `SCHEMA_MISMATCH`
- `CONFIG_SCOPE_MISMATCH`
- `INSUFFICIENT_REVISED_QUOTA`
- `INSUFFICIENT_REJECTED_QUOTA`
- `INSUFFICIENT_NEGATIVE_QUOTA`
- `AGGREGATE_INVARIANT_FAILURE`

非 PASS 不得修改 quota 或读取原数据补救。
