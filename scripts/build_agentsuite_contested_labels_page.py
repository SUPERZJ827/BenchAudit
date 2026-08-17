#!/usr/bin/env python3
"""Build the contested-annotation review page from frozen ACEBench artifacts."""
from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path

REPO = Path("/home/zhoujun/llmdata/after623")
AS = Path("/home/zhoujun/llmdata/AgentSuite-main")
MAT = REPO / "reports/agentsuite_acebench_102_solver_role_dev_20260816/materialized/audit_input.jsonl"
PILOT = REPO / "reports/agentsuite_acebench_102_deepseek_thinking_pilot_20260816"
KSCAN = REPO / "reports/agentsuite_acebench_102_thinking_k_scan_20260817"
OUT = REPO / "docs/research/acebench_contested_labels.html"

RUNS = [("R1", PILOT / "run/report.json"), ("R2", PILOT / "run_r2/report.json"),
        ("R3", PILOT / "run_r3/report.json"), ("R4", KSCAN / "run_r4/report.json"),
        ("R5", KSCAN / "run_r5/report.json")]

# Consolidated statements are written by hand from the run transcripts; every
# quoted value below is injected from the frozen artifacts, never retyped.
DISPUTED = [
    ("normal_single_turn_single_function::91", "标答编造无来源的标识符，并锁定一个推不出的年份", """
题面只说评估“conducted this June”，而本题<b>没有提供当前时间</b>（<code>time</code> 字段为空）。
schema 的 <code>assessmentDate</code> 是四选一枚举，其中 <code>2021-06</code> 与 <code>2022-06</code> 都是合法的 June，
标答直接锁定 <code>2022-06</code>，从给定材料无法推出。
<code>siteId</code> 是自由字符串，题面没有给出任何站点编号，也没有可查的注册表，
标答自行编造了 <code>"Great Wall Beijing"</code>。"""),

    ("normal_atom_bool::33", "标答填入用户从未提及的三个开关，且与用户给出的数据相反", """
题面通篇没有出现 <code>include_age_group_analysis</code>、<code>include_device_usage</code>、
<code>include_location_analysis</code> 这三个可选开关，标答却把它们<b>全部设为 false</b>。
而用户提供的 engagement data 恰恰强调了年龄段（25–34）、地区（urban areas）和设备（mobile devices）三个维度——
关掉这三项分析，与用户的画像请求方向相反。"""),

    ("normal_single_turn_parallel_function::1", "标答把账户余额当成了存款金额", """
题面只说“checking account with $5000 balance”和“made a deposit on January 1st, 2021”，
<b>从未说明这笔存款的金额</b>。标答在 <code>recent_activities[0].amount</code> 填入 <code>5000</code>，
是把余额直接当作存款额的推断。<code>amount</code> 在 schema 中是可选字段，本可以不填。"""),

    ("normal_multi_turn_user_switch::11_1", "工具无法表达用户的明确请求，标答改填了用户没表过态的选项", """
系统先问用户是否需要导航选项，用户明确回答“I would also like a <b>digital map</b> for navigation”。
但 <code>MuseumExplorer_getExhibitInfo</code> 的 <code>navigationOptions</code> 只有
<code>guidedTour</code> 和 <code>mustSeeExhibits</code> 两个字段，<b>没有任何字段能表达数字地图</b>。
标答的处理是：丢掉用户明确提出的需求，同时填入用户从未表态的
<code>guidedTour: false</code> 和 <code>mustSeeExhibits: []</code>。"""),

    ("normal_single_turn_single_function::59", "题面自身日期矛盾，标答把越界数据纳入了分析范围", """
<code>time</code> 字段写明当前时间是 2021-07-14，用户却列出了一条 <b>7 月 15 日</b>的 TikTok 会话——
晚于“当前时间”。用户同时要求只分析 <b>6/14 至 7/14</b>。
标答一方面把 <code>analysisPeriod.endDate</code> 设为 <code>2021-07-14</code>，
另一方面把包括 7/15 在内的<b>全部四条会话</b>都放进了 <code>usagePatterns</code>。
而 <code>usagePatterns</code> 的 schema 只有 platform / timeSpent / sessionStart，<b>没有日期字段</b>，
所以越界的那条在调用里根本无法与其他会话区分。"""),

    ("normal_preference::34", "标答只保留了用户两项饮食偏好中的一项", """
用户 profile 明确记录“Set dietary preferences to include only <b>vegetarian and gluten-free</b> options”，
题面也说“according to my dietary and allergic preferences”。
标答的 <code>UserDietaryPreference</code> 只填了 <code>"Gluten-Free"</code>，丢掉了 vegetarian。
该字段在 schema 中是<b>自由字符串、没有 enum 限制</b>，并不存在“只能选一个”的约束。"""),
]

WITHDRAWN = ("normal_atom_object_deep::38", "已撤回：这条是我们判断有误", """
我们报的是：对三条“当日取消不被允许”的预订，标答把 <code>sameDay.penalty</code> 填成了 0，
而题面未给出该数值。但 <code>allowed: false</code> 时罚金本就没有实际意义，填 0 是合理约定。
人工复核认定<b>这条属于我们的误报</b>，不列为标注争议。""")

CONTROLS = [
    ("normal_single_turn_single_function::9",
     "标答编造 <code>sourceId: \"1\"</code> 与 <code>accessProtocol: \"HTTPS\"</code>，题面均未提供。",
     """<b>我们检出了，但只在第五跑。</b>前四次独立运行全部漏检，R5 才报出，理由与作者一致：
标答的 <code>sourceId</code> 与 <code>accessProtocol</code> 在题面中没有任何来源。
这条与 <code>normal_single_turn_single_function::91</code> 的 <code>siteId</code> 是同一机制，
但那一条被作者标为无问题。"""),
    ("normal_atom_enum::22",
     "标答填入用户未要求的可选参数 <code>outputDetail: \"Summary\"</code>。",
     """<b>我们从未因为真正的原因报出这一条。</b>
在全部有效运行（V2、A0/A1/A2、challenger、prompt A/B、thinking 五跑）中，它<b>一次都没有被报出</b>。
唯一一次被标记发生在<b>已作废的 V1 运行</b>，而那次给出的理由是
“the reference solution references a non-existent function”“no such function exists in the provided context”——
这三条理由全部错误：该函数确实存在于工具列表中，模型之所以看不到它，是 V1 上下文截断缺陷所致，
也正是 V1 被作废的原因。
按题目级计分那次算命中，按理由核对则是<b>用错误的理由碰对了题号</b>。"""),
]

PAIRS = [
    ("标答编造无来源的标识符",
     [("normal_single_turn_single_function::9", 'sourceId: "1"')],
     [("normal_single_turn_single_function::91", 'siteId: "Great Wall Beijing"')]),
    ("标答填入用户未要求的可选参数",
     [("normal_atom_enum::22", 'outputDetail: "Summary"')],
     [("normal_atom_bool::33", "三个 include_* 开关设为 false"),
      ("normal_multi_turn_user_switch::11_1", "guidedTour: false, mustSeeExhibits: []")]),
]


def load_jsonl(p): return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l]
def esc(s): return html.escape(str(s))
def j(v): return esc(json.dumps(v, ensure_ascii=False, indent=2))


def main() -> int:
    items = {r["id"]: r for r in load_jsonl(MAT)}
    issues = {}
    for r in csv.DictReader((AS / "ACEBench/acebench_issues.csv").open(encoding="utf-8")):
        issues.setdefault(r["task_id"], []).append(r)

    findings = {}
    for name, path in RUNS:
        for v in json.loads(path.read_text(encoding="utf-8"))["violations"]:
            if (v.get("detection_method") == "llm_cross_artifact_consistency"
                    and v.get("defect_scope", "substantive") not in {"presentation", "operational"}
                    and v.get("defect_type") != "llm_audit_failure"):
                findings.setdefault(v["item_id"], []).append((name, v))

    def official(short):
        task, tid = short.split("::")
        rows = issues.get(f"{task}_{tid}", []) + issues.get(tid, [])
        return rows[0] if rows else None

    def schemas(item):
        names = {re.sub(r"_\d+$", "", str(n)) for n in (item.get("reference_solution") or {})}
        out = []
        for e in item.get("available_functions") or []:
            b = e.get("function") if isinstance(e.get("function"), dict) else e
            if str(b.get("name", "")) in names:
                out.append(e)
        return out

    def card(short, headline, body, kind):
        item = items["agentsuite-ace::" + short]
        rows = findings.get("agentsuite-ace::" + short, [])
        runs = sorted({n for n, _ in rows})
        confs = [float(v["confidence"]) for _, v in rows if v.get("confidence") is not None]
        off = official(short)
        chip = ('<span class="chip chip--issue">作者判定：有问题</span>' if kind == "control"
                else '<span class="chip chip--ok">作者判定：无问题</span>')
        h = [f'<article class="exhibit{" exhibit--control" if kind=="control" else ""}'
             f'{" exhibit--withdrawn" if kind=="withdrawn" else ""}" id="{esc(short)}">']
        h.append('<header class="exhibit__head">')
        h.append(f'<h3 class="exhibit__id">{esc(short)}</h3>')
        h.append(f'<div class="exhibit__chips">{chip}')
        if runs:
            span = (f"{min(confs):.2f}–{max(confs):.2f}" if confs and min(confs) != max(confs)
                    else (f"{confs[0]:.2f}" if confs else "—"))
            h.append(f'<span class="chip chip--meta">{len(runs)}/5 跑报出 · 置信度 {span}</span>')
        if not runs:
            h.append('<span class="chip chip--miss">有效运行中从未报出</span>')
        h.append(f'<span class="chip chip--meta">{"在 COBA 候选清单内（人工 KEEP）" if off else "不在 COBA 候选清单内"}</span>')
        h.append("</div></header>")

        if kind == "control" and off:
            h.append('<div class="block"><div class="label">作者给出的问题理由</div>'
                     f'<blockquote class="official">{esc(off["issue_reason"])}</blockquote></div>')

        h.append(f'<div class="block"><div class="label">题面</div>'
                 f'<div class="task">{esc(item.get("task") or "(无)")}</div></div>')
        if item.get("time"):
            h.append(f'<div class="block"><div class="label">当前时间</div>'
                     f'<div class="inlinefact">{esc(item["time"])}</div></div>')
        elif short.endswith("::91"):
            h.append('<div class="block"><div class="label">当前时间</div>'
                     '<div class="inlinefact inlinefact--absent">未提供</div></div>')

        h.append('<div class="block"><div class="label">标答（Ground Truth）</div>'
                 f'<pre class="code"><code>{j(item.get("reference_solution"))}</code></pre></div>')

        cls = "finding" + (" finding--withdrawn" if kind == "withdrawn" else "")
        label = {"withdrawn": "复核结论", "control": "机制与我们的检出状态"}.get(kind, "我们的异议")
        if kind == "control":
            cls = "finding finding--control"
        h.append(f'<div class="{cls}"><div class="label label--flag">{label}</div>'
                 f'<p class="finding__headline">{headline}</p>'
                 f'<div class="finding__body">{body.strip()}</div></div>')

        h.append('<details class="fold"><summary>完整函数定义</summary>'
                 f'<pre class="code"><code>{j(schemas(item))}</code></pre></details>')
        if rows:
            seen, quotes = set(), []
            for n, v in rows:
                key = (v.get("message") or "")[:80]
                if key in seen:
                    continue
                seen.add(key)
                quotes.append(f'<li><span class="run">{esc(n)}</span>'
                              f'<span class="dtype">{esc(v.get("defect_type"))}</span>'
                              f'<span class="conf">{esc(v.get("confidence"))}</span>'
                              f'<p>{esc(v.get("message"))}</p></li>')
            h.append(f'<details class="fold"><summary>各跑原始判词（{len(quotes)} 条，去重后）</summary>'
                     f'<ul class="quotes">{"".join(quotes)}</ul></details>')
        h.append("</article>")
        return "\n".join(h)

    pair_rows = []
    for mech, pos, neg in PAIRS:
        pos_html = "".join(f'<div class="pairitem"><a href="#{esc(s)}">{esc(s.split("::")[-1] if False else s)}</a>'
                           f'<span>{v}</span></div>' for s, v in pos)
        neg_html = "".join(f'<div class="pairitem"><a href="#{esc(s)}">{esc(s)}</a>'
                           f'<span>{v}</span></div>' for s, v in neg)
        pair_rows.append(f'<tr><th scope="row">{esc(mech)}</th><td>{pos_html}</td><td>{neg_html}</td></tr>')

    body = []
    body.append(f'<section class="intro">')
    body.append('<h2>这一页是什么</h2>')
    body.append('<p>AgentSuite 为 ACEBench 公开了一份 102 条的人工核验子集，51 条标为有缺陷、51 条标为无缺陷，'
                'COBA 与我们都以它作为评测基准。下面 6 条是<b>作者判定“无问题”</b>、但我们的审计器在五次独立运行中'
                '反复报出的条目。每条都给出作者的判定、原始题面、作者提供的标答，以及我们的具体异议。</p>')
    body.append('<p class="note">全部题面、标答与函数定义均由冻结产物直接注入，未经改写；'
                '“我们的异议”是对五次运行判词的人工整合，原始判词可在每条末尾展开核对。</p>')
    body.append('</section>')

    body.append('<section class="pairs"><h2>三组同机制、相反标签</h2>'
                '<p>最值得注意的不是单条判断分歧，而是<b>同一种缺陷机制在不同条目上得到了相反的标注</b>。</p>'
                '<div class="tablewrap"><table><thead><tr><th scope="col">缺陷机制</th>'
                '<th scope="col">作者判定「有问题」</th><th scope="col">作者判定「无问题」</th></tr></thead>'
                f'<tbody>{"".join(pair_rows)}</tbody></table></div></section>')

    body.append('<section><h2>争议条目</h2>')
    for short, headline, text in DISPUTED:
        body.append(card(short, headline, text, "disputed"))
    body.append('</section>')

    body.append('<section><h2>对照：作者判定「有问题」的同机制条目</h2>'
                '<p>这两条的缺陷机制与上面若干条相同，但被标为缺陷，并附有作者写下的理由。</p>')
    for short, headline, note in CONTROLS:
        body.append(card(short, headline, note, "control"))
    body.append('</section>')

    body.append('<section><h2>我们撤回的一条</h2>')
    body.append(card(WITHDRAWN[0], WITHDRAWN[1], WITHDRAWN[2], "withdrawn"))
    body.append('</section>')

    body.append('<section class="caveat"><h2>该怎么读这些结论</h2>'
                '<p>“同机制”是我们的判断。标注者可能持有未写进 CSV 的判准——例如某种<b>材料性</b>门槛：'
                f'<code>outputDetail: "Summary"</code> 是一个实质取值，而把三个布尔开关设为 <code>false</code> '
                '更像无操作默认。这类区分是合理的，只是没有被记录下来，从公开材料里看不出来。</p>'
                '<p class="warn"><b>我们自己也不一致。</b><code>normal_atom_enum::22</code> 被作者标为缺陷，'
                '机制与 <code>normal_atom_bool::33</code>、<code>normal_multi_turn_user_switch::11_1</code> 相同，'
                '但我们的审计器<b>五跑全部漏检</b>了它。也就是说，在“标答填入用户未要求的可选参数”这一机制上，'
                '我们与标注者是<b>双向分歧</b>，而不是我们单方面更严格。这一条同样削弱了简单的“标注有错”结论。</p>'
                '<p>要把“标注存在内部不一致”坐实，需要向 AgentSuite 核对判准，或用更多同机制配对来支撑。'
                '目前是 3 组。人工标签文件只含 <code>is_issue</code> 一列，<code>issue_type</code> 在全部 102 条上均为空。</p>'
                '<p>此外，这 51 个阳性全部来自 COBA 自己的候选池，因此该子集对 COBA 存在结构性选择优势；'
                '上述 6 条中有 5 条<b>从未进入 COBA 的候选清单</b>，只有 <code>normal_preference::34</code> '
                '进入过并被人工判为 KEEP。</p></section>')

    css = CSS
    page = ('<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            '<title>ACEBench 标注争议</title>\n'
            f'<style>{css}</style>\n</head>\n<body>\n'
            '<div class="page">\n<header class="masthead">'
            '<p class="eyebrow">AgentSuite · ACEBench 102 条人工核验子集</p>'
            '<h1>标答里的六处争议</h1>'
            '<p class="standfirst">作者判定「无问题」，但五次独立审计反复指出同样的毛病</p>'
            '<p class="meta">2026-08-17 · 证据取自冻结运行 R1–R5 · '
            '标签源 <code>pipeline/human_labelled_ground_truth/ACEBench.csv</code></p>'
            '</header>\n<main>\n' + "\n".join(body) + '\n</main>\n</div>\n')
    OUT.write_text(page, encoding="utf-8")
    print(f"written {OUT} ({OUT.stat().st_size} bytes)")
    return 0


CSS = """
:root{
  --paper:#f2f4f5; --surface:#ffffff; --surface-2:#e9edef;
  --ink:#15191d; --ink-2:#3f4a53; --muted:#68737d;
  --rule:#d5dbdf; --rule-strong:#b9c2c8;
  --petrol:#0f5f66; --petrol-soft:#dceaeb;
  --brass:#8a6316; --brass-soft:#f3ebd8;
  --shadow:0 1px 2px rgba(20,30,35,.06),0 8px 24px -18px rgba(20,30,35,.5);
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Songti SC","Noto Serif CJK SC",Georgia,serif;
  --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI","PingFang SC","Noto Sans CJK SC","Microsoft YaHei",sans-serif;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --paper:#111517; --surface:#191e21; --surface-2:#222a2e;
    --ink:#e7ecee; --ink-2:#b9c4ca; --muted:#8b979e;
    --rule:#2a3338; --rule-strong:#3a464c;
    --petrol:#4fb3b8; --petrol-soft:#12312f;
    --brass:#d6ab5c; --brass-soft:#302713;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -20px rgba(0,0,0,.9);
  }
}
:root[data-theme="dark"]{
  --paper:#111517; --surface:#191e21; --surface-2:#222a2e;
  --ink:#e7ecee; --ink-2:#b9c4ca; --muted:#8b979e;
  --rule:#2a3338; --rule-strong:#3a464c;
  --petrol:#4fb3b8; --petrol-soft:#12312f;
  --brass:#d6ab5c; --brass-soft:#302713;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 28px -20px rgba(0,0,0,.9);
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:var(--sans);font-size:16px;line-height:1.65;
  -webkit-font-smoothing:antialiased}
.page{max-width:60rem;margin:0 auto;padding:clamp(1.5rem,4vw,4rem) clamp(1rem,4vw,2.5rem) 6rem}
.masthead{border-bottom:2px solid var(--ink);padding-bottom:1.75rem;margin-bottom:3rem}
.eyebrow{font-size:.75rem;letter-spacing:.14em;text-transform:uppercase;color:var(--petrol);
  margin:0 0 1rem;font-weight:600}
h1{font-family:var(--serif);font-size:clamp(2rem,5.5vw,3.1rem);line-height:1.1;margin:0;
  font-weight:600;letter-spacing:-.01em;text-wrap:balance}
.standfirst{font-family:var(--serif);font-size:clamp(1.05rem,2.2vw,1.3rem);color:var(--ink-2);
  margin:.9rem 0 0;max-width:44ch;text-wrap:balance}
.meta{font-size:.8rem;color:var(--muted);margin:1.4rem 0 0}
main{display:flex;flex-direction:column;gap:3.5rem}
section{display:flex;flex-direction:column;gap:1rem}
h2{font-family:var(--serif);font-size:1.5rem;margin:0;font-weight:600;letter-spacing:-.005em}
p{margin:0;max-width:68ch}
.note{font-size:.875rem;color:var(--muted);border-left:2px solid var(--rule-strong);padding-left:.9rem}
code{font-family:var(--mono);font-size:.86em;background:var(--surface-2);
  padding:.1em .35em;border-radius:3px}
.tablewrap{overflow-x:auto;border:1px solid var(--rule);border-radius:6px;background:var(--surface)}
table{border-collapse:collapse;width:100%;min-width:44rem;font-size:.9rem}
th,td{text-align:left;padding:.85rem 1rem;border-bottom:1px solid var(--rule);vertical-align:top}
thead th{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);
  font-weight:600;background:var(--surface-2)}
tbody th{font-weight:600;width:16rem;color:var(--ink)}
tbody tr:last-child th,tbody tr:last-child td{border-bottom:0}
.pairitem{display:flex;flex-direction:column;gap:.15rem;padding:.3rem 0}
.pairitem a{font-family:var(--mono);font-size:.8rem;color:var(--petrol);text-decoration:none;
  border-bottom:1px solid transparent}
.pairitem a:hover,.pairitem a:focus-visible{border-bottom-color:var(--petrol)}
.pairitem span{font-family:var(--mono);font-size:.78rem;color:var(--muted)}
.exhibit{background:var(--surface);border:1px solid var(--rule);border-radius:8px;
  box-shadow:var(--shadow);padding:clamp(1.1rem,3vw,1.75rem);
  display:flex;flex-direction:column;gap:1.25rem;scroll-margin-top:1.5rem}
.exhibit--control{border-left:3px solid var(--petrol)}
.exhibit--withdrawn{opacity:.82}
.exhibit__head{display:flex;flex-direction:column;gap:.7rem}
.exhibit__id{font-family:var(--mono);font-size:.95rem;margin:0;font-weight:600;
  color:var(--ink);word-break:break-all}
.exhibit__chips{display:flex;flex-wrap:wrap;gap:.4rem}
.chip{font-size:.72rem;letter-spacing:.04em;padding:.22rem .6rem;border-radius:999px;
  border:1px solid var(--rule-strong);color:var(--muted);white-space:nowrap}
.chip--ok{border-color:var(--rule-strong);color:var(--ink-2);background:var(--surface-2)}
.chip--miss{border-color:var(--brass);color:var(--brass);font-weight:600}
.chip--issue{background:var(--petrol);border-color:var(--petrol);color:var(--surface);font-weight:600}
:root:not([data-theme="light"]) .chip--issue{color:#0d1214}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .chip--issue{color:#0d1214}}
:root[data-theme="dark"] .chip--issue{color:#0d1214}
.label{font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);
  font-weight:600;margin-bottom:.45rem}
.label--flag{color:var(--brass)}
.block{display:block}
.task{font-family:var(--serif);font-size:1rem;line-height:1.7;color:var(--ink-2);
  white-space:pre-wrap;border-left:2px solid var(--rule-strong);padding-left:1rem}
.inlinefact{font-family:var(--mono);font-size:.85rem;color:var(--ink-2)}
.inlinefact--absent{color:var(--brass);font-weight:600}
.official{margin:0;font-family:var(--serif);font-size:1rem;line-height:1.7;color:var(--ink-2);
  border-left:2px solid var(--petrol);padding-left:1rem}
.code{margin:0;overflow-x:auto;background:var(--surface-2);border:1px solid var(--rule);
  border-radius:6px;padding:.9rem 1rem;font-family:var(--mono);font-size:.8rem;line-height:1.55}
.code code{background:none;padding:0;font-size:inherit}
.finding{background:var(--brass-soft);border:1px solid var(--brass);border-radius:6px;
  padding:1rem 1.15rem}
.finding--control{background:var(--petrol-soft);border-color:var(--petrol)}
.finding--control .label--flag{color:var(--petrol)}
.finding--withdrawn{background:var(--surface-2);border-color:var(--rule-strong)}
.finding--withdrawn .label--flag{color:var(--muted)}
.finding__headline{font-family:var(--serif);font-size:1.08rem;font-weight:600;margin:0 0 .5rem;
  color:var(--ink);text-wrap:balance}
.finding__body{font-size:.925rem;line-height:1.7;color:var(--ink-2)}
.finding__body code{background:rgba(0,0,0,.06)}
:root[data-theme="dark"] .finding__body code{background:rgba(255,255,255,.09)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) .finding__body code{background:rgba(255,255,255,.09)}}
.fold{border-top:1px solid var(--rule);padding-top:.85rem}
.fold summary{cursor:pointer;font-size:.8rem;letter-spacing:.06em;color:var(--petrol);
  font-weight:600;list-style:none;display:flex;align-items:center;gap:.45rem}
.fold summary::-webkit-details-marker{display:none}
.fold summary::before{content:"+";font-family:var(--mono);font-size:.95rem;line-height:1}
.fold[open] summary::before{content:"−"}
.fold summary:focus-visible{outline:2px solid var(--petrol);outline-offset:3px;border-radius:3px}
.fold[open] summary{margin-bottom:.85rem}
.quotes{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.9rem}
.quotes li{border-left:2px solid var(--rule-strong);padding-left:.9rem}
.quotes p{margin:.3rem 0 0;font-size:.875rem;color:var(--ink-2);max-width:none}
.run,.dtype,.conf{font-family:var(--mono);font-size:.72rem;margin-right:.6rem}
.run{color:var(--petrol);font-weight:600}
.dtype{color:var(--muted)}
.conf{color:var(--muted);font-variant-numeric:tabular-nums}
.caveat{border-top:1px solid var(--rule);padding-top:2rem}
.caveat p{color:var(--ink-2);font-size:.925rem}
.warn{border-left:3px solid var(--brass);padding-left:1rem}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

if __name__ == "__main__":
    raise SystemExit(main())
