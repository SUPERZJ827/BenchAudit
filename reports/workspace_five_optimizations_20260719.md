# WorkspaceBench 验证记录：五项工程优化后（2026-07-19）

## 结论先行

这五项改动提高的是 BenchAudit 的**证据可信度、未知 benchmark 的适配能力和实验可复现性**；它们没有修改 WorkspaceBench 的核心 rubric 语义判定器。因此，不能把任何 Workspace 指标的细小变动宣传为“代码让检测率提升”。

当前可成立的结论是：当前 Workspace 的确定性 objective-certificate 路线保持完整覆盖；模型语义审计的数字只能作为模型快照诊断，不能与历史运行作因果比较。

## 五项实现

| # | 改动 | 解决的问题 | 安全/证据边界 |
|---|---|---|---|
| 1 | `execution_attestation` | 把执行与裁决的信任域显式拆开 | 无独立 attester + verifier 时，一律 `review`；容器不再被误称为可信证明。 |
| 2 | `verifier_routing` | 新 benchmark 不同组件不能只靠一个通用 LLM 审计器 | 自动路由 Workspace、可执行代码、表格、数学及未知 schema；未知任务明确为 review-only。 |
| 3 | 冻结首轮 probe 的自适应实验接口 | JSON 恢复/重试被误算为第二策略收益 | baseline 与 adaptive 使用字节一致的初始 probes，并记录 SHA-256。 |
| 4 | DS-1000 SciPy/Sklearn 镜像配方 | 数值/科学计算题因依赖缺失而无法覆盖 | 固定版本、非 root、只读容器运行；镜像构建后仍需 registry digest 才能发表为可复现实验环境。 |
| 5 | cache-only replay | “复用缓存”出现 miss 后意外发起新 API 采样 | 任何 exact-cache miss 在 HTTP 前失败；不会把新的模型样本伪装成复跑。 |

相关新增/修改测试与全套测试：**516 passed**。

## WorkspaceBench 的可比历史基线

同一 Lite-100 冻结选择（50 source tasks × 4 pair operators = 200 clean/mutant pairs）上的历史结果：

| 运行 | 最终 mutant hit | paired discrimination | strict paired | clean FP | uncertain | 含义 |
|---|---:|---:|---:|---:|---:|---|
| v2（早期） | 123/200 (61.5%) | 123/200 (61.5%) | 107/200 (53.5%) | 0/200 | 106/400 | 早期模型路径；没有 objective-certificate 指标。 |
| v3-final（此前最新有效） | 200/200 | 200/200 | 200/200 | 0/200 | 0/400 | 200/200 objective certificates；raw model diagnostic 166/200，grounded-model diagnostic 108/200。 |

这里的 200/200 只适用于挑战构造的四种**原子、可确定验证** mutant；它证明对应验证器和挑战协议工作，不代表任意真实 Workspace 缺陷都有 100% recall。

## 本次尝试的透明记录

本次首先尝试从 `v3-final` 精确复用 response cache。缓存键全部 miss，于是旧实现的“事后检查”在 400 个新请求已经完成后才判定 replay 失败：

| 项目 | 数值 |
|---|---:|
| clean / mutant 请求 | 200 / 200 |
| cache hit | 0 / 0 |
| API attempt | 200 / 200 |
| clean / mutant token | 761,291 / 757,573 |
| exact-cache 验证 | **failed** |

因此该目录 `/tmp/workspace-five-semantic-replay` 是**无效的 exact-cache replay**，不能用于宣称代码改进。其未注册的模型快照诊断为 raw paired 168/200、grounded paired 114/200，较 v3 的 166/200、108/200 分别多 2、6 个；这完全可能来自模型服务/采样漂移，不能解释为方法增益。

这次失败本身直接促成第 5 项修复。之后同类命令会在第一条 cache miss 时拒绝 HTTP；测试覆盖了“miss 零传输、exact hit 可用”。

## 本次可报告的 Workspace 结果

当前代码已对同一冻结 Lite-100 完成 prepare/preflight：50 source tasks、200 pairs、`objective_certified=200/200`、输入 inventory complete=50/50、synthetic-gold mismatch=0。该项是对 Workspace 构造器和确定性证书路线的无回归验证，和 v3-final 相同；它不声称模型检测率提升。

## 下一次真正能回答“是否比以前好”的实验

要评估 Workspace 上的**新方法增益**，必须先实现一个实际改变 Workspace 决策的模块（例如扩大 objective resolver 的可证明 grammar，或新增有明确 oracle 的 artifact constraint verifier），再进行：

1. 固定未参与开发的 Workspace holdout、operator 配额、数据与附件 hash；
2. 在旧版与新版上使用相同的已保存模型 response，或同模型同日的预注册成对请求；
3. 同时报 mutant recall、strict paired discrimination、clean FP、uncertain、operational failures、每 operator 指标；
4. 用等量随机 mutant/删题对照，且只把确定性 verifier 的结论称为 confirmed；
5. 将 cache-only 设为回放默认，禁止任何 cache miss 自动变成新采样。

在那之前，最诚实的表述是：**系统更安全、更可适配，Workspace 的已验证确定性能力没有回归；尚无证据表明这五项通用工程改动提高了 Workspace 语义缺陷检测率。**
