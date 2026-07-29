# Workspace grounding A″：冻结 calibration 结果

协议：`workspace-grounding-a-double-prime-residue-v1-20260729`

结论：**Calibration PASS，但仅为开发集诊断，不构成泛化证据。**

本轮使用 A′ 已缓存结果与同次运行的冻结 WorkspaceBench 源数据进行离线
重放，API 调用数为 0。R2a–R2d 是查看 7 条 dev20 漏检后设计的规则族，
因此本页所有恢复率都带有明确的开发选择偏差。

## 1. 实现与复现状态

- Spec 复核提交：`6247180`
- 可执行输入澄清提交：`4c00b7d`
- 首版实现提交：`0471021`
- 闭集与计量修复提交：`7bad3b2`
- 定向测试：19 passed
- 全量测试：800 passed
- API 调用：0
- operational unknown：0
- review ceiling escape：0

最终分析在 `PYTHONHASHSEED=1` 与 `2` 下逐字节一致：

| 产物 | SHA256 |
|---|---|
| `analysis.json` | `235a710fb5b3e62a1c86873f6ff6838f60f3f21ecd19d60e75d1c69383d8e7f1` |
| `observations.jsonl` | `557dd1b3b7d2330fe0a63b886f596a3ea3b28223b34f8a6cd6e1a1bd00bc64e8` |
| `h1_diagnostics.jsonl` | `8e2eb9cc7d1e1203ca6311812e73242d6518a750b2ef1c19bee7e1876e7e6521` |

完整 15 组合数据保存在
`A_DOUBLE_PRIME_CALIBRATION_ANALYSIS_20260729.json`。

## 2. 主结果

冻结 tie-break 优先选择候选数最少的通过组合，因此最终工作点是
`R2c + R2d`：

| 方法 | Candidate | Candidate rate | Family TP | Family recall | Reviewed P/R/F1 |
|---|---:|---:|---:|---:|---:|
| 旧 A | 211 | 52.1% | 16/19 | 84.2% | 0.850 / 0.810 / 0.829 |
| A′ | 188 | 46.4% | 12/19 | 63.2% | 0.813 / 0.619 / 0.703 |
| **A″：R2c+R2d** | **205** | **50.6%** | **16/19** | **84.2%** | **0.857 / 0.857 / 0.857** |
| A″ 高召回备选：R2a+R2c+R2d | 210 | 51.9% | 17/19 | 89.5% | 0.864 / 0.905 / 0.884 |
| A″ 四规则全并集 | 226 | 55.8% | 19/19 | 100.0% | 0.808 / 1.000 / 0.894 |

主工作点相对 A′：

- 新增 17 条候选；
- 恢复 4 条已知 family positive；
- family recall 从 63.2% 恢复到 84.2%；
- 边际成本为 4.25 条候选/恢复；
- candidate rate 增加 4.2 个百分点。

主工作点相对旧 A：

- 候选少 6 条；
- family recall 持平；
- 按“20 次 task router + 每候选一次 verifier”的统一口径，逻辑调用
  从 231 降至 225，减少 2.6%。

Reviewed P/R/F1 只覆盖 28/405 条、且 reference selection biased，只能作为
次要诊断，不能称为全量 precision/recall。

## 3. 单规则结果

| 规则 | 新增候选 | 总候选 | Family TP | 恢复 | 边际成本 | 单独 PASS |
|---|---:|---:|---:|---:|---:|---|
| R2a 顺序/位置 | 5 | 193 | 13/19 | 1 | 5.00 | 否 |
| R2b 数量/闭集 | 32 | 220 | 17/19 | 5 | 6.40 | 否 |
| R2c subtype modifier | 1 | 189 | 13/19 | 1 | 1.00 | 否 |
| R2d 具名结构 | 16 | 204 | 15/19 | 3 | 5.33 | 否 |

红队对 R2b 候选膨胀的预警成立：R2b 能恢复 5/7 条已知漏检，但单独使用
会达到 220 条候选，超过 211 的硬预算。四规则全并集虽然恢复 7/7，仍因
226 条候选而 FAIL。结果支持“规则能找回问题，但必须控制约束粒度”的
诊断，而不支持无条件合并全部规则。

15 个非空组合中共有 3 个满足冻结门槛：

1. R2c + R2d：205 条，16/19；
2. R2a + R2d：209 条，16/19；
3. R2a + R2c + R2d：210 条，17/19。

协议首先最小化 candidate count，所以选择第 1 个；这不是根据最终指标
临时改变 tie-break。

### 3.1 R2c 的单样本支持与工作点脆弱性

冻结工作点虽然通过 calibration gate，但 R2c 的数据支持仍然很窄：

- R2c 在 405 条 rubric 上的 `raw_trigger_count` 只有 1；
- 该触发恰好恢复 7 条目标漏检中的 1 条，在其余 398 条上触发 0 次；
- 去掉 R2c 后，当前工作点退化为 R2d 单独：204 条候选、15/19，
  不再通过 family TP 门槛；
- 不使用 R2c 时仍能通过的最小组合是 R2a+R2d：209 条候选、
  16/19，边际成本为 5.25，而不是头条工作点的 4.25。

R2c 的 head/modifier 机制通过了共享 head、已获支持 modifier、同词异
短语和多竞争 head 的对抗测试，因此这不是 marker 换名；但它在真实
rubric 上没有第二个触发样本，不能据此声称结构消歧机制已经获得统计支持。
205 条候选与 4.25 的边际成本应被理解为脆弱的开发集工作点。

### 3.2 独立词表消融：未发现针对 7 条漏检的词表拟合

独立红队在同一冻结 cache 上进行了三项零 API 离线消融。以下数字是复核层
诊断，不改写主 `analysis.json` 的 15 组合表。

第一项按“设计时查看的 7 条漏检”和其余 398 条拆分规则触发：

| 规则 | 总触发 | 命中目标 7 条 | 命中其余 398 条 | 非目标触发占比 |
|---|---:|---:|---:|---:|
| R2a | 5 | 1 | 4 | 80% |
| R2b | 32 | 5 | 27 | 84% |
| R2c | 1 | 1 | 0 | 0% |
| R2d | 16 | 3 | 13 | 81% |

R2a/R2b/R2d 的触发并未局限在用于设计规则的 7 条上。这是反对 item-ID
特例化或仅匹配目标措辞的正面证据；但其余 398 条大多没有完整标签，因此
“非目标触发”不等价于正确发现，也不能称为跨 task 泛化 precision。

第二项将词表换成不依赖这 7 条样本的更宽先验：

- R2c：heads 增加 17 项、modifiers 增加 19 项，分别或同时加宽后，
  冻结工作点仍为 205 条候选、16/19；
- R2d 单规则：governing heads 从 8 项加宽到 22 项后为
  209 条候选、15/19，只增加 5 条候选，没有增加 family recall；
- R2b 单规则：将固定形容词表替换为通用的最多 3 token 语法槽后为
  226 条候选、17/19，只增加 6 条候选，没有增加 family recall。

第三项将词表缩到最小通用集：

- R2c 只保留 4 个 heads 与 7 个 modifiers，冻结工作点仍为
  205 条候选、16/19；
- R2d 只保留 `section`、`part`、`chapter`，仍为
  204 条候选、15/19。

三项消融一致说明：当前窄词表主要在控制候选成本，不是在选择 7 条目标
漏检。此前将 R2b/R2c 的留一敏感性解释成词表拟合并不成立。

仍需保留两个较窄的边界：R2c 只有 1 个真实触发，缺少统计支持；R2d 的
`chapter` 触发包含 4 条非 family 候选、没有增加 family recall，加宽
heads 也只增加成本。
`suggestion`/`recommendation` 是对 Spec 中示例 governing head 的实现层
延伸，本轮没有影响结果，应在文字上明确但不构成拟合证据。

## 4. 与实现前推演的对照

四规则全并集对 7 条实现前预期漏检的恢复为 7/7：

- R2a：恢复顺序/位置案例；
- R2b：恢复 input 描述性数量、凭空数量与闭集案例；
- R2c：只恢复共享 `chart` head 下的 `bar` modifier 案例；
- R2d：恢复具名章节/类别结构案例。

实现调试中发现并修复了两处与冻结 Spec 不一致的缺口：

1. 没有显式数字的具名闭集未被抽成 countable atom；
2. input evidence 以十个枚举项而非“ten suggestions”字面数字表达时，
   未被识别为描述性数量。

这些修复依据 §9.2 与 §11.3 的实现前要求完成，不是看到最终 PASS 后新增
规则。修复同时新增回归测试。另修复 reviewed 指标未限制到 calibration
20 task 的计量错误；该错误不影响 candidate/family gate。

## 5. H1 卫生诊断

H1 共检查 133 条正面支持型拒绝：

- valid：48；
- invalid：13；
- source text unavailable：72（72/133，54.1%）；
- 其中空 quote：9，与预注册预期一致。

H1 不进入候选集、不调用 verifier、不产生 finding，因此不影响 A″
calibration gate。本轮分析器没有传入 `input_text`；72 条 unknown 全部来自
`evidence_source="input"`，因此 `input` 来源的完整逐字校验在本轮不可
识别，被诚实记为 unknown，没有伪装成 valid 或 invalid。

同一输入可见性边界也影响 R2b。R2b 的 descriptive atoms 只能使用
`input_inventory`、空的 `input_text` 与 `evidence_quote`：当真实输入正文
包含支持信息但 inventory/quote 未保留时，step 3 可能无法应用应有的委托
豁免，4b 也可能被归因为 4a。因此 R2b 的 32 条新增候选和 5 条恢复只能
视为输入部分可见条件下的开发诊断，其子类型归因并非完全可识别。冻结
工作点 R2c+R2d 不包含 R2b，所以这一限制不改变 205/16-19 的头条数字。

## 6. 诚实边界与下一步

本轮只能说明：

> 在已经参与规则设计的 dev20 上，受限的 subtype-modifier 与具名结构
> residue 可以将 A′ 恢复到旧 A 的 family recall，同时把候选数保持在旧 A
> 以下。

本轮不能说明：

- A″ 已跨 task 泛化；
- 205 条候选的全量 precision 为 85.7%；
- 新规则可产生 confirmed finding；
- R2b 应进入默认流程；
- 规则在完整 388 题上仍保持相同成本。

按照冻结协议，下一步不是继续在 dev20 调规则，而是：

1. 对提交 `7bad3b2` 和本结果做独立对抗复核；
2. 复核通过后才允许运行未使用的 internal10；
3. internal10 必须使用冻结工作点 `R2c + R2d`，不得重新选组合；
4. internal10 不通过则停止，不创建第四份 holdout；
5. internal10 通过后，才创建 task-disjoint 的新 holdout 检验泛化。

### 6.1 internal10 运行前冻结的脆弱性预期

在看到 internal10 结果前，冻结如下预期与处理纪律：

- 工作点保持 `R2c + R2d`，不得改为更稳健但候选更多的 R2a+R2d；
- 根据 dev20 的触发稀疏性，R2c 在 internal10 上预期只触发 0–1 次；
- 若 R2c 触发 0 次，工作点在该批数据上会实际等价于 R2d 单独，family
  recall 有较大概率不能达到 85%；
- 这种情况按正常负结果记录，不修改 tie-break、不补词表、不切换组合，
  也不进行 operational retry；
- internal10 的完整样本、指标和成本 gate 仍需在运行前单独冻结；本段只
  冻结 R2c 的触发预期和失败处理，不以事后结果反推协议。

## 7. 复现命令

```bash
python scripts/analyze_workspace_a_double_prime.py \
  --artifact-root /home/zhoujun/llmdata/after623 \
  --reviewed-reference /home/zhoujun/llmdata/after623/WorkspaceBench_full388_Codex证据化逐条标注_20260720.md \
  --output-dir /home/zhoujun/llmdata/after623/reports/workspace_grounding_a_double_prime_calibration_20260729
```

脚本在读取数据前校验 8 份冻结输入哈希；缺文件或任一哈希不匹配均
fail-closed。
