# P1：Evaluator 缺陷注入算子的协议无关化设计说明

> 日期：2026-08-02
>
> 状态：设计说明；未实现、未运行、未预测结果
>
> 证据边界：现有 DS-1000 实验报告的是 shared-driver `review` 候选敏感度，不是 confirmation recall。可信裁决器 V1 当前结论为 `NOT_IDENTIFIABLE_TRUSTED_ADJUDICATOR`，因此本说明不能授权把既有数字改称 confirmed。

## 0. 目标与非目标

目标是把当前位于 `scripts/run_ds1000_defect_injection.py` 的三种 evaluator 缺陷，从“对一个 Python harness 做字符串替换”分解成：

1. 协议无关的缺陷语义；
2. 协议相关的注入适配；
3. 可机械验证的注入激活证书；
4. 与 execution observation / proof contract 对齐的检测结果；
5. 至少三个执行协议上的 `protocol × defect class` 矩阵。

矩阵的最终目标是 confirmation recall，但只有在独立可信裁决路径已经可用时才能使用这个名称。在此之前，同一实验最多报告 `review-candidate sensitivity`。

本说明不做以下事情：

- 不把 DS-1000 字符串替换函数直接搬进 `benchcore`；
- 不增加生产接口；
- 不实现新的确认路径；
- 不以“所有结果都弃权”取得零 FP；
- 不把 LLM 生成 probe 当作注入真值；
- 不预测任一协议上的召回率。

## 1. 现有三个算子的真实可迁移边界

### 1.1 `neutralize_comparator`

#### 协议无关的部分

它表达的缺陷类是：

> evaluator 的判别逻辑被替换为常量接受，导致至少一个由合法 canonical 对照可区分的错误输出被接受。

“判别逻辑常量化”不依赖 DS-1000。函数调用、stdin/stdout、SQL 结果、文件产物和 CLI evaluator 都可能出现 accept-all 或绕过 comparator 的缺陷。

#### DS-1000 专用的部分

当前实现搜索：

```python
def exec_test(...):
```

并在函数体首行插入 `return 1`。以下假设均为 DS-1000/Python harness 形态，而非缺陷语义：

- evaluator 是 Python 源码；
- 比较入口叫 `exec_test`；
- truthy 整数表示接受；
- 在函数首行返回不会破坏 runner 协议；
- 字符串替换只改到一个目标入口。

#### 上移结论

可上移的是 `constant_acceptance` 缺陷类、激活条件和验证关系；不能上移的是查找 `exec_test` 的正则和 Python 源码补丁。

### 1.2 `reject_gold`

#### 协议无关的部分

它表达的缺陷类是：

> evaluator 拒绝自身声明的 canonical/reference 行为。

这是三个算子中语义最强、最协议无关的一类。只要协议能物化官方 reference，并能获得 evaluator verdict，就可以构造 canonical self-consistency 控制。

#### DS-1000 专用的部分

当前实现把源码中的第一个 `assert exec_test` 替换成 `assert not exec_test`。它依赖：

- Python `assert` 作为 verdict 路径；
- 特定源码字面量；
- 对第一次命中的字符串替换能精确代表“反转 gold verdict”；
- assertion failure 与 evaluator 拒绝具有相同 operational semantics。

在 stdin/stdout 协议中，等价注入可能是反转 checker exit status；在 SQL 协议中可能是反转结果关系；在文件 evaluator 中可能是把 valid predicate 取反。不能共用当前补丁器。

#### 上移结论

`canonical_rejection` 的 proof obligation 可以上移；注入方式必须由协议适配器产生并证明只改变 verdict 极性。

### 1.3 `implementation_assert`

#### 可泛化的缺陷语义

它表达的缺陷类是：

> evaluator 强制某个与声明输出语义无关、只与参考实现路径相关的性质，从而拒绝一个语义合法但实现不同的结果。

此类缺陷不仅存在于 DS-1000：代码任务可钉 API/token/AST 形状，SQL 可钉查询写法，文件任务可钉生成工具元数据，CLI 可钉日志或命令序列。

#### DS-1000 专用且不充分的当前实现

当前 `gold_token()` 从 reference 源码选择首个匹配的调用、属性或长单词，然后在 `test_execution` 中断言 token 出现在 solution 字符串里。它同时依赖：

- 被测对象有可读源码；
- evaluator 能读取源码字符串；
- 函数叫 `test_execution`；
- token 出现与否可代表实现路径；
- 至少一个合法替代实现不含该 token。

最后一条并不总成立，也是现有 13/20 敏感度的机制性解释：若 token 是所有合理等价实现都会采用的自然写法，注入虽然存在，却没有被现有对照集区分。此时不能把“未检出”简单解释成 checker 漏检；也可能是注入没有对该 item 形成一个可观察的 overstrictness 见证。

#### 上移结论

可上移的是 `implementation_coupling` 缺陷类和“必须存在不满足实现谓词的合法替代实现”这一激活证书。自然 token 选择器本身不能作为通用算子。

## 2. 最小协议无关抽象

### 2.1 不先造一个全能接口

只有一个 DS-1000 实现时，不应在 `benchcore` 中提前固化抽象。建议先让三个协议适配器各自产出同一份数据记录，待重复结构被实际验证后再提取 Protocol/ABC。

需要稳定的是记录语义，而非注入技术：

```text
InjectionPlan
  operator_id / operator_version
  defect_class
  protocol_family
  target_artifact_sha256
  mutation_patch_sha256
  expected_relation
  applicability_reason
  preconditions

InjectionActivationReceipt
  canonical_control_completed
  canonical_control_accepted
  injected_control_completed
  injected_control_relation
  distinguishing_witness_ids
  operational_failures
  activated

DetectionObservation
  finding_method / evidence_level / defect_type
  review_only / confirmation_eligible
  replay identifiers and artifact hashes
```

`InjectionPlan` 说明改了什么；`ActivationReceipt` 证明这个改动在当前 item 上确实制造了预注册缺陷，而不是只改了文本；`DetectionObservation` 才衡量 BenchAudit 是否发现它。三者不得合并成一个由 runner 自填的“命中”字段。

### 2.2 复用 `execution.py`

现有 `ExecutionPolicy`、`CommandSpec`、`RunResult` 和 `ContainerRunner` 已经覆盖：

- digest-pinned 容器外围调用；
- 禁网、只读 workspace、non-root、能力删除；
- timeout、内存、CPU、进程和输出上限；
- 退出码、stdout、stderr 与 operational timeout 的分离。

通用注入不应重写执行后端。协议适配器只负责把原 evaluator 和 injected evaluator 物化为两个冻结 workspace/command，并将二者交给同一个 runner 和同一策略。

### 2.3 复用 `evaluator_execution.py`

应复用的不是 DS-1000 `DRIVER` 字符串，而是它已经建立的证据关系：

- canonical control 必须先通过；
- instrumentation 不得改变 canonical verdict；
- probe/candidate 只负责制造可执行对照；
- timeout/error 与语义 verdict 分开；
- code context、reference、probe、driver、输入物化和观察结果都带 hash；
- LLM 只生成 probe，不授予判断。

未来可把这些关系收敛为 protocol-neutral replay record，但只有 stdin/stdout、函数调用、文件/查询三个适配器都产出真实记录后才提接口。

### 2.4 协议适配层的最低职责

每个协议适配器必须机械提供：

1. evaluator artifact 的不可变标识；
2. operator 的 applicability 判断；
3. 一个确定性、最小、单一语义改动；
4. canonical/reference 的物化方式；
5. 一个能激活缺陷的区分见证或明确 `NOT_APPLICABLE`；
6. evaluator verdict 的结构化读取；
7. operational failure 与 semantic rejection 的区分；
8. 注入前后 artifact diff/hash；
9. 相同资源、环境和输入预算；
10. 对等的 clean/sham 控制。

适配器不得自己声称 confirmed；它只产生注入与执行 observation。

## 3. 三协议候选矩阵

以下协议族用于检验抽象是否真实重复，而不是立即授权实现。

| 协议族 | `constant_acceptance` | `canonical_rejection` | `implementation_coupling` |
|---|---|---|---|
| Python 函数/内存对象（DS-1000） | 替换 comparator 入口，但当前 observation trust 未解决 | 反转或包裹 canonical verdict | 源码 token/AST/API 约束；须有无该性质的合法等价实现 |
| stdin/stdout 测试协议（如 APPS 类） | checker/wrapper 对所有输出返回接受 | 对官方 canonical 输出反转 verdict | 约束源代码 token、语言构造或非语义 stdout；仅在任务未授权时适用 |
| 文件/查询/结构化产物协议 | 文件 validator 常量接受，或结果 comparator 绕过 | 官方 reference artifact/query result 被拒 | 钉生成工具、内部 metadata、列顺序或实现痕迹；若规范明确要求则不适用 |

这里的第三列最容易误用。若 benchmark 本来就测“必须使用某 API/算法/格式”，实现约束是规范的一部分，不是 defect。必须由冻结 task/contract mapping 判定其未被授权。

## 4. 合法对照集与非退化验收

### 4.1 分母不是“所有题”

每个矩阵单元的 confirmation recall 分母必须是：

> 通过全部 eligibility、canonical、single-edit 和 activation gates 的注入实例。

不得把语法不适用、canonical 本来失败、注入未改变行为、对照不存在、运行超时或 observation 不可信的实例计入分母。它们分别报告为 `NOT_APPLICABLE`、`CONTROL_INVALID`、`NOT_ACTIVATED`、`OPERATIONAL_UNKNOWN` 或 `TRUST_NOT_IDENTIFIABLE`。

### 4.2 每个注入实例的四个必要对照

1. **Pristine control**：原 evaluator 接受官方 canonical/reference，且没有该 injected defect 的 finding。
2. **Sham-edit control**：应用同规模但语义无关的确定性编辑，行为保持一致；防止检测器只识别“文件变了”。
3. **Activation control**：injected evaluator 对预注册区分见证表现出预期错误关系。
4. **Clean alternative control**：至少一个不带缺陷的 evaluator 或合法输出通过，防止系统靠拒绝所有东西获得表面零 FP。

任一必要对照缺失，该实例不得进入 confirmation-recall 分母。

### 4.3 各算子的激活证书

#### Constant acceptance

激活要求同时存在：

- canonical 仍被接受；
- 至少一个机械证明违反目标关系的 candidate 被 injected evaluator 接受；
- pristine evaluator 对该 candidate 的 verdict 与 injected evaluator 不同；
- 差异不是 timeout/error/解析失败。

若没有可信的“candidate 违反关系”证明，只能记 review sensitivity，不能成为 confirmed 分母。

#### Canonical rejection

激活要求：

- pristine evaluator 接受同一官方 canonical；
- injected evaluator 完成执行并拒绝它；
- 输入、canonical bytes/code 和非目标环境完全相同；
- 注入 receipt 证明只改变 verdict 极性或等价的单一判定路径。

这类激活不依赖 LLM 产生替代解，最适合作为跨协议基础控制。

#### Implementation coupling

激活要求：

- task/contract 未授权该实现谓词；
- canonical 满足该谓词；
- 至少一个机械或独立证明语义合法的替代实现不满足该谓词；
- pristine evaluator 接受该替代实现；
- injected evaluator 仅因该谓词拒绝同一替代实现。

若替代实现也自然包含 token，或其语义等价性只有 LLM 自述，注入未得到 activation certificate，不进入分母。

### 4.4 防止“零 confirmed FP 靠什么都不 confirm”

矩阵必须并列报告：

- eligible injections；
- activated injections；
- trusted-observation eligible；
- confirmed TP；
- review-only detection；
- confirmed FP；
- clean controls correctly left clean；
- operational unknown；
- not applicable；
- trust not identifiable。

放行不能只要求 `confirmed FP = 0`，还必须要求：

1. 每个被评价矩阵单元至少有预注册数量的 activated injection；
2. positive controls 能到达 confirmation 路径；
3. clean 和 sham controls 保持 clean；
4. confirmation recall 在明确分母上报告；
5. 所有未确认实例都有互斥 reason code。

若 trusted positive path 不可达，正确结论是 `NOT_IDENTIFIABLE_CONFIRMATION_MATRIX`，而不是“precision 100%”。

## 5. `implementation_assert` 漏检机制的跨协议分析

### 5.1 现有 65% 敏感度测量了什么

历史 13/20 表示：在当时的 clean DS-1000 对照与已缓存 probe 集合上，13 个注入产生了目标 review finding。它不是“算子有 65% 缺陷制造成功率”，也不是 confirmation recall。

当前 token 选择偏向 reference 中第一个自然语法片段。若这个片段是任务域的惯用、唯一或几乎唯一写法，等价 probes 仍包含 token，overstrict evaluator 就不会拒绝它们。因此漏检可能来自三处：

- 没有真正不同的合法替代实现；
- probe generator 没覆盖无 token 的替代实现；
- token 本身不区分实现路径。

### 5.2 该机制会跨协议存在

会，但强弱取决于实现表示是否丰富：

- **源码协议**：API、AST 节点和库调用很容易成为自然共有词，问题直接存在。
- **SQL**：`JOIN`、聚合函数、目标表名等可能是所有合法查询共有，文本 token 同样不具判别力。
- **CLI/shell**：某命令或 flag 可能由任务规范要求，不能作为未授权实现约束。
- **文件产物**：生成器 metadata 或压缩器标签可能是工具默认值；有时所有合法文件都相同，有时与内容语义无关。
- **二进制或远端 API**：若实现本身不可观察，算子直接 `NOT_APPLICABLE`，不应为覆盖率而造一个代理 token。

所以一般问题不是“怎样挑更好的关键词”，而是：

> 是否能在注入前证明该实现谓词把两个语义等价、规范允许的实现区分开。

### 5.3 两种不同的实验应分开

1. **受控 sentinel coupling**：在 canonical 实现中加入语义无影响、唯一且预注册的 sentinel，再让 evaluator 强制 sentinel。它能验证 detection/proof plumbing，但人为性强，只是系统控制。
2. **自然 implementation coupling**：从真实 reference 提取实现谓词，但只有在独立合法替代实现不满足它时才激活。它更接近真实缺陷，但分母更小。

二者不得合并报告。前者回答“通道能否检出已知 overconstraint”，后者回答“真实实现耦合能否被发现”。

## 6. 建议的实施顺序（待后续协议冻结）

1. 先为三个协议各选一小组冻结 pristine items，确认数据、canonical、evaluator 和运行环境可得。
2. 在看检测结果前冻结每个 operator 的适用条件、single-edit 规则、激活证书和 reason code。
3. 先实现协议适配器和 activation receipt，不接 checker。
4. 用 pristine/sham/activation/clean-alternative 四类控制验证注入是真实、非退化的。
5. 三个协议都产出同构记录后，才把重复的数据类型上移到 `benchcore`。
6. 接入现有 checker，只测 review-candidate sensitivity。
7. 可信 adjudication 路径另行通过后，原样冻结同一批注入，再测 confirmation recall；不得事后改分母。
8. 输出完整矩阵和逐实例 receipt，保留 `NOT_APPLICABLE`、`NOT_ACTIVATED`、`OPERATIONAL_UNKNOWN` 与 `TRUST_NOT_IDENTIFIABLE`。

## 7. 研究价值与停止条件

真正的新指标不是“我们注入了多少 bug”，而是：

> 在每一种执行协议和 evaluator 缺陷类上，有多少机械激活的缺陷具备可确认机会，其中多少被可重放 proof contract 确认，且合法对照的 confirmed FP 为零。

停止条件包括：

- 三个协议无法形成同构 activation record，说明抽象过早；
- 合法替代实现无法机械验证，`implementation_coupling` 只能停在 review；
- trusted positive path 不可达，不得报告 confirmation recall；
- clean/sham control 出现 confirmed FP；
- operator 需要 item ID 特例或事后调适用条件；
- 某协议的 operational unknown 被误计为 semantic miss/hit。

在这些条件下保留负结果，比把 DS-1000 专用正则搬进核心模块更有研究价值。
