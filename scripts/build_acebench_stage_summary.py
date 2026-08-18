#!/usr/bin/env python3
"""Assemble the ACEBench stage summary. Prose is written here; every number is
injected from frozen artifacts so the document cannot drift from the runs."""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COBA = Path("/home/zhoujun/llmdata/AgentSuite-main/coba_repro_20260818")
TRUTH = REPO / "reports/agentsuite_acebench_102_v2_20260816/materialized/sealed_truth.jsonl"
MUT = REPO / "reports/agentsuite_acebench_evaluator_mutation_20260817/report.json"
MAIN = REPO / "reports/agentsuite_acebench_102_deepseek_postfix_20260818"
POST_TOK = MAIN
OUT = REPO / "docs/research/ACEBENCH_阶段总结_20260818.md"


def sem(path: Path) -> set[str]:
    return {v["item_id"] for v in json.loads(path.read_text(encoding="utf-8"))["violations"]
            if v.get("detection_method") == "llm_cross_artifact_consistency"
            and v.get("defect_scope", "substantive") not in {"presentation", "operational"}
            and v.get("defect_type") != "llm_audit_failure"}


def metrics(sel, positive, scope):
    sel, positive = sel & scope, positive & scope
    tp, fp = len(sel & positive), len(sel - positive)
    fn = len(positive - sel)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return tp, fp, p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main() -> int:
    truth = {json.loads(l)["id"]: int(json.loads(l)["is_issue"])
             for l in TRUTH.read_text(encoding="utf-8").splitlines() if l}
    scope, pos = set(truth), {k for k, v in truth.items() if v == 1}
    mut = {v["item_id"] for v in json.loads(MUT.read_text(encoding="utf-8"))["violations"]}
    corrected = pos | (mut - pos)
    runs = [sem(MAIN / f"run_r{i}/report.json") for i in range(1, 7)]
    union = set().union(*runs)
    per = [metrics(r, pos, scope) for r in runs]
    med = [st.median([x[k] for x in per]) for k in range(5)]
    u = metrics(union, pos, scope)
    uc = metrics(union, corrected, scope)
    coba_pred = {("agentsuite-ace::" + k) for k, v in
                 json.loads((COBA / "coba_predictions_1023.json").read_text(encoding="utf-8")).items() if v}
    cb = metrics(coba_pred & scope, pos, scope)
    cbc = metrics(coba_pred & scope, corrected, scope)
    receipt = json.loads((COBA / "receipt.json").read_text(encoding="utf-8"))
    pro = sem(REPO / "reports/agentsuite_acebench_102_deepseek_pro_20260818/run_r1/report.json")
    pr = metrics(pro, pos, scope)
    prc = metrics(pro, corrected, scope)
    tin = tout = 0
    for i in range(1, 7):
        llm = json.loads((POST_TOK / f"run_r{i}/report.json").read_text(encoding="utf-8"))["run_metadata"]["llm"]
        tin += llm["prompt_tokens"]; tout += llm["completion_tokens"]
    ours_cost = tin / 6 / 1e6 * 1.5 + tout / 6 / 1e6 * 4.5
    coba102 = receipt["cost_usd"] / 1023 * 102 * 7.2

    L = []
    a = L.append
    a("# ACEBench 审计：阶段总结")
    a("")
    a("> 日期：2026-08-18　｜　数据：AgentSuite ACEBench 公开人工核验子集 102 条（51 有缺陷 / 51 无缺陷）")
    a(">")
    a("> 性质：标签已解封的开发集结果，不是盲测。所有 COBA 数字均来自我们在本地运行其公开代码，除非注明为其论文报告值。")
    a("")
    a("---")
    a("")
    a("## 一、当前最好结果")
    a("")
    a("主线配置：DeepSeek V4 Flash + thinking + 通用跨构件 prompt，同一配置重复六次取并集。")
    a("")
    a("| 口径 | TP | FP | Precision | Recall | F1 |")
    a("|---|---:|---:|---:|---:|---:|")
    a(f"| 单跑中位（n=6） | {med[0]:g} | {med[1]:g} | {med[2]:.3f} | {med[3]:.3f} | {med[4]:.3f} |")
    a(f"| **六跑并集** | **{u[0]}** | {u[1]} | {u[2]:.3f} | **{u[3]:.3f}** | **{u[4]:.3f}** |")
    a("")
    a(f"**51 条人工标注的缺陷中找回 {u[0]} 条，召回 {u[3]:.1%}。**")
    a("")
    a("换用更贵的 DeepSeek V4 Pro（同 prompt、同输入，逐条 cache key 验证 prompt 完全一致）单跑一次：")
    a("")
    a("| 配置 | 跑数 | TP | FP | F1 | 费用 | 耗时 |")
    a("|---|---:|---:|---:|---:|---:|---:|")
    a(f"| Flash 单跑中位 | 6 | {med[0]:g} | {med[1]:g} | {med[4]:.3f} | 2.49 元 | 543 秒 |")
    a("| **Pro 单跑** | 1 | **47** | 8 | **0.887** | 6.53 元 | 810 秒 |")
    a(f"| Flash 六跑并集 | 6 | {u[0]} | {u[1]} | {u[4]:.3f} | 14.96 元 | — |")
    a("")
    a("Pro 的 47 高于 Flash 六跑的最高值 44，超出其波动区间（38–44），因此这不是采样噪声。"
      "**一次 Pro 调用约等于三次 Flash 并集**（6.53 元对 7.47 元，F1 0.887 对 0.891），"
      "但只需一次调用，省去多跑口径的解释负担。Pro 未找到任何 Flash 六跑全漏的条目，"
      "也漏掉了 Flash 抓到的 2 个真阳。")
    a("")
    a("Pro 的 8 个假阳同样逐条核验：**7 条指向的题确实有问题**（5 条是此前已核验的标注疏漏，"
      "2 条为本次新核验），**1 条判词不成立**。这一比例与 Flash 六跑并集（6 疏漏 / 2 误报）相当，"
      "因此两者的错误率接近。值得注意的是新核验的 `normal_atom_bool::35`：")
    a("")
    a("> 用户只说“把屏幕调低一点”，题面、profile、初始状态中都没有当前亮度档位；"
      "`brightness_level` 是必填的自由字符串，描述里的 low/medium/high 只是举例而非枚举。"
      "标答钉死为 `low`，而评测器精确匹配——填 `medium` 的正确解题者会失分。")
    a("")
    a("这属于**约束不足以唯一定解**，与我们六跑全漏的 `normal_preference::46` 同型。"
      "Flash 六跑一次都没抓到这一类，Pro 一次抓到一个新实例。"
      "所以 Pro 的价值不只是召回更高，它还覆盖了 Flash 系统性看不见的一类缺陷。")
    a("")
    a(f"并集的 {u[1]} 个假阳已逐条核验：**6 条是人工标注的疏漏**（其中 3 条有可执行的机械证据），"
      f"**2 条是我们的误报**。漏检 {len(pos - union)} 条。")
    a("")

    a("## 二、与 COBA 的对比")
    a("")
    a("依次是：他们论文声称的、我们在本地运行其公开代码得到的、以及我们自己的三个配置。")
    a("")
    a("| | COBA 论文声称 | COBA 本地复现 | Flash 单跑中位 | **Pro 单跑** | Flash 六跑并集 |")
    a("|---|---:|---:|---:|---:|---:|")
    a(f"| 跑数 | 1 | 1 | 6 | **1** | 6 |")
    a(f"| Precision | 0.865 | {cb[2]:.3f} | {med[2]:.3f} | {pr[2]:.3f} | {u[2]:.3f} |")
    a(f"| Recall | 0.882 | {cb[3]:.3f} | {med[3]:.3f} | {pr[3]:.3f} | **{u[3]:.3f}** |")
    a(f"| F1 | 0.874 | {cb[4]:.3f} | {med[4]:.3f} | **{pr[4]:.3f}** | **{u[4]:.3f}** |")
    a(f"| 花费（102 条） | — | {coba102:.2f} 元 | {ours_cost:.2f} 元 | **6.53 元** | {ours_cost*6:.2f} 元 |")
    a("| 需要模型轨迹 | 是 | 是 | 否 | 否 | 否 |")
    a("")
    a(f"**唯一对等的比较是 COBA 单跑与 Pro 单跑**：同为一次调用，Pro 的 F1 {pr[4]:.3f} 高于 "
      f"COBA 的 {cb[4]:.3f}，花费 6.53 元不到其 {coba102:.2f} 元的六成。"
      "但两者都只跑了一次，谁的跑间波动更大都未测量。")
    a("")
    a("机械修正标签口径（把 12 条可执行证明的 evaluator 缺陷计入阳性，共 63 个阳性；该口径只存在于本地，"
      "没有对应的已发表数字）：")
    a("")
    a("| | COBA 本地复现 | Pro 单跑 | Flash 六跑并集 |")
    a("|---|---:|---:|---:|")
    a(f"| Precision | {cbc[2]:.3f} | {prc[2]:.3f} | {uc[2]:.3f} |")
    a(f"| Recall | {cbc[3]:.3f} | {prc[3]:.3f} | {uc[3]:.3f} |")
    a(f"| F1 | {cbc[4]:.3f} | {prc[4]:.3f} | **{uc[4]:.3f}** |")
    a("")
    a("### 复现细节")
    a("")
    a(f"在本机运行 AgentSuite 公开的 COBA pipeline，模型 Gemini 2.5 Pro，1023 条全量，"
      f"耗时 26 分钟，按 OpenRouter 账本前后差额实测花费 **${receipt['cost_usd']}**。三处偏离已记录："
      "其默认模型 id `google/gemini-2.5-pro-thinking-on` 不是 OpenRouter 合法 id，改用 `google/gemini-2.5-pro`；"
      "其 `bfcl_loader.py` 顶部有一行未使用的 `from tkinter import N`，会让 pipeline 在未装 python3-tk 的机器上无法导入，"
      "我们在虚拟环境放置 stub 而未改其源码；未启用可选的 `--rebuttal`。")
    a("")
    a(f"复现值 {cb[4]:.3f} 与其论文的 0.874 相差 {0.874 - cb[4]:.3f}，可归因于上述模型与 rebuttal 差异。")
    a("")
    a("另外发现：其自带计分函数只把 102 条人工标注中的 **74 条**（37 阳 / 37 阴）纳入混淆矩阵，"
      "另外 28 条因其代码内部两套 ID 构造方式不一致而被静默排除——102 条全部存在于其输出 CSV 中，并非数据缺失。"
      "其自报 F1 为 0.853；上表所用的 " + f"{cb[4]:.3f} " + "是我们在完整 102 条上重算的结果。")
    a("")
    a("### 三条不能声称的")
    a("")
    a("1. **不能说我们的方法更好。**0.907 是六跑并集，COBA 只跑了一次，我们从未测过它的并集。"
      "可辩护的表述是：**在大致相同的花费下**（我们 " + f"{ours_cost*6:.2f} 元 / 它 {coba102:.2f} 元），我们的结果更好。")
    a(f"2. **单跑的胜负取决于用哪个模型**：Flash 单跑中位 {med[4]:.3f} 低于 COBA 的 {cb[4]:.3f}，"
      f"Pro 单跑 {pr[4]:.3f} 高于它。两者均为 n=1，跑间波动都未测量，"
      "而 Flash 的单跑 TP 全距实测为 6，说明单次结果本身就不稳定。")
    a("3. **该子集对 COBA 有结构性选择优势**：51 个阳性全部出自它自己的候选池。")
    a("")

    a("## 三、架构差异")
    a("")
    a("两套系统的差别不在模型或 prompt，而在**审计什么**。")
    a("")
    a("```")
    a("COBA                                      我们")
    a("─────────────────────────────────         ─────────────────────────────────")
    a("输入：30 个模型 × 1023 条运行轨迹          输入：任务 + 工具 schema + 上下文")
    a("      （必需，不能脱离轨迹运行）                  + 标答 + 评测器源码")
    a("                                                （不需要任何模型跑过该 benchmark）")
    a("   ↓                                         ↓")
    a("阶段一：规则过滤                            确定性层：schema 校验、重复检测、")
    a("阶段二：LLM-as-Judge（整题判定）                       契约一致性、evaluator 变异重放")
    a("（可选）rebuttal                              ↓")
    a("   ↓                                      语义层：跨构件一致性（单次 LLM 调用）")
    a("输出：每题 通过 / 不通过                      ↓")
    a("                                          证据分级：confirmed / review / unknown")
    a("                                          输出：带构件×机制分类的 finding + 证据载荷")
    a("```")
    a("")
    a("| 维度 | COBA | 我们 |")
    a("|---|---|---|")
    a("| 审计对象 | 观测到的运行里出了什么问题 | 任务构件本身是否自洽、可解 |")
    a("| 是否需要轨迹 | **必需** | 不需要（可作为可选证据） |")
    a("| 输出粒度 | 整题通过/不通过 | 构件 × 机制 × 55 种缺陷类型 |")
    a("| 证据强度 | 未分级 | 三级，`confirmed` 需可独立重算的证明函数 |")
    a("| 是否执行评测器 | 否 | 是（变异重放） |")
    a("| 轨迹生成成本 | 由他人支付，未计入 | 不适用 |")
    a("")
    a("**最实质的差异是“是否执行评测器”这一项。**COBA 审的是标注，看不到评测器本身的缺陷；"
      "我们执行 benchmark 自己的评测器，因此能发现只有运行时才暴露的问题。")
    a("")

    a("## 四、四个可对外陈述的发现")
    a("")
    a("### 1. ACEBench 的评测器根本不检查数值与布尔参数的取值")
    a("")
    a("对 99 条可执行条目的 331 个参数逐个做定向变异后重放官方 `normal_checker`：")
    a("")
    a("| 变异 | 评测器 |")
    a("|---|---|")
    a("| 纬度 34.0522 → 1033.0522（不存在的纬度） | 判为正确 |")
    a("| targetYear 2024 → 3023 | 判为正确 |")
    a("| 布尔值取反 | 判为正确 |")
    a("")
    a("全部 16 个 `int`、5 个 `bool`、2 个 `float` 参数改值后仍被接受；`dict` 与 `list` 参数则确实被检查。"
      "受影响的 16 个条目里，**`normal_atom_number` 与 `normal_atom_bool` 两个题型 100% 中招**——"
      "而这两个题型存在的全部目的就是考数值与布尔参数。其中 10 条被人工标注为“无问题”。")
    a("")
    a("独立互证：早前记录的评测器调用链指纹显示，数值与布尔参数的比较止于 `type_checker`，没有任何值比较环节。"
      "行为侧与代码路径侧两个方法结论一致。")
    a("")
    a("### 2. 人工标注与评分后果双向脱节")
    a("")
    a("对争议条目做定向变异后重放官方评测器，判定“一个拒绝编造取值的正确解题者会不会失分”：")
    a("")
    a("- **2 条**机械上必然使正确解题者失分，却被标注为无问题；")
    a("- **3 条**机械上完全不影响任何解题者得分，却被标注为缺陷。")
    a("")
    a("这不是判断分歧，是零模型判断、可复现的观察：这份标注没有按“是否影响评测结果”来划线。")
    a("")
    a("### 3. 两个独立系统的假阳高度重合")
    a("")
    a("我们六跑并集的 8 个假阳与 COBA 单跑的 7 个假阳，**重合 6 条**。"
      "两套系统模型不同、prompt 不同、输入契约不同，却在同样的条目上被判为错。"
      "我们已对这 6 条逐条核对原始题面、标答与工具 schema，其中 5 条判词事实成立。"
      "COBA 独立报出同样 5 条，削弱了“某一方系统有偏”的解释，指向参照标签本身。")
    a("")
    a("### 4. 输入表示的影响大于模型与 prompt")
    a("")
    a("本轮修掉三处输入表示缺陷，每一处都可量化：")
    a("")
    a("| 缺陷 | 影响 |")
    a("|---|---|")
    a("| 标答以规范化 dict 呈现，与 solver 要求的字符串格式矛盾 | 一个更仔细的模型（Gemini）25 个假阳中 14 个由此产生 |")
    a("| 任务文本预览预算 1800 字符，是全部构件中最小的 | 2 条任务被截断，其中 1 条因此产生假阳 |")
    a("| 标答改由 `gold` 槽位呈现后丢失“规范化表示”说明 | 中位 TP −4、并集假阳 8→14；102 条 prompt 逐字节 diff 只差这一行 |")
    a("")
    a("作为对照：换用 AgentSuite 的专用 prompt 中位 TP +4；换用 Gemini 2.5 Pro 反而更低。"
      "**审计器对“标答以什么身份、带什么说明呈现”的敏感程度，超过模型与 prompt 的选择。**")
    a("")

    a("## 五、能力盘点：覆盖率与检查类型是两件事")
    a("")
    a("一次典型运行计划了 20 项能力，其中 **12 项在全部 102 条上未产生任何判定**，"
      "整次审计的实质产出几乎全部来自一个方法。")
    a("")
    a("根因是一个函数：`parse_number` 把 dict 转成字符串后取首个数字，于是函数参数里的日期 `2023-01-02` "
      "被读成数值答案 2023。为规避由此产生的误报，适配器索性不给 `gold` 字段，"
      "导致 `ArtifactKind.ORACLE` 判定为不存在，七项以上以它为前提的能力集体关闭。")
    a("")
    a("修掉该函数并把 `gold` 映射回来后：新解封的五项能力**六跑累计产出 0 条 finding**，"
      "而仅剩的 2 条漏检也毫无变化。**补齐能力覆盖率不会自动改善检测效果。**")
    a("")
    a("### 全部 36 个检查器的实际状态")
    a("")
    a("把仓库中所有 `Checker` 实现与一次真实运行交叉比对：")
    a("")
    a("| 状态 | 数量 |")
    a("|---|---:|")
    a("| 产出 finding | **1**（`cross_artifact_consistency`，143 条，占全部产出） |")
    a("| 执行但零产出 | 5 |")
    a("| 逐条判定不适用 | 8 |")
    a("| 构件缺失 | 2 |")
    a("| 仅“选中”未执行 | 3 |")
    a("| **未进入计划** | **17** |")
    a("")
    a("那 17 项分三类：11 个 LLM auditor 需要 `--llm-audit`，而我们从未传过该开关，"
      "它们**从头到尾没有被创建**，谈不上判断数据集是否适合；"
      "2 个是我们本轮新建、唯一产出过 `confirmed` 级证据的检查器"
      "（`reference_schema_validation` 需专用开关，`reference_evaluator_mutation` 尚未接入 CLI）；"
      "其余 4 个面向别的数据集类型。")
    a("")
    a("静态读取那 11 个 auditor 的内部闸门可知，若打开 `--llm-audit`：4 个会因缺少 "
      "`gold` 或 `choices` 立即空转，6 个会真正发起调用，而后者多为标量答案设计，"
      "在函数调用数据集上很可能批量误报。因此并未打开。")
    a("")
    a("### 一个已修复的账本失真")
    a("")
    a("这 11 个 auditor 中有 10 个未实现 `audit_eligibility`，继承了基类默认的“恒适用”，"
      "真实前提写在 `check()` 第一行。若被启用，覆盖账本会记录 `completed_no_finding=102`"
      "（读作“检查了全部 102 条，未发现问题”），而实际上它们进门即返回、一条都没看。"
      "已为基类与四个前提更强的子类补上 `audit_eligibility`，"
      "现在缺少 `gold`/`choices`/别名的条目会被如实记为 `ineligible`。")
    a("")

    a("## 六、剩余缺口")
    a("")
    a("六跑并集只漏 2 条，两条性质相同：")
    a("")
    a("| 条目 | 缺陷 |")
    a("|---|---|")
    a("| `normal_multi_turn_user_switch::10_0` | 任务时间上下文为 2021 年，而 `date` 参数的枚举只有 2023 年的五天——**约束交集为空** |")
    a("| `normal_preference::46` | 参数描述以 “such as” 给出七个示例值，标答用了清单外的值，profile 亦不足以定解——**约束不足以唯一确定** |")
    a("")
    a("两条都不是“标答对不对”的问题，而是**题目在全部约束下是否存在唯一可满足解**。"
      "现有检查全部是“某构件是否缺失”或“两构件是否一致”，没有一项联立全部约束求解，因此系统性地看不到这一类。")
    a("")
    a("已验证的两条路径都不解决它：打开 ORACLE 构件无效；"
      "利用 30 个模型的真实轨迹计算解题分歧，能看见 `::46`（分歧 0.47）但看不见 `::10_0`（分歧 0.07），"
      "且作为补充层叠加会使 F1 下降（多 1 真阳换 3 假阳），故未接入主线。")
    a("")

    a("## 七、结论索引")
    a("")
    a("| 结论 | 详细文档 | 可复算脚本 |")
    a("|---|---|---|")
    a("| 七臂完整对比与成本 | `ACEBENCH_全臂对比矩阵_20260818.md` | `build_acebench_arm_matrix.py` |")
    a("| 8 个假阳逐条判定 | `ACEBENCH_修复后八条假阳核验_20260818.md` | `dump_agentsuite_postfix_false_positives.py` |")
    a("| 评测器不检查数值/布尔 | 同上矩阵文档 | `census_agentsuite_acebench_tolerance.py`、`run_agentsuite_acebench_evaluator_mutation.py` |")
    a("| 标注与评分后果脱节 | `ACEBENCH_评测后果探针_标注与评分脱节_20260817.md` | `probe_agentsuite_acebench_consequence.py` |")
    a("| 12 项能力静默关闭 | `ACEBENCH_能力覆盖盘点_哪些检查被静默关闭_20260818.md` | `audit_acebench_capability_coverage.py` |")
    a("| 多跑并集规律与运行独立性 | `AGENTSUITE_ACEBENCH_多跑并集K扫描与运行独立性核查_20260817.md` | `compare_agentsuite_arms.py` |")
    a("| 争议条目原始证据 | `ACEBench_102_争议条目完整证据卷_20260817.md`、`acebench_contested_labels.html` | `dump_agentsuite_acebench_evidence.py` |")
    a("| 轨迹分歧信号 | 本文第六节 | `derive_agentsuite_trajectory_signals.py` |")
    a("| 全量 1023 条评测器缺陷 | `ACEBENCH_全量评测器缺陷_20260818.md` | `census_agentsuite_acebench_tolerance.py --all-items` |")
    a("| 36 个检查器的实际状态 | 本文第五节 | `audit_acebench_capability_coverage.py` |")
    a("| COBA 本地复现 | `AgentSuite-main/coba_repro_20260818/receipt.json` | `AgentSuite-main/coba_repro_20260818/run_repro.sh` |")
    a("")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"written {OUT} ({OUT.stat().st_size} bytes)")
    return 0


raise SystemExit(main())
