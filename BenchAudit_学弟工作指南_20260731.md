# SVAMP 实验复盘与迭代方案（定稿 2026-07-31）
> 替代旧版《SVAMP 第一轮反馈与下阶段安排》；旧版归因过早，本文为修正定稿。
> 无需补充外部文件，现有数据与缓存完整可用。

---

# 0 核心结论：指标下跌非本地改动导致
## 0.1 多轮指标对照（固定100题数据集、同一manifest）
| 运行版本 | 运行日期 | 候选P | 候选R | 候选F1 | TP/FP/FN | confirmed |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| 原始v5 | 06-26 | 0.860 | 0.974 | 0.914 | 37/6/1 | — |
| 07-07重校验 | 07-07 | 0.857 | 0.947 | 0.900 | 36/6/2 | 26 |
| 主线最新 | 07-31 | 0.660 | 0.868 | 0.750 | 33/17/5 | 0 |
| 本地实验 | 07-30 | 0.640 | 0.842 | 0.727 | 32/18/6 | 0 |

本地结果与主线基线仅相差 0.023，F1 整体回退为框架/策略变更导致，**并非本地代码改动问题**。

## 0.2 2项必须合入主线的修复（任务0）
本地5份未提交改动中，2项为主线固有缺陷修复，需提交主线仓库：
1. `scripts/run_svamp_pilot.py`：缺失 `--allow-remote-data-egress` 参数透传，主线脚本无法正常运行；新增开关透传，不写死、保持默认安全。
2. `configs/llm_deepseek.json`：缺少 `thinking` 配置；DeepSeek V4 默认开启思考链路，补充 `"thinking": "disabled"` 适配模型。

剩余3份修改文件（`benchcore/llm_client.py`、`run_direct_llm_baseline.py`、`tests/test_llm_client.py`）先区分：属于同类主线缺陷修复则一并提交；纯实验调试代码执行 `git stash` 暂存。
完成标准：`git status` 工作区干净。

---

# 1 无需修复：confirmed 恒等于0 为设计约束
主线全量110条检测结果统计：
```
evidence_tier: {'review': 109, 'unknown': 1}
review_only  : {True: 110}
```
7月中旬项目硬性规范：LLM 生成证据仅允许停留在 `review` 层级，**禁止自动升级至 confirmed**；仅本地可确定性重放、带独立签名的非LLM证据，才可标记 confirmed。

07-07版本存在26条 confirmed、F1=0.688，是旧证据分级政策产物，该政策已主动废弃。
因此 `0.914 → 0.750` 不具备横向对比口径，指标下跌不能作为代码问题依据。

---

# 2 核心待优化问题：FP数量膨胀三倍
| 批次 | 候选总量 | TP | FP | FN |
| ---- | ---- | ---- | ---- | ---- |
| 07-07历史基线 | 42 | 36 | 6 | 2 |
| 主线/本地当前 | 50 | 32 | 18 | 6 |

- TP仅小幅下降，FP从6上涨至18，膨胀3倍，候选精度跌至0.64；
- 优化目标：FP压缩至10左右、TP无明显损失，精度提升至0.76、F1达到0.79；
- 三大改进方案共性：仅过滤模型自证无冲突、内部逻辑矛盾的无效证据，**无召回损耗风险**，属于帕累托优化。

---

# 3 零成本迭代机制（全方案共用）

## 3.0 你手里已有什么，以及哪些东西 GitHub 上没有

**不需要任何人给你文件，你本地已经齐全。** 但要知道它们分别从哪来：

| 文件 | 来源 | 丢了怎么办 |
|---|---|---|
| `benchcore/`、`scripts/`、`configs/` 全部代码 | GitHub | `git fetch` 即可 |
| `experiments/svamp_platinum_pilot100.manifest.json` | **只在本地** | ⚠️ **GitHub 上没有**（被 .gitignore 排除），删了要找师兄要 |
| `datasets/svamp_platinum/svamp_platinum_all.jsonl` | **只在本地** | ⚠️ **GitHub 上没有**（`datasets/` 被忽略），删了要找师兄要 |
| `reports/junior_svamp_benchaudit_*`（你那轮的结果和缓存） | **只在本地** | `reports/` 被忽略；缓存删了只能花 $0.19 重跑 |

**一句话：`experiments/` 和 `datasets/` 这两个目录别删，GitHub 上没有备份。**

## 3.1 缓存说明

缓存文件：`reports/junior_svamp_benchaudit_cache.jsonl`（662 条）

三个改进都是后处理聚合/判定逻辑，不碰 prompt，所以缓存能全命中 → **0 API 调用、0 费用、2 分钟一轮**，可以无限次迭代。

**但缓存命中不是理所当然的。** 缓存 key 由这些字段一起算出来：

```
model / base_url / temperature / max_tokens / thinking / dry_run / prompt
```

**其中 `thinking` 最容易踩坑**：你的缓存是用 `"thinking": "disabled"` 建的，而主线 `configs/llm_deepseek.json` **没有这个字段**（缺省 = None）。实测两者 key 不同：

```
无 thinking 字段    → a678f7ea...
thinking=disabled  → d50654a6...
```

**所以同步代码时，千万别让主线那份 config 覆盖掉你本地的。** 一旦被覆盖，缓存 100% 失效，而且会在 thinking 开启状态下跑——那是另一个实验，不是同一个基线。

## 3.1.5 第 0 步：先验证缓存真的还活着

在做任何改动之前，**什么都不改，先按 3.2 空跑一次**：

- API attempts = **0** → 缓存有效，后面可以放心免费迭代；
- API attempts ≠ 0 → **停下来**，先检查 `configs/llm_deepseek.json` 里有没有 `"thinking": "disabled"`。

（就算缓存真失效了也不是灾难：全新冷跑约 635 次调用、$0.19、2 分钟。只是你要知道自己在哪个模式。）

## 3.2 零成本重跑完整命令
```bash
# 生成实验报告
python -m benchcore.cli audit \
    datasets/svamp_platinum/svamp_platinum_all.jsonl \
    --manifest experiments/svamp_platinum_pilot100.manifest.json \
    --llm-audit --llm-auditors gold,question,quantity,event \
    --gold-evidence-mode cascade \
    --llm-config configs/llm_deepseek.json \
    --llm-cache reports/junior_svamp_benchaudit_cache.jsonl \
    --workers 16 --progress-every 20 \
    --out reports/exp_<改动名>_report.json \
    --md reports/exp_<改动名>_report.md \
    --allow-remote-data-egress --print-summary

# 指标对比工具
python -m benchcore.cli compare \
    datasets/svamp_platinum/svamp_platinum_all.jsonl \
    --report reports/exp_<改动名>_report.json \
    --truth-field metadata.audit_label --clean-value clean \
    --manifest experiments/svamp_platinum_pilot100.manifest.json \
    --out reports/exp_<改动名>_comparison.json \
    --md reports/exp_<改动名>_comparison.md --print-summary
```
校验标准：每次执行后查看 API 调用次数。**非 0 就立即停下来排查** —— 要么是改到了 prompt，要么是 config（尤其 `thinking`）被动过。不要在缓存失效的情况下继续迭代，否则每轮都在花钱，而且比较的可能不是同一个基线。

---

# 4 任务1：FP归因分析（半天、零API消耗，优先级最高）
## 4.1 输入数据源
1. `reports/junior_svamp_benchaudit_report.json`：本地实验全部检测结果
2. `reports/junior_svamp_benchaudit_comparison.json`：TP/FP/FN判定明细
3. `experiments/svamp_platinum_pilot100.manifest.json`：固定100题范围
4. `datasets/svamp_platinum/svamp_platinum_all.jsonl`：数据集真实标签 `metadata.audit_label`
> 报告文件丢失可执行3.2命令重跑生成。

## 4.2 统计分析脚本
```python
import json
from collections import defaultdict

# 加载检测结果
rep = json.load(open("reports/junior_svamp_benchaudit_report.json"))
findings = rep.get("violations") or rep.get("findings")

# 加载数据集真实标签
truth = {}
for line in open("datasets/svamp_platinum/svamp_platinum_all.jsonl"):
    r = json.loads(line)
    truth[r["id"]] = r["metadata"]["audit_label"]

# 限定100题范围
man = json.load(open("experiments/svamp_platinum_pilot100.manifest.json"))
scope = {row["item_id"] for row in man["selected"]}

# 统计每个auditor覆盖题目、单题命中auditor列表
by_method = defaultdict(set)
methods_of = defaultdict(set)
for f in findings:
    if f["item_id"] in scope:
        by_method[f["detection_method"]].add(f["item_id"])
        methods_of[f["item_id"]].add(f["detection_method"])

# 输出各检测器指标
print(f"{'auditor':42s} {'题数':>5} {'TP':>4} {'FP':>4} {'条件精度':>8}")
for m, items in sorted(by_method.items(), key=lambda x: -len(x[1])):
    tp = sum(1 for i in items if truth[i] != "clean")
    print(f"{m:42s} {len(items):5d} {tp:4d} {len(items)-tp:4d} {tp/len(items):8.3f}")

# 输出仅单一检测器命中的样本（FP核心来源）
print("\n仅被单个auditor命中的题：")
for item, ms in sorted(methods_of.items()):
    if len(ms) == 1:
        lab = "TP" if truth[item] != "clean" else "FP"
        print(f"  {item:28s} {lab}  {list(ms)[0]}")
```

## 4.3 必须输出3项分析结论（决定改进A/B开发顺序）
1. 18条FP中，仅单一auditor触发的样本数量；单检测器FP为对应模块缺陷，多检测器共同触发为题目天然争议。
2. 两类 `*_nonmaterial` 检测器分别产出的TP、FP总量（直接判定改进A是否落地）。
3. 与上一轮人工裁决（10纯误报 / 4争议证据不足 / 4数据集漏标）是否匹配。

产出统计表格后同步，共同确定优先开发改进A或改进B。

---

# 5 三大优化方案
## 5.1 改进A：仅含nonmaterial证据禁止生成候选
### 5.1.1 背景证据
两类nonmaterial检测器主线检出量：
- `llm_quantity_consistency_nonmaterial`：9条
- `llm_event_state_nonmaterial`：6条

`nonmaterial` 为模型自标记字段：识别到轻微矛盾，但该矛盾不影响题目最终答案。
存在多条仅该标签触发的纯FP案例：
| item ID | 触发标签 | 人工裁决 | 证据原文 |
| ---- | ---- | ---- | ---- |
| chal-875 | `llm_event_state_nonmaterial` 单独触发 | 纯误报 | "No state conflicts or role confusions. The problem is straightforward." |
| chal-699 | `llm_quantity_consistency_nonmaterial` 单独触发 | 纯误报 | "4 shelves × 11 = 44. Cabinets are irrelevant. **No contradictions.**" |

chal-699典型问题：原文明确标注无矛盾，仍生成检测候选。

### 5.1.2 代码修改规则（候选聚合层）
若单题**全部证据标签均为 `*_nonmaterial`**：
1. 不生成对外候选；
2. 证据保留存入review注释，供人工复核；
存在任意一条material有效证据：原有聚合逻辑完全不变。

### 5.1.3 落地代价（依赖任务1结论）
样本chal-258为多nonmaterial证据聚合产出的有效TP（`llm_quantity_consistency_nonmaterial` + `llm_event_state_nonmaterial`，标签bad_question），该规则会丢失此类样本。
落地判定标准：
- nonmaterial-only样本 FP 远多于 TP → 执行改造，整体收益正向；
- FP/TP数量持平或TP更多 → 放弃改造，记录风险结论归档。

> 核心准则：优化不能仅关注可消除的误报，必须提前量化召回损耗。

### 5.1.4 验收标准
零缓存重跑对比前后指标：
- 基准：TP=32，FP=18
- 验收判断：TP下降1、FP减少4为优质优化；TP下降3、FP仅减少3不建议落地。

## 5.2 改进B：LLM内部自相矛盾响应降级（自研方向）
### 5.2.1 背景证据
5道高频自相矛盾FP样本：162、599、687、934、974
典型案例chal-974：
> "...deleted = 110 - 24 = 86. The question asks how many more added than deleted: added 89, deleted 86, difference = 3. **Wait, derived answer should be 3, not 86. Correction: derived answer i…**"
模型推理正确结果3，但`derived_answers`写入中间变量86，程序化对比产出假缺陷。
chal-934同理：算式结果与标准答案一致，但审计聚合返回全错高置信投票。

### 5.2.2 修改逻辑（derived_answers前置校验）
1. 校验 `derived_answers` 数值与rationale内最终计算结果一致 → 正常进入对比流程；
2. 数值不一致 → 当前响应标记无效，可重试；
3. 重试后仍不一致 → 降级为`unknown`，不生成候选。

遵循项目fail-closed规范：内部不自洽的LLM输出，不应产出正式检测结论。

### 5.2.3 分步落地约束
1. 第一阶段：仅实现不一致直接降级unknown，**不加重试**，全程复用缓存、零API成本验证效果；
2. 验证有效后，再追加重试逻辑；
3. 将5条问题样本固化为回归测试用例。

### 5.2.4 验收标准
重跑后5道自相矛盾样本不再产出候选，其余样本指标无变动。

## 5.3 改进C：确定性数量可行性检查器（唯一可产出confirmed的模块）
### 5.3.1 背景证据（纯算术可判定，无需LLM）
| item ID | 问题描述 | 当前状态 |
| ---- | ---- | ---- |
| chal-513 | David完成38个，比Zachary多56 → Zachary=-18 | 漏检 |
| chal-797 | 系列共17部电影，观看21部 | 漏检 |
| chal-826 | 系列共4本书，阅读19本 | 漏检 |
| chal-417 | 71 − sold + 38 = 116 → sold = −7 | 正常检出 |
| chal-463 | 花瓶15朵，丢弃33朵 | 正常检出 |
| chal-908 | 9块甜饼干，吃掉36块 | 数据集标clean，疑似漏标 |
| chal-666 | 持有4美元，消费13美元 | 数据集标clean，疑似漏标 |

当前LLM审计遗漏3条算术硬冲突样本；该模块为**非LLM确定性逻辑**，是SVAMP场景首个可生成confirmed标签的检测器，优先级高于单纯F1提升。

### 5.3.2 强制预飞流程（团队历史规范，规避无效开发）
必须先完成协议定义+全量覆盖率扫描，达标后才可编码实现。
#### C.3.1 输出协议文档（仅MD，不写代码）
固定约束：
1. V1仅覆盖三类硬冲突：消耗数量>存量、推导计数为负数、消费金额>持有金额；
2. 明确定义「实体-初始值-变化量-最终值」抽取规则；
3. 无法抽取完整字段统一标记`NOT_IDENTIFIABLE`，禁止猜测推导；
4. 落地门槛：预飞全量覆盖率≥20%，阈值固定不可调整；
5. 校验控制集：正常题目无触发，抽取失败仅弃权，不强制标记clean；
6. 全程无LLM调用。

#### C.3.2 覆盖率预飞扫描
开发纯统计扫描脚本，在SVAMP-Platinum全量300题执行，仅输出聚合统计与数据集哈希，不导出原题文本。
判定分支：
- 覆盖率＜20%：终止开发，输出结论「V1抽取语法覆盖不足，方案不成立」（负结果同样具备工程价值）；
- 覆盖率≥20%：同步协议+预飞数据复核，通过后再编码。

#### C.3.3 前置依赖
改进C开发前**必须同步主线最新代码**：主线7-27新增确认合约、重放证明、review-only限制等核心模块，本地当前版本`c6f62ce`缺失相关逻辑。
同步后通读两处核心源码，明确confirmed判定标准：
1. `benchcore/promotion.py` → `_differential_oracle_replay`
2. `benchcore/differential_oracle.py` → `replay_differential_oracle_proof`

---

# 6 代码环境、成本与开发规范
## 6.1 版本同步说明
本地代码commit：`c6f62ce`（07-25）
主线7-27新增全套确认链路、独立重放、执行证明模块：
1. 任务1、改进A、改进B：现有版本可直接开发，无需同步主线；
2. 改进C：强制同步主线最新代码。

同步完成标准：全量测试用例≥780个passed。

## 6.2 调用成本参考
1. 100题全新冷跑（缓存未命中）：635次LLM调用、1.2M tokens、成本$0.19，耗时2分钟；
2. 缓存复用重跑：0调用、0成本、2分钟。

## 6.3 三条强制开发准则
1. **先定协议，后写代码**
   固定流程：协议文档提交 → 实现+单测提交 → 执行实验 → 输出指标报告；四阶段拆分，避免事后调整指标阈值。
2. **领域解析模块先测覆盖率**
   同改进C预飞逻辑，两次历史案例证明可大幅节省无效开发工时。
3. **测试用例优先级高于业务实现**
   测试失败优先修复代码逻辑；仅能提供完整证明原断言失效时，才可修改测试用例（历史教训：曾为兼容代码篡改测试，掩盖底层bug）。

## 6.4 禁止执行操作清单
1. 禁止强行修改、消除`confirmed=0`：属于顶层架构设计约束；
2. 禁止调整置信度阈值降低FP：模型置信度高度饱和，阈值无区分能力；
3. 禁止新增auditor检测器：当前单题平均6.35次调用，调用成本过高；
4. 禁止篡改Platinum数据集真实标签美化指标；
5. 优化报告必须同时输出TP、FP变动，不得只展示FP下降数据。

---

# 7 整体开发节奏
1. 任务0（主线缺陷提交）：0.5h
2. 任务1（FP归因统计）：0.5天
3. 改进A / 改进B 二选一迭代：各1~2天
4. 同步主线最新代码
5. 改进C（协议编写 → 覆盖率预飞 → 复核 → 编码）

## 同步沟通节点（必须同步结果）
1. 任务1FP归因统计表格产出，确定A/B开发顺序；
2. 改进C协议文档+覆盖率预飞结果完成，编码前复核。

无论实验正向优化、覆盖率不足终止方案、代码阻塞，均同步反馈；负向实验结论同样具备参考价值。

---

# 8 上一轮工作正向沉淀（可复用经验）
1. 完整记录未提交变更脏工作区，快速定位指标下跌根因；
2. 主动区分review/confirmed分级口径，对齐项目顶层规范；
3. 指标下跌对本地结论不利，完整披露、不隐藏，罗列多维度潜在归因；
4. 不单纯统计FP总量，人工逐条划分误报/争议/数据集漏标三类；
5. 主动拒绝美化指标的捷径方案：篡改数据集标签、调整置信阈值。

上一轮仅缺少明确优化落地路径，本文补齐完整迭代方案；现有缓存与数据可支撑低成本、多轮调优，目标提升候选检测精度。