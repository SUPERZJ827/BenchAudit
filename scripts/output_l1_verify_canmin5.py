#!/usr/bin/env python3
"""L1 output-correctness prototype (仓敏_5 welfare task).

Independently RE-COMPUTES the expected aggregates from the raw input forms, then
compares them to the values asserted by the rubrics / reference output. This
checks output content correctness objectively -- robust to layout -- and at the
same time verifies whether the rubric/reference values are themselves correct.
"""
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ATT = Path("/home/zhoujun/llmdata/after623/图片和附件")
FILES = ["0eea01c0f40c90b4_福利发放单 1.xlsx", "e8eeec2de731d599_福利发放单 2.xlsx"]

# benefit -> (person-column keyword, amount-column keyword)
BENEFITS = {
    "生日礼金": ("生日礼金人数", "生日礼金金额"),
    "季度奖励": ("季度奖励人数", "季度奖励金额"),
    "年终奖励": ("年终奖励人数", "年终奖励金额"),
}
# what the rubric / reference output claims (人数, 金额)
RUBRIC = {
    "生日礼金": (299, 58000),
    "季度奖励": (2446, 1237000),
    "年终奖励": (1871, 4178000),
}


def load(f):
    df = pd.read_excel(ATT / f, header=0)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def col(df, kw):
    for c in df.columns:
        if kw in c:
            return pd.to_numeric(df[c], errors="coerce")
    return pd.Series(dtype=float)


def main():
    dfs = [load(f) for f in FILES]
    print(f"输入: {len(dfs)} 个单据文件, 共 {sum(len(d) for d in dfs)} 条发放记录\n")
    print(f"{'福利类型':10} {'重算人数':>8} {'rubric人数':>10} {'重算金额':>12} {'rubric金额':>12}  判定")
    bad = 0
    for b, (pk, ak) in BENEFITS.items():
        ppl = int(sum(col(d, pk).sum() for d in dfs))
        amt = int(sum(col(d, ak).sum() for d in dfs))
        rp, ra = RUBRIC[b]
        ok = (ppl == rp) and (amt == ra)
        bad += 0 if ok else 1
        mark = "✅一致" if ok else "🔴不符!"
        print(f"{b:10} {ppl:>8} {rp:>10} {amt:>12} {ra:>12}  {mark}")
    print(f"\n结论: {'全部一致,参考值正确' if bad==0 else f'{bad} 项与重算不符 → 参考输出/rubric 期望值有误(或口径不同)'}")


if __name__ == "__main__":
    main()
