#!/usr/bin/env python3
"""Answer MMLU-Redux MCQs with several models, for the ranking-impact experiment.

Each model answers all items zero-shot; we record per-item correctness plus the
MMLU-Redux error_type label, so ranking_impact_analysis.py can later compare
rankings on the full set vs. with defective items removed.

Per-model results go to reports/ranking_impact/answers/<slug>.jsonl (one line per
item), resumable: already-answered ids are skipped, so a rerun never re-pays for
work already done. Cost control: openrouter models are billed; keep to cheap
models and use --limit to pilot before a full run.

Usage:
  mmlu_answer_models.py --models "deepseek,openrouter:meta-llama/llama-3.1-8b-instruct" [--limit N] [--workers 8]
"""
from __future__ import annotations

import argparse, json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from benchcore.llm_client import LLMClient, LLMConfig, load_llm_config

DATA = REPO / "experiments/mmlu_redux_pilot1000.jsonl"
OUTDIR = REPO / "reports/ranking_impact/answers"
LETTERS = ["A", "B", "C", "D"]

SYSTEM = ('You are answering a 4-option multiple-choice question. Reply with ONLY a '
          'JSON object {"answer":"X"} where X is exactly one of A, B, C, D.')


def build_prompt(row: dict) -> str:
    opts = "\n".join(f"{L}. {c}" for L, c in zip(LETTERS, row["choices"]))
    return f'Question: {row["question"]}\n\nOptions:\n{opts}\n\nWhich option is correct?'


def parse_letter(resp: dict) -> str | None:
    raw = str(resp.get("answer", "")) if isinstance(resp, dict) else str(resp)
    m = re.search(r"[ABCD]", raw.upper())
    return m.group(0) if m else None


def make_client(spec: str) -> tuple[str, LLMClient]:
    """spec: 'deepseek' or 'openrouter:<model-id>'. Returns (slug, client)."""
    if spec == "deepseek":
        cfg = load_llm_config(str(REPO / "configs/llm_deepseek.json"))
        cfg.cache_path = None
        return "deepseek", LLMClient(cfg)
    if spec.startswith("openrouter:"):
        model = spec.split(":", 1)[1]
        base = load_llm_config(str(REPO / "configs/llm_openrouter_gpt55.json"))
        cfg = LLMConfig(**{**base.__dict__})
        cfg.model = model
        cfg.cache_path = None
        slug = model.replace("/", "__").replace(":", "_")
        return slug, LLMClient(cfg)
    raise ValueError(f"bad model spec: {spec}")


def answer_model(spec: str, rows: list[dict], workers: int) -> dict:
    slug, client = make_client(spec)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = OUTDIR / f"{slug}.jsonl"
    done = {json.loads(l)["id"] for l in out.read_text().splitlines()} if out.exists() else set()
    todo = [r for r in rows if r["id"] not in done]
    print(f"[{slug}] {len(done)} done, {len(todo)} to answer", flush=True)
    fh = out.open("a", encoding="utf-8")
    lock = __import__("threading").Lock()
    errors = {"n": 0}

    def one(row: dict):
        try:
            resp = client.chat_json(SYSTEM, build_prompt(row))
            pred = parse_letter(resp)
        except Exception as e:
            errors["n"] += 1
            if errors["n"] <= 3:
                print(f"[{slug}] err {row['id']}: {type(e).__name__}: {str(e)[:80]}", flush=True)
            pred = None
        rec = {"id": row["id"], "gold": row["gold"], "pred": pred,
               "correct": (pred == row["gold"]) if pred else False,
               "error_type": row["metadata"].get("error_type", "ok"),
               "subject": row["metadata"].get("subject")}
        with lock:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh.flush()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, todo))
    fh.close()
    recs = [json.loads(l) for l in out.read_text().splitlines()]
    acc = sum(r["correct"] for r in recs) / len(recs) if recs else 0.0
    print(f"[{slug}] DONE {len(recs)} answered, overall acc={acc:.3f}, "
          f"parse/api fails={errors['n']}", flush=True)
    return {"slug": slug, "spec": spec, "answered": len(recs), "acc": round(acc, 4),
            "fails": errors["n"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True, help="comma-separated specs")
    ap.add_argument("--limit", type=int, default=0, help="0 = all items")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    rows = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines()]
    if args.limit:
        rows = rows[:args.limit]
    specs = [s.strip() for s in args.models.split(",") if s.strip()]
    print(f"answering {len(rows)} items with {len(specs)} models\n")
    summary = []
    for spec in specs:
        t0 = time.time()
        try:
            res = answer_model(spec, rows, args.workers)
            res["secs"] = round(time.time() - t0, 1)
            summary.append(res)
        except Exception as e:
            import traceback; traceback.print_exc()
            summary.append({"spec": spec, "error": f"{type(e).__name__}: {e}"})
    (OUTDIR.parent / "answer_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n==== SUMMARY ====")
    for s in summary:
        if "error" in s:
            print(f"  {s['spec']}: ERROR {s['error'][:80]}")
        else:
            print(f"  {s['slug']:<45} acc={s['acc']:.3f} n={s['answered']} fails={s['fails']} {s['secs']}s")


if __name__ == "__main__":
    main()
