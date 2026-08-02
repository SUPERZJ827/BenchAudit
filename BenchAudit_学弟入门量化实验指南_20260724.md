# BenchAudit 学弟入门与量化实验指南

> 更新时间：2026-07-24  
> 适用对象：第一次参与 BenchAudit、希望先跑通真实数据并看到量化改进的同学  
> 推荐主实验：**SVAMP-Platinum 固定 100 题监督实验**

---

## 1. 先说结论：为什么优先跑 SVAMP-Platinum

当前最适合新同学入门的不是 WorkspaceBench、Terminal-Bench 或 DS-1000，而是
**SVAMP-Platinum 100 题固定试验集**。

原因如下：

1. 它有人工整理的缺陷标签，可以直接计算 Precision、Recall 和 F1。
2. 100 题中包含 38 道已知缺陷题，实验规模不大，但信号足够明显。
3. 不需要准备复杂容器、代码仓库、Workspace artifact 或官方评测服务器。
4. 可以直接比较“单次 LLM 判断”和“BenchAudit 结构化审计”。
5. 历史实验中，BenchAudit 相比单次 LLM 获得了明显的召回率和 F1 提升。
6. 实验失败时容易定位原因，适合熟悉数据加载、审计器、缓存和评估流程。

这项实验最适合回答：

> 把 benchmark 缺陷检测拆成多个专门审计步骤，是否比让一个 LLM 一次性判断更有效？

---

## 2. 历史参考结果

以下数字来自仓库已有的固定 100 题实验，不代表每次 API 调用都会逐位复现：

| 方法 | Precision | Recall | F1 | 找到的真实缺陷 |
|---|---:|---:|---:|---:|
| 单次 LLM 直接判断 | 0.897 | 0.684 | 0.776 | 26/38 |
| BenchAudit 结构化审计 | 0.860 | 0.974 | 0.914 | 37/38 |
| 变化 | -0.037 | **+0.290** | **+0.138** | **多找到 11 道** |

对应的计数大致为：

| 方法 | TP | FP | FN |
|---|---:|---:|---:|
| 单次 LLM | 26 | 3 | 12 |
| BenchAudit | 37 | 6 | 1 |

这个结果表示：

- BenchAudit 为获得更高召回率，接受了少量额外误报。
- 单次 LLM 漏掉了 12 道已知问题，BenchAudit 只漏掉 1 道。
- 最明显的改进是 Recall 从 `0.684` 提升到 `0.974`。
- 综合 F1 从 `0.776` 提升到 `0.914`。

仓库也曾出现约 `0.889` 的独立复现结果，因此不应要求新一次运行严格得到
`0.914`。应重点检查实验方向是否一致，并分析结果差异来自哪里。

### 重要口径

这些数字主要衡量的是 **candidate/review 候选检测能力**：

- `candidate`：系统认为值得进一步审查的题目；
- `review`：需要后续验证的信号；
- `confirmed`：必须有可重放、可验证的客观证据，不能仅靠 LLM 判断。

因此不能把 `candidate F1=0.914` 说成“系统自动确认了 91.4% 的错误”。

---

## 3. 环境准备

### 3.1 克隆仓库

```bash
git clone https://github.com/SUPERZJ827/BenchAudit.git
cd BenchAudit
```

建议先记录当前版本，保证实验可追溯：

```bash
git rev-parse HEAD
git status --short
```

### 3.2 创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip install datasets
```

说明：

- `.[dev]` 安装 BenchAudit 及测试依赖；
- `datasets` 用于从 Hugging Face 下载 Platinum 数据；
- 当前仓库没有名为 `research` 的 optional dependency，因此不要使用
  `.[dev,research]`。

### 3.3 先运行单元测试

```bash
pytest -q
```

如果这里失败，先不要运行 API 实验。应保存：

- Python 版本；
- 完整报错；
- `git rev-parse HEAD`；
- `pip freeze`；
- 操作系统信息。

---

## 4. 准备 SVAMP-Platinum 数据

数据准备脚本的默认输出路径包含作者机器上的绝对路径，所以在新机器上必须显式指定
`--out`。

```bash
mkdir -p datasets/svamp_platinum

python scripts/prepare_svamp_platinum.py \
  --out datasets/svamp_platinum/svamp_platinum_all.jsonl \
  --manifest experiments/svamp_platinum_pilot100.manifest.json \
  --pilot-size 100 \
  --seed 42
```

预期生成：

- `datasets/svamp_platinum/svamp_platinum_all.jsonl`
- `experiments/svamp_platinum_pilot100.manifest.json`

准备完成后，终端应显示：

- 完整数据条数；
- `cleaning_status` 分布；
- `audit_label` 分布；
- 固定试验集包含 100 道题。

这个 manifest 固定了采样题目，后续所有方法必须使用同一份 manifest，不能为不同方法重新抽样。

---

## 5. 配置 DeepSeek API

仓库当前的 DeepSeek 配置文件是：

```text
configs/llm_deepseek.json
```

设置密钥：

```bash
export DEEPSEEK_API_KEY="你的密钥"
```

安全要求：

- 不要把密钥写进代码、Markdown、JSON、日志或 Git commit；
- 不要把带密钥的 shell history、`.env` 或终端截图上传；
- 运行前检查 `git diff`，确认没有密钥；
- API 调用会写缓存，中断后应优先复用缓存，不要直接删除重跑。

仓库当前配置的具体模型名可能随 API 服务变化。如果服务端报告模型不可用，应先确认
API 提供方当前支持的模型，再修改本地配置；不要悄悄换模型后与历史数字直接比较。

---

## 6. 实验 A：单次 LLM 基线

这个基线只让一个 LLM 对每道题做一次整体判断：

> 这道 benchmark 题是否存在质量问题？

它不使用结构化审计器分工，是最简单的对照组。

```bash
python scripts/run_direct_llm_baseline.py \
  --input datasets/svamp_platinum/svamp_platinum_all.jsonl \
  --manifest experiments/svamp_platinum_pilot100.manifest.json \
  --tag junior_svamp_naive \
  --truth-field metadata.audit_label \
  --truth-clean-value clean \
  --model deepseek \
  --workers 8 \
  --progress-every 10
```

主要输出：

```text
reports/junior_svamp_naive_direct_llm_comparison.json
reports/junior_svamp_naive_direct_llm_cache.jsonl
```

终端会直接显示：

- Items；
- Known defects；
- Flagged；
- Precision、Recall、F1；
- TP、FP、FN。

---

## 7. 实验 B：BenchAudit 结构化审计

BenchAudit 将问题拆给不同审计器处理：

- `gold`：检查标准答案是否可能错误；
- `question`：检查题意、充分性和歧义；
- `quantity`：检查数字、数量和约束是否一致；
- `event`：检查事件状态和题目叙述是否一致。

运行：

```bash
python scripts/run_svamp_pilot.py \
  --input datasets/svamp_platinum/svamp_platinum_all.jsonl \
  --manifest experiments/svamp_platinum_pilot100.manifest.json \
  --tag junior_svamp_benchaudit \
  --model deepseek \
  --auditors gold,question,quantity,event \
  --mode cascade \
  --workers 8 \
  --progress-every 10
```

主要输出：

```text
reports/junior_svamp_benchaudit_report.json
reports/junior_svamp_benchaudit_report.md
reports/junior_svamp_benchaudit_comparison.json
reports/junior_svamp_benchaudit_comparison.md
reports/junior_svamp_benchaudit_cache.jsonl
```

其中：

- `report.json`：完整机器可读审计结果；
- `report.md`：适合人工阅读的问题清单；
- `comparison.json`：完整评估指标；
- `comparison.md`：适合直接查看的指标报告；
- `cache.jsonl`：LLM 调用缓存，用于断点续跑和复现。

---

## 8. 自动打印两组核心指标

两组实验完成后，可以运行：

```bash
python - <<'PY'
import json
from pathlib import Path

files = {
    "Naive LLM": Path("reports/junior_svamp_naive_direct_llm_comparison.json"),
    "BenchAudit": Path("reports/junior_svamp_benchaudit_comparison.json"),
}

print(f"{'Method':<14} {'TP':>4} {'FP':>4} {'FN':>4} {'P':>8} {'R':>8} {'F1':>8}")
print("-" * 60)
for name, path in files.items():
    data = json.loads(path.read_text(encoding="utf-8"))
    m = data["candidate"]
    print(
        f"{name:<14} "
        f"{m['true_positive']:>4} "
        f"{m['false_positive']:>4} "
        f"{m['false_negative']:>4} "
        f"{m['precision']:>8.3f} "
        f"{m['recall']:>8.3f} "
        f"{m['f1']:>8.3f}"
    )
PY
```

学弟最终至少应提交下面这张表：

| 方法 | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| 单次 LLM | 实测 | 实测 | 实测 | 实测 | 实测 | 实测 |
| BenchAudit | 实测 | 实测 | 实测 | 实测 | 实测 | 实测 |
| 差值 | — | — | — | 差值 | 差值 | 差值 |

---

## 9. 指标是什么意思

### True Positive（TP）

数据集标注为有缺陷，系统也成功将其找出。

### False Positive（FP）

数据集标注为干净，但系统将其报告为候选问题。

FP 不一定永远是“系统完全判断错”。它可能是：

1. 真正的系统误报；
2. Platinum 标签没有覆盖的新问题；
3. 题目存在争议，但客观证据不足；
4. 输出格式或展示造成的假象。

因此 FP 必须分类分析，不能只看总数。

### False Negative（FN）

数据集明确标注为有缺陷，但系统没有找出来。

### Precision

```text
Precision = TP / (TP + FP)
```

含义：系统报告的问题里，有多少命中了已有标签。

### Recall

```text
Recall = TP / (TP + FN)
```

含义：所有已知问题中，系统找到了多少。

### F1

```text
F1 = 2 × Precision × Recall / (Precision + Recall)
```

F1 用来综合衡量 Precision 和 Recall，但不能代替两者分别报告。

---

## 10. 学弟第一周的具体任务

### 阶段一：完整复现

1. 克隆仓库并记录 commit SHA。
2. 建立独立虚拟环境。
3. 运行全部单元测试。
4. 生成固定 SVAMP 100 题数据。
5. 运行单次 LLM 基线。
6. 运行 BenchAudit。
7. 填写两组 P/R/F1、TP/FP/FN。
8. 保存运行命令、配置和输出文件。

### 阶段二：做误差分析

分别列出：

- BenchAudit 新增找出的真实问题；
- 单次 LLM 找到、但 BenchAudit 漏掉的问题；
- BenchAudit 的 FP；
- 两个系统共同漏掉的问题。

每条至少记录：

| 字段 | 内容 |
|---|---|
| item ID | 题目编号 |
| Platinum 标签 | clean / wrong_gold / bad_question |
| 系统判断 | 是否报告 |
| 主要证据 | 为什么认为有问题 |
| 初步裁决 | TP / FP / FN / 标签可能漏标 |
| 建议改进 | 规则、提示词、聚合还是证据门禁 |

### 阶段三：选择一个小问题改进

只选择一种重复出现的失败模式，例如：

- 数量关系没有识别；
- 题目状态转换理解错误；
- LLM 给出结论但没有足够证据；
- 相同根因被重复报告；
- 某一类表达方式造成稳定漏检。

改进流程必须是：

1. 先保存修改前结果；
2. 为失败样例编写回归测试；
3. 确认测试在修改前失败；
4. 修改实现；
5. 运行单元测试；
6. 重跑同一份实验；
7. 报告 P/R/F1 和 FP/FN 的变化；
8. 检查是否通过降低召回率来换取表面上的精度提升。

---

## 11. 防止“为了分数而调参”

这份 SVAMP Pilot 100 包含全部 38 道已知缺陷，因此它适合：

- 复现实验；
- 学习代码；
- 调试流水线；
- 建立误差分类；
- 验证回归是否被修复。

但不能反复观察这 100 题、修改代码，再把同一批题的提升声称为未知数据上的泛化能力。

真正开始优化前，应当：

1. 冻结当前 Pilot 100 结果；
2. 将数据划分为开发集与 holdout；
3. 开发时只查看开发集；
4. holdout 在方案确定后只运行一次；
5. 最好再在 GSM8K-Platinum 或 MMLU-Redux 上做跨数据集验证。

如果只在同一批 100 题上变好，正确表述是：

> 修复了已知回归，并在固定 SVAMP 试验集上提升。

不能直接表述为：

> 对任意 benchmark 的泛化检测能力提升。

---

## 12. 公平比较：需要注意 API 调用预算

BenchAudit 会将题目拆给多个审计器，通常比单次 LLM 基线使用更多调用。因此：

- 第一轮比较证明的是“完整系统效果更好”；
- 它还不能单独证明“在相同调用成本下也更好”。

更严格的第二阶段实验应加入 equal-budget baseline：

```bash
python scripts/run_equal_budget_baseline.py \
  --input datasets/svamp_platinum/svamp_platinum_all.jsonl \
  --manifest experiments/svamp_platinum_pilot100.manifest.json \
  --tag junior_svamp_equal_budget \
  --truth-field metadata.audit_label \
  --truth-clean-value clean \
  --n-votes N \
  --workers 8
```

这里的 `N` 不能随便填写，应根据 BenchAudit 实际每题平均 LLM 调用次数确定。

equal-budget baseline 会比较：

- `union`：多次调用中只要一次认为有问题，就报告；
- `self_consistency`：多次调用多数票决定；
- BenchAudit：相同量级调用预算下的结构化分工。

这能够区分：

> 提升究竟来自结构化审计，还是仅仅因为调用了更多次 LLM？

建议第一轮由学弟完成普通基线复现，equal-budget 实验在熟悉缓存和调用统计后再做。

---

## 13. 无需 API 的补充实验：排行榜影响

仓库已经保存了 15 个模型在 MMLU-Redux 1000 道题上的逐题回答，可以离线分析
benchmark 缺陷是否改变模型排名：

```bash
python scripts/ranking_impact_analysis.py
```

主要输出：

```text
reports/ranking_impact/ranking_impact.json
reports/ranking_impact/ranking_impact.md
reports/ranking_impact/ranking_impact_per_subject.json
```

历史核心结果：

| 指标 | 结果 |
|---|---:|
| 模型数量 | 15 |
| 题目数量 | 1000 |
| 被移除的第三方标注客观缺陷 | 181 |
| 清理前后 Kendall’s τ | 0.981 |
| 最大全局名次变化 | 1 |

Kendall’s τ 越接近 1，表示两个排行榜顺序越相似。`0.981` 表明整体排序变化不大，
但已经出现真实换位。

注意：

- 这是“缺陷影响排行榜”的实验；
- 它不是 BenchAudit 检测准确率实验；
- 181 道问题来自第三方人工标注；
- 细分学科题量较小时，冠军变化可能由删题数量和并列打破造成，必须参考随机删题对照，
  不能只展示最有利的学科结果。

---

## 14. 为什么暂时不让学弟先跑其他数据集

### WorkspaceBench

需要处理任务包、输入附件、rubric、输出 artifact 和 LLM judge。问题可能出在数据、
artifact 提取、rubric grounding 或 judge，自变量过多，不适合作为第一个实验。

### Terminal-Bench

需要真实运行轨迹、容器、版本配对、顺序控制和噪声门禁。实验价值很高，但搭建和解释成本较高。

### DS-1000

适合研究 evaluator soundness、等价实现和行为变异，但依赖 Python 科学计算环境及执行隔离。
它更适合熟悉系统后的执行证据专项。

### MMLU-Redux 全量 LLM 审计

有监督标签、研究价值高，但题目数量更多、API 成本更高。适合在 SVAMP 流程跑通后做跨领域验证。

推荐顺序：

```text
SVAMP 监督复现
    ↓
SVAMP 误差分析与小改进
    ↓
冻结 holdout 验证
    ↓
MMLU/GSM8K 跨数据集验证
    ↓
DS-1000 执行证据
    ↓
Workspace/Terminal 轨迹与 rubric 审计
```

---

## 15. 最终交付物

学弟完成第一轮后，至少提交：

1. `EXPERIMENT_ENV.md`
   - commit SHA；
   - Python 和依赖版本；
   - 模型配置名；
   - 完整运行命令；
   - 是否使用缓存。

2. `SVAMP_RESULTS.md`
   - 两个方法的 TP/FP/FN；
   - Precision/Recall/F1；
   - 与历史结果的差异；
   - 不能复现时的原因分析。

3. `SVAMP_ERROR_ANALYSIS.md`
   - 新增 TP；
   - FP；
   - FN；
   - 失败模式分类；
   - 推荐优化点。

4. 机器可读产物
   - comparison JSON；
   - audit report JSON；
   - 不含密钥的必要配置；
   - 如缓存过大，不直接提交 Git，只记录哈希和保存位置。

5. 如果修改代码
   - 新增回归测试；
   - 修改前后量化结果；
   - 完整测试结果；
   - 已知边界和可能回退。

---

## 16. 最简任务说明

可以直接把下面这段发给学弟：

> 请先在 BenchAudit 仓库上复现 SVAMP-Platinum 固定 100 题实验。使用同一份
> manifest，分别运行单次 DeepSeek 直接判断基线和 BenchAudit 的
> `gold,question,quantity,event` 结构化审计。报告 TP、FP、FN、Precision、Recall 和
> F1，并逐条分析两种方法的差异。历史参考结果为单次 LLM F1=0.776、
> BenchAudit candidate F1=0.914，但不要求逐位一致。第一轮不要修改代码；
> 第二轮从重复 FP/FN 中选择一种模式，先写回归测试，再修改并重跑。所有结果必须记录
> commit SHA、模型配置、命令和缓存状态。候选结果不得表述为自动 confirmed，且不能在
> 反复查看同一 100 题后声称获得未知数据泛化提升。

