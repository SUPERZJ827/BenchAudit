# WorkspaceBench：重复逻辑输入文件名的自动确认验证（2026-07-20）

## 结论

新增的 `ambiguous_input_filename` verifier 已在 WorkspaceBench full388 上发现并自动确认 **1 个真实数据缺陷**：`workspacebench-351` 的 manifest 将两份不同内容的输入都命名为 `table.xlsx`。任何按逻辑文件名暴露输入的平面工作目录都无法同时无歧义地提供这两份文件。

这是一个确定性 artifact collision，不是 LLM 对“任务是否覆盖”的判断。

## 证据

| item | 逻辑名 | 文件 1 | 文件 2 | 结论 |
|---|---|---|---|---|
| `workspacebench-351` | `table.xlsx` | `data/1a6aa769eb9ec70a_table.xlsx`，13,150 B，SHA-256 `1a6aa769…54753257` | `data/fe4103768eb82bc1_table.xlsx`，207,610 B，SHA-256 `fe410376…d711625e` | 同名但字节不同，confirmed |

判定条件刻意很窄：必须同时满足（1）manifest 有重复逻辑文件名；（2）两条记录都可在显式 allowlist 根下 materialize；（3）对应字节 SHA-256 不同。仅有重复 metadata、相同内容副本、或无法安全读取的路径都不会被确认。

## 受控 mutation 验证

在 full388 上新增第六个 blind operator：`manifest_filename_content_collision`。它只对至少有两份、且已在受信根下确认字节不同的 manifest 输入构造 collision；mutation provenance 保留在 sidecar，审计行本身不包含标签。

| 指标 | 结果 |
|---|---:|
| source items | 388 |
| 可构造配对 | 352 |
| 不适用/安全跳过 | 36 |
| exact mutation recall | 352/352 = 1.000，95% Wilson [0.989, 1.000] |
| paired discrimination | 352/352 = 1.000，95% Wilson [0.989, 1.000] |
| extra / duplicate delta alarms | 0 / 0 |
| clean-side collision alarms | 1（即真实的 `workspacebench-351`） |

历史五类 structural mutations 在同一 full388 上已有 1,940/1,940 exact 与 paired discrimination。本次不是重跑它们，而是新增一个此前未覆盖的 defect class。

## 边界

该结果证明此 verifier 对“同名、不同字节的可见输入”这一类缺陷有效，并且在全量数据中找到一个真实实例；它不估计其他结构缺陷或语义缺陷的总体 recall。输出文件重复、self-loop dependency、自然语言任务与 rubric 是否覆盖等仍需单独的 verifier 与相应的可判定 oracle。
