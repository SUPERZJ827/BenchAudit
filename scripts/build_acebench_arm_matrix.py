#!/usr/bin/env python3
"""Consolidate every ACEBench arm we have measured into one comparison document."""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COBA = Path("/home/zhoujun/llmdata/AgentSuite-main/coba_repro_20260818")
TRUTH = REPO / "reports/agentsuite_acebench_102_v2_20260816/materialized/sealed_truth.jsonl"
MUT = REPO / "reports/agentsuite_acebench_evaluator_mutation_20260817/report.json"
OUT = REPO / "docs/research/ACEBENCH_全臂对比矩阵_20260818.md"

PILOT = REPO / "reports/agentsuite_acebench_102_deepseek_thinking_pilot_20260816"
KSCAN = REPO / "reports/agentsuite_acebench_102_thinking_k_scan_20260817"
POST = REPO / "reports/agentsuite_acebench_102_deepseek_postfix_20260818"
GEM = REPO / "reports/agentsuite_acebench_102_gemini_generic_20260817"
AB = REPO / "reports/agentsuite_acebench_102_prompt_specialization_thinking_ab_20260817"


def strip(i): return i.replace("agentsuite-ace::", "")


def candidates(path: Path) -> set[str]:
    return {strip(v["item_id"]) for v in json.loads(path.read_text(encoding="utf-8"))["violations"]
            if v.get("detection_method") == "llm_cross_artifact_consistency"
            and v.get("defect_scope", "substantive") not in {"presentation", "operational"}
            and v.get("defect_type") != "llm_audit_failure"}


def tokens(path: Path) -> tuple[int, int]:
    llm = json.loads(path.read_text(encoding="utf-8"))["run_metadata"]["llm"]
    return llm.get("prompt_tokens", 0), llm.get("completion_tokens", 0)


def metrics(sel, positive, scope):
    sel, positive = sel & scope, positive & scope
    tp, fp = len(sel & positive), len(sel - positive)
    fn = len(positive - sel)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return tp, fp, p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main() -> int:
    truth = {strip(json.loads(l)["id"]): int(json.loads(l)["is_issue"])
             for l in TRUTH.read_text(encoding="utf-8").splitlines() if l}
    scope = set(truth)
    pos = {k for k, v in truth.items() if v == 1}
    mut = {strip(v["item_id"]) for v in json.loads(MUT.read_text(encoding="utf-8"))["violations"]}
    corrected = pos | (mut - pos)

    ab = json.loads((AB / "scoring/result.json").read_text(encoding="utf-8"))["runs"]
    coba_pred = {k for k, v in json.loads((COBA / "coba_predictions_1023.json").read_text(encoding="utf-8")).items() if v}
    coba_cost = json.loads((COBA / "receipt.json").read_text(encoding="utf-8"))["cost_usd"]

    arms = {
        "DeepSeek + 通用 prompt（修复前）": [candidates(p / "report.json") for p in
            (PILOT / "run", PILOT / "run_r2", PILOT / "run_r3", KSCAN / "run_r4", KSCAN / "run_r5", KSCAN / "run_r6")],
        "DeepSeek + 通用 prompt（修复后）": [candidates(POST / f"run_r{i}/report.json") for i in range(1, 7)],
        "DeepSeek + AgentSuite 专用 prompt": [set(ab[f"specialized_r{i}"]["overall"]["tp_ids"])
            | set(ab[f"specialized_r{i}"]["overall"]["fp_ids"]) for i in (1, 2, 3)],
        "Gemini 2.5 Pro + 通用 prompt": [candidates(GEM / f"run_r{i}/report.json") for i in (1, 2, 3)],
        "COBA 完整 pipeline": [coba_pred & scope],
    }
    arms["DeepSeek + AgentSuite 专用 prompt"] = [{strip(x) for x in s} for s in arms["DeepSeek + AgentSuite 专用 prompt"]]

    L, a = [], None
    L.append("# ACEBench-102 全臂对比矩阵")
    L.append("")
    L.append("> 日期：2026-08-18")
    L.append("> 数据：AgentSuite ACEBench 公开平衡人工子集 102 条（51 issue / 51 non-issue）")
    L.append("> 性质：标签已解封的开发集对比，不是盲测")
    L.append("")
    L.append("五个实验臂全部在同一批 102 条上测量，用同一个计分口径。COBA 一臂是我们本地复现其公开 pipeline 得到的逐条预测，不是引用其论文报告值。")
    L.append("")

    L.append("## 怎么读下面的表")
    L.append("")
    L.append("**两把尺子。** 原 AgentSuite 标签认定 102 条里有 51 条缺陷。变异探针又机械证明了另外 12 条也有缺陷"
             "（把纬度 34.0522 改成 1033.0522，官方评测器照样判对，说明这些参数的取值根本不参与比较），"
             "而这 12 条人工都标为无问题。把它们计入后得到 63 个阳性，即“机械修正标签”。"
             "设两把尺子是因为：只用原标签时，一个系统发现了那 12 条真缺陷反而会被记成假阳。"
             "修正口径只存在于本地，不能与任何已发表数字并列。")
    L.append("")
    L.append("**两个 F1。** 同一臂重复跑 N 次：单跑中位 F1 是每次各算一个 F1 取中位数，回答“只跑一次大概拿到什么”；"
             "并集 F1 是 N 次结果合并、任意一次报过即算报出，回答“愿意跑 N 次最多拿到什么”。"
             "并集召回必然更高，假阳也会累加。COBA 一栏没有并集，因为只跑了一次。")
    L.append("")
    for label, positive in (("原 AgentSuite 标签", pos), ("机械修正标签（+12 条 evaluator 缺陷）", corrected)):
        L.append(f"## 口径一：{label}" if positive is pos else f"## 口径二：{label}")
        L.append("")
        L.append("| 实验臂 | 跑数 | 单跑中位 TP | FP | P | R | F1 | 并集 TP | FP | F1 |")
        L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for name, runs in arms.items():
            per = [metrics(r, positive, scope) for r in runs]
            med = [st.median([x[k] for x in per]) for k in range(5)]
            utp, ufp, _, _, uf1 = metrics(set().union(*runs), positive, scope)
            union = f"{utp} | {ufp} | {uf1:.3f}" if len(runs) > 1 else "— | — | —"
            L.append(f"| {name} | {len(runs)} | {med[0]:g} | {med[1]:g} | {med[2]:.3f} | {med[3]:.3f} | "
                     f"**{med[4]:.3f}** | {union} |")
        L.append("")
        L.append("")

    L.append("## 成本")
    L.append("")
    L.append("| 实验臂 | 模型 | 102 条一跑的量 | 实测花费 | 需要模型轨迹 |")
    L.append("|---|---|---|---|---|")
    tp_, tc_ = 0, 0
    for i in range(1, 7):
        p, c = tokens(POST / f"run_r{i}/report.json")
        tp_ += p; tc_ += c
    gp, gc = 0, 0
    for i in (1, 2, 3):
        p, c = tokens(GEM / f"run_r{i}/report.json")
        gp += p; gc += c
    idle = tp_/6/1e6*1.5 + tc_/6/1e6*4.5
    coba102 = coba_cost/1023*102*7.2
    L.append(f"| DeepSeek + 通用（修复后） | deepseek-v4-flash thinking | 输入 {tp_//6:,} / 输出 {tc_//6:,} token | **{idle:.2f} 元**（空闲时段） | 否 |")
    L.append(f"| Gemini + 通用 | gemini-2.5-pro | 输入 {gp//3:,} / 输出 {gc//3:,} token | 约 ${(gp/3/1e6*1.25 + gc/3/1e6*10):.2f} | 否 |")
    L.append(f"| COBA 完整 pipeline | gemini-2.5-pro | 1023 条全量 | **${coba_cost}** = {coba_cost*7.2:.0f} 元（合 102 条 {coba102:.2f} 元） | **是** |")
    L.append("")
    L.append("DeepSeek V4 Flash 按官方价目：输入未命中 1.5 元/M（空闲时段）、输出 4.5 元/M（空闲时段），高峰时段翻倍。"
             "我们六跑均在空闲时段、每跑全新缓存（`cache_hits=0`），故输入全部按未命中计价。美元按 7.2 折算，仅用于对照。")
    L.append("")
    L.append("| 对比 | 我们 | COBA | 比值 |")
    L.append("|---|---:|---:|---|")
    L.append(f"| 102 条单跑 | {idle:.2f} 元 | {coba102:.2f} 元 | 我们便宜 **{coba102/idle:.1f}×** |")
    L.append(f"| 我们六跑并集 vs 其单跑 | {idle*6:.2f} 元 | {coba102:.2f} 元 | 仅贵 **{idle*6/coba102:.2f}×** |")
    L.append(f"| 1023 条全量单跑 | {idle*1023/102:.0f} 元 | {coba_cost*7.2:.0f} 元 | 我们便宜 **{coba_cost*7.2/(idle*1023/102):.1f}×** |")
    L.append("")
    L.append(f"因此“并集要六倍成本”是有误导性的表述：六倍的是一个便宜五倍的基数。实际账面是——"
             f"我们跑六次 {idle*6:.2f} 元得到 F1 .907，COBA 跑一次 {coba102:.2f} 元得到 .863，多花约两成钱多拿 4.4 个点。"
             f"真正的论点不是“我们会用并集”，而是同等预算下我们能跑更多次：COBA 若也跑六次需约 {coba102*6:.0f} 元。")
    L.append("")
    L.append("### 轨迹成本：不在上表内，但确实存在")
    L.append("")
    L.append("COBA 的 pipeline 以模型轨迹为输入，不能脱离轨迹运行。AgentSuite 公开了 30 个模型 × 1023 条轨迹，"
             "我们下载是免费的，但这笔生成费用由他人支付，且未计入其审计成本。")
    L.append("")
    L.append("量级估算（**估算，非实测**）：轨迹文件的 `system` 字段为空，只存了用户消息与助手回复，"
             "因此生成时的真实输入远大于存档内容——它还包含 ACEBench 约 9,000 字符的 agent system prompt 与全部工具 schema。"
             "按我们实测同类 prompt 的 Gemini 用量（约 3,000 输入 token/条）与其 `sampling_params.max_tokens=1200` 推算，"
             "1023 条约需 3.1M 输入 + 至多 1.2M 输出，按 $1.25/M 与 $10/M 计约 **$16**，"
             "与运行一次 COBA 审计本身（$17.62）同一量级。按 30 个模型计则是数十倍。")
    L.append("")
    L.append("我们的审计不需要任何模型跑过该 benchmark，这一项为零。")
    L.append("")

    ours = set().union(*arms["DeepSeek + 通用 prompt（修复后）"])
    coba_s = coba_pred & scope
    our_fp, coba_fp = sorted(ours - pos), sorted(coba_s - pos)
    both = sorted(set(our_fp) & set(coba_fp))
    VERDICT = {
        "normal_single_turn_single_function::59": "事实成立：题面自身日期矛盾（当前时间 7/14，却含 7/15 会话），标答把越界数据纳入分析",
        "normal_single_turn_single_function::91": "事实成立 + 机械证据：`time` 为空、`assessmentDate` 枚举含两个合法 June，evaluator 拒绝任何等价替代写法",
        "normal_multi_turn_user_switch::11_1": "事实成立：用户明确要 digital map，工具 schema 无对应字段，标答改填未表态选项",
        "normal_single_turn_parallel_function::1": "事实成立 + 机械证据：标答把余额当存款额，省略该参数会被 evaluator 拒绝",
        "normal_preference::34": "事实成立：profile 记录两项饮食偏好，标答只保留一项，该字段无 enum 限制",
        "normal_atom_bool::33": "事实成立 + 机械证据：标答填入用户未提及的三个开关，且这些取值 evaluator 根本不检查",
        "normal_atom_object_deep::38": "**我们误报**：`penalty` 是必填字段，『same-day 不被允许』使 0 成为唯一站得住的填法，且 evaluator 不评分该字段",
        "normal_multi_turn_user_adjust::37_2": "**我们误报**：比较操作对称，模型自身在同一跑内也写了 reference is otherwise aligned，属低置信度犹豫（仅 1/6 跑）",
        "normal_atom_number::5": "COBA 独有，我们未报；未核验",
    }
    L.append("## 假阳分析：两个系统在同样的题上『犯错』")
    L.append("")
    L.append(f"我们（六跑并集）{len(our_fp)} 条，COBA（1 跑）{len(coba_fp)} 条，**重合 {len(both)} 条**。")
    L.append("")
    L.append("| 条目 | 我们 | COBA | 逐条核验结论 |")
    L.append("|---|:--:|:--:|---|")
    for s in sorted(set(our_fp) | set(coba_fp)):
        L.append(f"| `{s}` | {'✓' if s in our_fp else '—'} | {'✓' if s in coba_fp else '—'} | {VERDICT.get(s, '未核验')} |")
    L.append("")
    L.append("两个系统模型不同、prompt 不同、输入契约不同（COBA 消费模型轨迹，我们不需要），却在 6 条相同条目上被判为假阳。"
             "我们已对这 6 条逐条核对原始题面、标答与工具 schema，其中 5 条的判词事实成立。"
             "COBA 独立地报出同样 5 条，这削弱了『我们的系统有系统性偏差』这一解释，指向参照标签本身。")
    L.append("")

    L.append("## 漏检对比")
    L.append("")
    L.append(f"- COBA 漏检 {len(pos - coba_s)} 条：{', '.join('`'+x+'`' for x in sorted(pos - coba_s))}")
    L.append(f"- 我们（六跑并集）漏检 {len(pos - ours)} 条：{', '.join('`'+x+'`' for x in sorted(pos - ours))}")
    L.append("")
    L.append("双方都漏掉的：" + (", ".join('`'+x+'`' for x in sorted((pos - coba_s) & (pos - ours))) or "无"))
    L.append("")
    L.append("我们仅剩的两条漏检都属于『schema 描述文字本身含混』——缺陷不在标答里，而在某一个构件自己的措辞中。"
             "当前架构的检查全部围绕跨构件一致性设计，对这一类没有对应机制。")
    L.append("")

    L.append("## evaluator 盲区：两个系统都基本看不见")
    L.append("")
    L.append(f"变异探针机械证明了 {len(mut)} 条 evaluator 缺陷（数值与布尔参数的取值完全不参与比较）。")
    L.append("")
    L.append(f"- COBA 命中 {len(mut & coba_s)}/{len(mut)}")
    L.append(f"- 我们语义层命中 {len(mut & ours)}/{len(mut)}")
    L.append("")
    L.append("两边的命中都是语义层碰巧撞上，不是因为检测到了评测器问题。只有执行变异重放能系统性发现这一类，"
             "而两个系统的语义架构都不做这件事。这是目前唯一确定性领先的方向。")
    L.append("")

    L.append("## 我们的不足")
    L.append("")
    L.append("1. **单跑落后。**原标签口径下 COBA 单跑 F1 .863，我们修复后单跑中位 .846。"
             "超过它的 .907 来自六跑并集，而并集是 COBA 同样可以使用的通用手段——"
             "只是在同等预算下我们能跑更多次（见成本一节）。")
    L.append("2. **prompt 更弱。**同模型同输入下，AgentSuite 的专用 prompt 中位 TP 45、我们的通用 prompt 41，"
             "三次配对差 +4/+6/+4 方向一致。我们的优势从来不在 prompt 上。")
    L.append("3. **换更强模型没有直接收益。**Gemini + 我们的 prompt 单跑中位 F1 低于 DeepSeek；"
             "其假阳中有 14/25 由我们自己的输入表示缺陷造成，修复后需重跑才能引用。")
    L.append("4. **对『构件自身措辞含混』无检查。**仅剩的两条漏检都属于这一类。")
    L.append("5. **运行不稳定。**修复后六跑 TP 全距 6（38–44），任何单次结果都不能代表系统能力。")
    L.append("")
    L.append("## 不能说")
    L.append("")
    L.append("- 不能说复现值 .863 等于其论文的 .874：模型 id 被替换（其 `google/gemini-2.5-pro-thinking-on` 非 OpenRouter 合法 id，"
             "thinking 预算未知），且未启用 `--rebuttal`。")
    L.append("- 不能说 .907 优于 COBA：跑数与成本不对等。")
    L.append("- 不能把机械修正标签下的分数与任何论文报告值并列：该口径只存在于本地。")
    L.append("- 这 51 个阳性全部出自 COBA 自己的候选池，该子集对其存在结构性选择优势。")
    L.append("")
    L.append("## 一处附带发现")
    L.append("")
    L.append("COBA 自带的计分函数在本次复现中只把 102 条人工标注里的 **74 条**（37 阳 / 37 阴）纳入混淆矩阵，"
             "另外 28 条因其内部两套 ID 构造方式不一致而被静默排除（102 条全部存在于其输出 CSV 中，并非数据缺失）。"
             "其自报 F1 为 .853；我们用完整 102 条重算为 .863。上表所有 COBA 数字均为后者。")
    L.append("")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"written {OUT} ({OUT.stat().st_size} bytes)")
    return 0


raise SystemExit(main())
