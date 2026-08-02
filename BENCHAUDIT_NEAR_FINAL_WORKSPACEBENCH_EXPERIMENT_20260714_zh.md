# BenchAudit 接近最终版：WorkspaceBench 实验、代码实现与通用查错路线

> 更新时间：2026-07-14  
> 仓库：`/home/zhoujun/llmdata/after623`  
> 文档用途：给项目成员、Claude、面试官或论文合作者说明“现在做到了什么、结果如何、距离任意 benchmark 自动查错还差什么”。

> **证据口径：** 本文把受控注入、受控证书、自然数据 review、模型复核和人工确认
> 严格分开。文中的 `clean` 仅表示受控实验里“应被支持的一侧”，不表示原始
> Workspace-Bench item 已被人工证明无缺陷。所有实验都绑定数据与实现源码哈希；当前
> worktree 仍为 `dirty=true`，尚未形成不可变 Git tag/release。

## 0. 先给最终答案

当前代码已经不是一个只靠 LLM 阅读题目的查错脚本，而是一套具备以下能力的
benchmark audit 平台：

1. 自动扫描 benchmark package、推断 family、归一化 schema；
2. 为每个 item × checker 记录完整 coverage ledger，区分已检查、无 finding、
   不适用、abstain、unsupported、安全拒绝和运行失败；
3. 同时使用静态约束、差分执行、metamorphic/mutation、LLM 语义调查和附件证据；
4. 由中央 promotion 层重新验证证据，LLM 判断和自报哈希不能直接变成
   `confirmed`；
5. 输出 `confirmed / review / unknown`，且明确坚持“没有 finding 不等于 benchmark
   干净”。

但它还不能诚实声称“随便给一个 benchmark，就能自动找出全部问题”。真正可实现、
也更强的最终目标应写成：

> 给定一个尽可能完整的 benchmark package，系统自动建立可审计的 artifact 与
> coverage 地图；对有客观 oracle、可重放环境或闭世界证据的缺陷自动确认；对
> 语义风险生成高召回候选；对缺失的环境、真值或解析能力明确输出 UNKNOWN，而不
> 把未检查包装成 clean。

这不是降低目标。它把不可验证的“全知式召回”改成了可以测量的三个目标：

- 客观可确认集合中的 precision / recall；
- 语义候选的 root-cause recall 与 review budget；
- 所有未覆盖能力的 100% 可追责性。

## 1. 为什么“除了人工不足”仍然不能保证找出任意错误

人工不是唯一瓶颈。任意 benchmark 可能依赖：

- 没有提供的私有环境、API 状态、数据库或真实世界事实；
- 领域规范、法律时点、医学指南等外部 oracle；
- 任意程序的行为等价性和充分测试，通用情况下无法由有限测试证明；
- 图片布局、公式重算、GUI 状态和物理环境，而输入包中可能没有这些状态；
- 训练数据 provenance，闭源模型通常不会披露。

如果这些信息不在输入里，自动系统也不能凭空恢复。正确做法是把缺失信息转化为
机器可读的 `unsupported / security_blocked / unknown`，并给出需要补充的 artifact，
而不是继续投票直到模型“看起来确信”。

## 2. 我们对 benchmark 问题的统一理解

一个 agent/LLM benchmark 不只是“题目 + 答案”，而应建模为：

```text
B = (
  task specification,
  context / attachments,
  environment / tools / protocol,
  output contract,
  oracle / reference,
  evaluator / tests / rubrics,
  attempts / traces,
  provenance / version
)
```

最重要的两条有效性条件是：

```text
Task validity:
  具备目标能力的 agent，应该能够在可见信息和环境中完成任务。

Outcome validity:
  evaluator 接受，当且仅当任务真的完成。
```

Outcome validity 又分成两个方向：

- completeness 缺陷：正确或合理等价的解被拒绝，例如测试过严、格式钉死；
- soundness 缺陷：错误、不完整或投机的解仍通过，例如测试覆盖不足、广播比较、
  只检查“点击保存”而没检查状态真的改变。

因此 BenchAudit 的主线不是再加一个分类 prompt，而是：

```text
candidate discovery
  → grounding / root-cause attribution
  → independent replay or typed certificate
  → confirmed / review / unknown
```

## 3. 本轮代码到底改进了什么

### 3.1 Coverage：不再把空结果当 clean

`benchcore/coverage.py` 为每个计划检查记录以下终态：

- `completed_no_finding`
- `finding`
- `abstained`
- `unsupported`
- `operational_failed`
- `security_blocked`
- `ineligible`

每条记录带 `row_uid`。`row_uid` 绑定原始 source row index，并另存 source-row
SHA-256；它不会因 `offset`、`limit` 或 sample manifest 重排而改变。重复 `item_id`
不再被字典覆盖。`investigate`、forensic bundle 和 gold study 都必须使用有效
`row_uid + source hash` 联结，缺失时即使 item_id 唯一也 fail closed。

### 3.2 Promotion：报告自己说“执行过”不再算证明

`benchcore/promotion.py` 现在按 live item 或完整 live dataset 重新验证 proof tuple：

- arithmetic、contract、evaluator 与 executable evidence 从当前 item 重算；
- duplicate ID / conflicting oracle 从完整当前数据集重放；
- finding 的 item_id、row_uid、source hash 必须一致；
- Workspace 重放必须携带 checker 注入的 canonical trusted roots；
- execution driver 和 numeric adjudicator 仍在一个信任域时，结果最高只能是
  `review`。

这修复了一个关键的二阶问题：审计系统本身也可能被伪造 evidence 欺骗。

### 3.3 执行层：LLM 提议，执行裁决，但必须分离信任域

`benchcore/evaluator_execution.py` 已实现 gold replay、等价实现和行为变异体，并在
DS-1000 pilot 中发现两个经人工复核的真实 evaluator 盲点：timezone 核心属性未被
检查，以及 scalar/shape 因 broadcasting 被错误视为相等。

进一步对抗审查发现，旧 driver 与 comparator 同处一个 Python 解释器，恶意 harness
可以 monkeypatch comparator。因此当前代码刻意把这类 observation 降为 `review`；
只有将 benchmark harness 与独立 adjudicator 分到不同容器/进程、并验证完整
transcript 后，才应恢复自动确认。

表格 `CodeExecVerifier` 本轮也已关闭直接宿主 subprocess 的路径：

- 默认没有 runner 就 `security_blocked`；
- 推荐使用 digest-pinned、无网络、只读 workspace 的 container runner；
- 不安全本地运行需要两个显式确认开关，且 evidence ceiling 为 `review`；
- 缺依赖、代码生成失败和 timeout 分别进入 typed coverage，不再变成空 finding。

### 3.4 附件解析：安全失败与“空文件”分开

`benchcore/file_reader.py` 统一返回：

```text
ok / truncated / security_blocked / budget_exceeded /
unsupported / operational_failed / missing
```

主要边界包括：

- regular-file 检查、`O_NOFOLLOW`、稳定私有 snapshot 与流式 SHA-256；
- 原文件、ZIP member、总解压量、压缩比、页/Sheet/Slide、XML node、输出字符、
  时间、内存、CPU 和 PID 上限；
- DOCX/PPTX/XLSX 使用有界 OOXML 投影；
- PDF、旧 Office 和 OCR 没有隔离容器时默认安全拒绝；
- cache key 使用内容哈希、parser 版本、容器镜像和完整 limits，不依赖路径；
- prompt 被全局截断时，actor-view completeness 自动变为 false；
- citation 校验复用冻结内容哈希，不再二次无界读取或产生 TOCTOU。

OOXML 文本投影仍不等价于视觉布局、公式重算或完整 Office 渲染。这一点作为 coverage
上限保留，不作能力声称。

### 3.5 远程数据安全与可复现性

- 所有 LLM CLI 路径必须显式使用 `--allow-remote-data-egress`；
- run metadata 记录可能外发的 task、gold、rubric、附件内容等字段；
- container image 必须使用不可变 digest；
- 报告记录输入 SHA-256、source-row manifest、实现源码 manifest、模型与 prompt
  signature；
- Workspace 正式实验同时做 start/end source hash gate；源码在运行中发生变化，
  整轮结果直接作废。

## 4. WorkspaceBench 实验设计

Workspace-Bench 包含 388 个任务、7,399 条 rubrics、74 种文件类型和 20,476 个文件；
Lite 是 100 条子集。这里分别做了三类互补实验，而不是用一个 100% 数字概括全部
能力。[Workspace-Bench 论文](https://arxiv.org/abs/2605.03596)

### 4.1 实验 A：全量结构不变量 challenge

对每个真实 source item 注入五类原子缺陷：

1. manifest unresolved；
2. dangling dependency；
3. output contract filename conflict；
4. raw evaluator 与 rubric divergence；
5. rubric_types cardinality mismatch。

clean 与 mutant 分开审计，mutation provenance 只在 sidecar，所有 planned pair 都进入
分母。

| 数据 | 源任务 | Pair | Exact recall | Paired discrimination | Source 全五类通过 | 额外/重复 alarm |
|---|---:|---:|---:|---:|---:|---:|
| Full 388 | 388 | 1,940 | 1,940/1,940 = 1.000 | 1,940/1,940 = 1.000 | 388/388 | 0 / 0 |
| Lite 100 | 100 | 500 | 500/500 = 1.000 | 500/500 = 1.000 | 100/100 | 0 / 0 |

按 pair 计算，Full 的 exact/paired 95% Wilson 区间为 `[0.9980, 1.000]`，Lite 为
`[0.9924, 1.000]`。同一 source 的五个 pair 相关，因此更保守的 source-level
“五类全通过”区间分别是 Full `[0.9902, 1.000]`、Lite `[0.9630, 1.000]`。Full 的
388 条 unmutated side 没有 natural alarm。Lite 有 1 条 unmutated natural alarm：
task 388 中一个文件的名称/正文命中“疑似输出生成脚本”启发式；隐藏 oracle 等价性和
score impact 均未证明。它不是注入 target 的额外 alarm，因此不能称为 synthetic
false positive，也不能直接称作已确认真实缺陷。

产物：

- `reports/workspace_invariant_experiment_full388_20260714_release/summary.md`
- `reports/workspace_invariant_experiment_lite100_20260714_release/summary.md`

边界：注入器与检测器围绕同一组已知 schema/artifact invariant 共同设计，因此这个
实验是 conformance/regression test，只证明五类 operator 没有漏检或成对混淆；它不
估计自然数据缺陷率、held-out root-cause recall，也不测附件正文语义。

### 4.2 实验 B：200 对语义 grounding challenge

从 Lite 稳定抽样 50 个真实任务，每个任务构造四类 clean/mutant 对：

1. task 明示标题 vs 隐藏标题；
2. contract 要求文件 vs 未要求 companion file；
3. 正确输入文件数 vs 错误数字；
4. 真实可见 filename vs 不存在 filename。

每次请求只有一个 rubric；模型看不到 pair/operator/expected label。机器证书只读取
生产可见的 canonical task、output contract 和完整 input inventory，不读取实验
sidecar。

| 判定层 | Mutant recall | Clean FP | Paired | Strict paired | Uncertain |
|---|---:|---:|---:|---:|---:|
| Raw LLM | 200/200 = 1.000 | 34/200 = 0.170 | 166/200 = 0.830 | 166/200 = 0.830 | 0/400 |
| Citation-grounded，不含证书 | 114/200 = 0.570 | 10/200 = 0.050 | 108/200 = 0.540 | 79/200 = 0.395 | 137/400 |
| Objective certificate | 200/200 = 1.000 | 0/200 | 200/200 = 1.000 | 200/200 = 1.000 | 0/400 |
| Certificate-aware controlled decision | 200/200 = 1.000 | 0/200 | 200/200 = 1.000 | 200/200 = 1.000 | 0/400 |

关键 95% Wilson 区间：

- raw paired：`[0.772, 0.876]`；
- grounded paired：`[0.471, 0.608]`；
- grounded strict：`[0.330, 0.464]`；
- certificate-aware paired：`[0.981, 1.000]`；
- certificate-aware clean FP 上界：`0.0189`。

四个 operator 来自同一批 50 个 source task，200 个 pair 不是完全独立样本。按
source cluster 重采样保留同一任务的四行，raw paired 的 95% bootstrap 区间约为
`[0.775, 0.880]`，grounded paired 为 `[0.480, 0.600]`，grounded strict 为
`[0.335, 0.455]`。更严格的“一个 source 的四类全部成功”统计为：raw 25/50、
grounded 0/50、certificate-aware 50/50；最后一项的 source-level Wilson 区间为
`[0.929, 1.000]`。这比只把 200 个 pair 当独立样本更诚实。

分 operator 的 raw / grounded / certificate paired：

| Operator | Raw | Grounded | Certificate-aware |
|---|---:|---:|---:|
| companion file | 1.000 | 0.640 | 1.000 |
| input file count | 0.780 | 0.780 | 1.000 |
| visible/nonexistent filename | 0.720 | 0.100 | 1.000 |
| explicit/hidden title | 0.820 | 0.640 | 1.000 |

这组数字的研究意义不是“LLM 达到 100%”，恰恰相反：

- raw LLM 会把 17% 的 clean 误判为 unsupported；
- 自由文本引用绑定把误报降到 5%，但大量样本变为 uncertain，paired 只有 54%；
- negative proof 最难，因为“不存在的字符串”无法被引用；
- 闭世界证书可以表达 `complete_inventory ∧ target ∉ inventory`，因此对这四类窄
  语法给出可重算结论。

这里还有一个必须公开的限制：challenge generator 与 resolver 是共同设计的，resolver
用四个 `re.fullmatch` 原子语法解析 generator 生成的 rubric。证书不读取 sidecar、
operator 或 expected label，这能防止标签泄漏；但它仍是**已知窄语法的证书
conformance**，不是对自然语言改写、未见谓词或自然 Workspace rubric 的独立泛化
实验。`Objective certificate` 与下一行的 certificate-aware decision 也走同一条决策
路径，不能把两行当成两个独立系统互相验证。

覆盖情况：50 个任务、326 个附件；input inventory 50/50 完整，但 actor content
view 只有 24/50 完整，另有 26 个 parser-failure 文件、147 个 partial 文件和 6 个
bundle-truncated task。因此 200/200 只能推广到 task/contract/inventory 的四类原子
谓词，绝不能写成“附件内容查错 100%”。

正式结果：

- `reports/workspace_semantic_challenge_lite100_20260714_v3_final/summary.md`
- `reports/workspace_semantic_challenge_lite100_20260714_v3_final/ANALYSIS_zh.md`
- `reports/workspace_semantic_challenge_lite100_20260714_v3_final/source_hash_end_check.json`
- `reports/workspace_semantic_challenge_lite100_20260714_v3_final/exact_cache_reuse_validation.json`

### 4.3 为什么有两轮结果被作废

这是本项目可信度的重要组成部分：

- `..._v3/`：parser evidence 曾并发构建，objective resolver 与三层指标尚未冻结；
  mutant 未启动，目录含 `RUN_INVALIDATED.md`；
- `..._v3_invalid_source_drift/`：400 个 response 全完成、运行无 API failure，但实验中
  `loader.py/schema.py` 被并发更新，implementation end hash 不一致，因此整轮不计分。

付费轮共 400 个逻辑请求、402 个成功 HTTP response（2 次 JSON retry），合计
1,517,358 tokens。当前审计实现按精确源码 manifest 冻结后生成了新的 run/phase
signature，并逐条验证完整 request key：clean/mutant 各 200 个 cache hit，HTTP 为
0；随后重新构建证据、重新评分，source end-check 与 exact-cache validation 均通过。
缓存复用不是新实验样本，只是对相同确定性请求复用已记录响应；源码 manifest 冻结也
不等于已经创建 Git release/tag。

### 4.4 实验 C：未修改 Workspace 数据的自然静态审计

| 数据 | Package plan（方法） | Selected-checker ledger | 自动 confirmed | Review signal |
|---|---:|---:|---:|---:|
| Lite CN 100 | 8 executed / 5 ineligible / 7 skipped / 5 unsupported | 800 completed / 500 ineligible | 0 | 1 |
| Full 388 | 8 executed / 5 ineligible / 7 skipped / 5 unsupported | 3,104 completed / 1,940 ineligible | 0 | 2 |

Lite 的 1 条 signal 是 task 388 中“疑似输出生成脚本”与 agent/evaluator 视图中的
文件字节相同。runner visibility 已在线重验，但 `oracle_equivalence_proven=false`、
`score_impact_proven=false`，因此中央 promotion 正确保持 `review`。

Full 的 2 条 signal 是 `current version / latest version` 触发的 temporal-scope 规则。
这些措辞也可能由冻结 workspace 内的文件版本充分定义，因此同样只应当作 review
候选，不是 defect ground truth。

产物：

- `reports/workspace_static_final_20260714/lite_cn_100_runner_verified_online_release.md`
- `reports/workspace_static_final_20260714/full388_release.md`

selected-checker ledger 中 `unknown=0` 只表示已选中的八种方法没有运行失败或安全
拒绝；它不能覆盖 plan 中 7 个 skipped 和 5 个 unsupported 方法。自然静态审计的
正确结论是“在当前已执行能力内没有自动确认缺陷，产生 3 个可解释候选，并明确保留
未实现能力”，不能写成“Full 388 全部干净”或“找到了 3 个真缺陷”。

还要避免把两个 Lite 口径混为一谈：结构/语义实验使用
`datasets/workspacebench/lite_100.jsonl`（SHA-256 前缀 `fe59c596...`），自然审计使用
`lite_cn_100_pinned.jsonl`（前缀 `89be51be...`）。它们都来自 Lite，但本地行表示和
实验用途不同，不能把三组 finding 逐行直接相加。

## 5. Claude / Codex 审阅版本到底算什么

仓库已有以下历史双模型审阅：

- `reports/workspace_lite100_v17_claude_vs_codex_analysis_20260710.md`：217 个候选，
  keep/delete/review 一致 213/217（98.2%）；Claude 分为 27 true、114 borderline、
  10 review、66 false positive；
- `reports/workspace_full388_v17_B_claude_vs_codex_analysis_zh_20260710.md`：122 个
  author-priority 候选，Claude 判 92 true、25 review、5 borderline；但只有 24/122
  在本地重新打开 source 后可直接验证，其余是对同一 investigator evidence 的第二次
  阅读；
- `reports/workspace_full388_v19_claude_assessment_zh_20260710.md`：复核 10 条
  likely-true，5 true、5 borderline，并发现 3/3 investigators 也可能一致归因错误。

所以答案是：有 Claude 与 Codex 的标注审阅版本，但它们是 model-model adjudication，
不是 human gold、author confirmation 或独立 ground truth。98.2% agreement 只能说明
两个审阅流程结论相似，不能估计真实 precision。当前 v3 受控 challenge 不依赖这些
标签，因为它的 sidecar truth 由确定性 intervention 和生产可见证据生成。

## 6. 与 2025–2026 最新研究的对应关系

### OpenAI：真实 pipeline 需要 attempts、trace 和环境

OpenAI 对 SWE-Bench Pro 731 条 public tasks 的 pipeline 标出 200 条（27.4%），五名
工程师的人类 campaign 标出 249 条（34.1%）；类别重合 74%，而 low-coverage tests
在人类标签中为 9.4%、agent pipeline 中仅 4.1%。这说明仅审 task/test 文本会漏掉
低覆盖，必须结合多模型 attempts、failure traces、repo 与真实执行环境。
[OpenAI：Separating signal from noise in coding evaluations](https://openai.com/index/separating-signal-from-noise-coding-evaluations/)

OpenAI 此前对 SWE-bench Verified 的 138 个困难任务审计发现至少 59.4% 有实质问题，
同时指出 contamination 会让分数失去能力解释。
[OpenAI：Why SWE-bench Verified no longer measures frontier coding capabilities](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)

### Task Verification Bench：必须评 root cause，不只评 verdict

TVB 报告，简单的 broken/not-broken verdict recall 可能把真实性能夸大最多 54 个百分
点；强基线的 root-cause-matched recall 仍约 35%–60%，基础设施层尤其困难。这支持
BenchAudit 采用 exact proof tuple、root-cause operator 和 planned denominator。
[Task Verification Bench](https://openreview.net/pdf?id=QdDcI0Ftvo)

### ABA / BenchGuard：跨 artifact 审计可规模化，但仍需外部确认

ABA 审计 9 个领域共 168 个 benchmarks，报告超过 25.7% 的被审任务存在问题；过滤
问题项后，SWE-bench Verified 与 Terminal-Bench 2 的平均性能分别变化 9.9% 与
9.6%。[ABA](https://arxiv.org/abs/2605.26079)

BenchGuard 在 ScienceAgentBench 找到 12 个 author-confirmed issue，并在
BIXBench Verified-50 匹配 83.3% 的专家问题；它也强调联看 task、environment、
reference、grader 与 traces。[BenchGuard](https://arxiv.org/abs/2604.24955)

### STING：错误解仍通过必须靠 mutation 与增量测试

STING 在 SWE-bench Verified 中发现 77% 的任务至少有一个 surviving variant，生成
1,014 个验证测试，增强后 top-10 agent resolved rate 下降 4.2–9.0 个百分点。这与
BenchAudit 的 minimal-wrong-solution / kill matrix 路线一致。
[STING](https://arxiv.org/abs/2604.01518)

### RuVerBench：LLM judge 不是稳定 oracle

RuVerBench 提供 2,458 个 human-labeled rubric 实例；论文发现 frontier judge 仍有
明显噪声，batching 存在精度/成本权衡，majority vote 收益递减。这解释了为什么本
项目不允许多模型同意直接进入 confirmed。
[RuVerBench](https://arxiv.org/abs/2606.29920)

### ABC 与 evidence-supported bounds：UNKNOWN 应进入最终分数解释

Agentic Benchmark Checklist 把问题分为 task validity、outcome validity 和 reporting；
其案例显示 benchmark 问题可导致相对误差达到 100%，在 CVE-Bench 修正中性能高估
下降 33%。[ABC / NeurIPS 2025](https://arxiv.org/abs/2507.02825)

2026 年的 evidence-supported bounds 进一步主张将每次 outcome 标为 Evidence Pass、
Evidence Fail 或 Unknown，并报告分数上下界，而不是把 unknown 隐藏在单点分数中。
[Evidence-Supported Bounds](https://arxiv.org/abs/2605.10448)

### 无人工标签时还能用什么

- IRT/model panel 可作为 mislabel 排序信号；一项 114-model 研究在七个选择/偏好
  benchmark 的 top-200 达到 95% precision，但它仍是统计筛选，不是逐项证明。
  [IRT auditing](https://arxiv.org/abs/2605.30504)
- contamination 统计检测在 distribution shift 和小 benchmark 上会误报或失去
  检验力，不能替代透明 provenance。
  [Reliability Gap](https://arxiv.org/abs/2606.03305)

## 7. 距离“接近最终版本”还差哪些能力

### P0：不完成就不能声称通用自动审计

| 缺口 | 当前状态 | 要实现的 release gate |
|---|---|---|
| Family adapter / harness SDK | 自动识别 generic、Workspace、SWE、Terminal，但复杂 family 仍需专用代码 | 新 benchmark 能声明 artifact、环境、oracle、runner、semantic contract；未知 family 自动 UNKNOWN |
| 独立 execution adjudicator | driver 与裁决器尚未完全分离，因此 execution 最高 review | harness 容器、adjudicator 容器和只读 transcript 三方隔离；恶意 monkeypatch 测试通过 |
| Attempt / trace ingestion | 尚未成为统一 canonical artifact | 多模型 attempt 聚类到 assertion/environment/root cause，并在 held-out TVB 上测 root-cause recall |
| 自然缺陷 meta-benchmark | 当前强结果主要来自受控 intervention | 在 TVB、benchmark revision diff 或 author-acknowledged issue 上报告 held-out root-cause P/R/F1 |
| 多模态与真实 Office 语义 | OOXML 主要是文本投影，PDF/旧 Office/OCR 需容器 | digest-pinned parser、页/图/公式/布局 coverage；截断与缺依赖保持 UNKNOWN |
| Outcome score bounds / ranking impact | 已有 ranking-impact 基础模块，但未对 Workspace 给出有效性修正分数 | confirmed / unknown 对最终模型分数和排名的上下界、bootstrap 与 rank stability |
| Provenance / contamination | 有 source/version/hash 和字面 leak，缺训练集级证据 | 时间切分、近重复、历史 source、canary；统计信号只能 review |

### P1：显著提高 recall 与扩展效率

1. 将自然语言 contract 编译为 typed predicate IR；
2. 让 LLM 选择 evidence node ID / stable span，而不是自由生成 quote；
3. 实现 `closed_world(scope) + membership/non-membership` 等通用证书组合；
4. 生成 behavior-preserving alternative solutions 与 minimal wrong solutions；
5. 以 mutation kill matrix、coverage delta、property tests 评 evaluator；
6. 使用 model response matrix / IRT 排序难以程序化的错标候选；
7. 实现 adapter conformance suite、分布式内容缓存和成本预算。

## 8. 建议的统一 release gates

不应再用单个 candidate F1 判断“接近最终”。建议每次 release 同时满足：

1. **Coverage accountability**：package plan 中 selected / skipped / unsupported 全部
   可追责，且 100% selected item × checker 都有 terminal ledger；
2. **Confirmed precision**：在独立自然 gold 上报告 Wilson 下界，而不只报点估计；
3. **Root-cause recall**：在 held-out benchmark revisions / TVB 上 exact 或语义根因匹配；
4. **Paired specificity**：clean/mutant 成对实验同时测 recall 与 clean FP；
5. **Abstention quality**：unsupported artifact 不得升级为 clean/confirmed；
6. **Reproducibility**：至少三次 fresh preflight 的数据、证据和实现签名一致；
7. **Security**：路径逃逸、ZIP bomb、prompt egress、恶意 harness、伪造 payload、重复 ID
   adversarial suite 全通过；
8. **Environment replay**：镜像 digest、依赖、seed、网络、fixture、runner 版本完整记录；
9. **Score impact**：修复/过滤缺陷前后的分数区间与排名变化可重放；
10. **Claim audit**：synthetic、silver、model-review、human-gold、author-confirmed 严格分栏。

## 9. 下一轮最值得做的三件事

### 第一优先：独立执行 adjudicator

把 DS-1000 与通用 harness 的执行结果升级为可确认，需要：

```text
untrusted benchmark/harness container
  → signed input/output transcript
  → separate trusted comparator container
  → replayable proof bundle
```

验收标准不是“又发现几个 case”，而是恶意 harness 无法修改 comparator、fixture 或
最终 proof，并在 injected soundness/completeness defects 上报告 paired metrics。

### 第二优先：接入 TVB / benchmark revision gold

受控 mutation 适合回归，但论文需要自然 root cause。优先将 TVB 或公开 benchmark
修订前后 diff 转成统一 truth schema，严格区分 verdict 与 root-cause recall。

### 第三优先：trace + attempt clustering

引入多模型 attempts、失败 assertion、环境 setup 日志和通过轨迹。聚类后生成：

- common failure locus；
- correct-looking alternative rejected；
- incomplete solution passed；
- environment-only failure；
- prompt/test contradiction。

这是当前代码与 OpenAI SWE-Bench Pro pipeline 之间最大的能力差距。

## 10. 可以对外说什么，不能说什么

### 可以说

> BenchAudit 将 benchmark 查错拆为候选发现、证据 grounding 和客观确认，并用
> coverage ledger 显式记录未知范围。在 Workspace-Bench 的 1,940 个结构缺陷对和
> 200 个共同设计的语义证书对上，版本化规则/证书均实现 100% paired
> discrimination；
> 语义实验同时显示 raw LLM paired 仅 83%，citation-grounded paired 仅 54%，说明
> 结构化证据接口而非单纯模型投票是关键。本系统对自然数据保持保守：Full/Lite
> 静态审计只产生 review candidates，没有把可见性或时间措辞自动确认为缺陷。

### 不能说

- “WorkspaceBench 已经 100% 查完，所有问题都找到了”；
- “200/200 证明任意 benchmark recall 为 100%”；
- “Claude/Codex agreement 是人工 ground truth”；
- “没有 finding 的 385/388 条就是 clean”；
- “执行发现已经自动 confirmed”；
- “附件正文语义覆盖 100%”。

## 11. 当前工程验证与复现

本轮最终全套测试：

```text
355 passed in 13.33s
```

核心复现命令：

```bash
# Workspace Full 结构 challenge
python scripts/run_workspace_invariant_experiment.py \
  --suite full388 --workers 8 --strict \
  --out-dir reports/workspace_invariant_experiment_full388_20260714_release

# Workspace 语义 challenge；需要显式可信附件根和 API 成本授权
python scripts/run_workspace_semantic_challenge.py \
  --suite lite100 --sample-size 50 \
  --allow-input-root /trusted/workspace-cache \
  --phase both --execute-api --workers 8 --strict \
  --out-dir reports/workspace_semantic_challenge_lite100_20260714_v3_final

# 未修改 Full 的静态审计
python -m benchcore.cli audit datasets/workspacebench/full.jsonl \
  --profile auto --allow-input-root /trusted/workspace-cache \
  --workers 8 --out reports/workspace_static.json \
  --md reports/workspace_static.md
```

复现时不要复用本机绝对 cache 路径；应传入自己的 trusted root。若源码、dataset、
附件、prompt、model config 或 evidence signature 变化，必须使用新目录和新 run
signature，不得与旧 decision 混合。

当前实验虽有逐文件 implementation manifest、数据哈希和 end gate，但 Git 记录仍是
`dirty=true`。正式论文/对外 release 前必须提交这些改动、建立不可变 tag，并从该 tag
重新执行或验证所有报告；“精确源码 manifest 可复现”和“已有正式 release”不是一回事。

## 12. 一分钟讲清楚这个项目

> 现在很多 benchmark 的低分不一定是模型能力差，也可能是题面缺条件、gold 错、
> 测试过严、测试覆盖不足、环境不稳定或评分器只检查了表面信号。BenchAudit 先把
> task、附件、环境、输出合同、oracle、evaluator、trace 和 provenance 统一起来，
> 再用静态规则、差分执行、mutation 和 LLM 调查找候选。最关键的是，LLM 只负责
> 提议；只有可重放执行或版本化机器证书能自动确认，证据不足就明确返回 review 或
> UNKNOWN。Workspace 实验说明裸 LLM 能看到很多问题，但误报和 evidence binding
> 都很明显；结构化闭世界证书能可靠解决其中可形式化的一部分。下一步是把独立执行
> adjudicator、attempt/trace 聚类和自然 root-cause meta-benchmark 接进来，从“针对
> 几个数据集的查错器”走向“任意 benchmark 的可审计 QA 平台”。
