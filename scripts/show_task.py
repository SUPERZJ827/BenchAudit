#!/usr/bin/env python3
"""Hand-verification helper: gather everything needed to check one Lite task's
findings in one place.

For a given absolute_id it prints:
  1. the task description,
  2. every rubric, tagged with the detector verdict the scan gave it
     (已确认 / 候选 / -) so you see which ones need checking,
  3. the LOCAL paths of the real input files (downloaded from HF),
  4. a short content preview of each input so you can eye-ball it.

Findings come from reports/lite_pilot/<id>.json (the scan output); task text +
rubrics + input files are resolved via auditor_agent's existing loaders.

Usage:
  python scripts/show_task.py 33
  python scripts/show_task.py 33 --full   # dump full input contents, not a preview
"""
import importlib.util, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
_a = importlib.util.spec_from_file_location("aa", REPO / "scripts" / "auditor_agent.py")
aa = importlib.util.module_from_spec(_a); _a.loader.exec_module(aa)
from benchcore.file_reader import read_file


def verdicts_by_rubric(aid):
    """Map rubric text -> list of '<detector>:<status>' from the saved scan."""
    f = REPO / "reports" / "lite_pilot" / f"{aid}.json"
    if not f.exists():
        return {}, None
    d = json.loads(f.read_text(encoding="utf-8"))
    m = {}
    for x in d.get("report", {}).get("findings", []):
        m.setdefault(x.get("rubric", ""), []).append(
            f"{x.get('detector')}:{x.get('status')}")
    return m, d.get("summary", {})


def main():
    if len(sys.argv) < 2:
        print("usage: python scripts/show_task.py <absolute_id> [--full]"); return
    aid = int(sys.argv[1])
    full = "--full" in sys.argv

    item = aa.load_hf_item(aid)
    vmap, summ = verdicts_by_rubric(aid)

    print(f"===== id={aid} " + (f"({summ['persona']}, {summ['diff']}, "
          f"{summ['task_type']})" if summ else "") + " =====")
    print("\n[TASK]\n" + item["task"].strip())

    print(f"\n[RUBRICS]  ({len(item['rubrics'])} total; "
          "★=有 finding，核实这些)")
    for i, r in enumerate(item["rubrics"], 1):
        tags = vmap.get(r, [])
        mark = "★ " + ",".join(tags) if tags else "  -"
        print(f" {i:>2}. [{mark}]\n     {r}")

    print(f"\n[INPUT FILES]  ({len(item['inputs'])} 个，本地路径可直接打开)")
    for p in item["inputs"]:
        print(f"\n  ● {p}")
        try:
            txt = read_file(p, 20000 if full else 1500)
        except Exception as e:
            txt = f"<读取失败: {type(e).__name__}: {e}>"
        print("    " + txt.replace("\n", "\n    "))


if __name__ == "__main__":
    main()
