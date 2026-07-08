"""Export Terminal-Bench 2.1 tasks and Harbor trial results for BenchAudit.

Examples:
  python scripts/export_terminal_bench21.py tasks \
    --repo /tmp/terminal-bench-2-1 \
    --out datasets/terminal_bench_2_1/tasks.jsonl

  python scripts/export_terminal_bench21.py harbor-trials \
    --job-url https://hub.harborframework.com/jobs/<job-id> \
    --out reports/terminal_bench_2_1_harbor_trials.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any


TRIAL_PATTERN = re.compile(
    r'\\"id\\":\\"([^\\"]+)\\".*?'
    r'\\"name\\":\\"([^\\"]+)\\".*?'
    r'\\"task_name\\":\\"([^\\"]+)\\".*?'
    r'\\"source\\":\\"([^\\"]+)\\".*?'
    r'\\"agent_name\\":\\"([^\\"]+)\\".*?'
    r'\\"agent_version\\":\\"([^\\"]+)\\".*?'
    r'\\"model_provider\\":\\"([^\\"]+)\\".*?'
    r'\\"model_name\\":\\"([^\\"]+)\\".*?'
    r'\\"reward\\":([0-9.]+|null).*?'
    r'\\"error_type\\":(null|\\"[^\\"]*\\").*?'
    r'\\"attempt\\":([0-9]+).*?'
    r'\\"n_attempts\\":([0-9]+).*?'
    r'\\"is_scored\\":(true|false)',
    re.S,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    tasks = sub.add_parser("tasks", help="Export Terminal-Bench task definitions to BenchAudit JSONL")
    tasks.add_argument("--repo", required=True, help="Path to terminal-bench-2-1 repository")
    tasks.add_argument("--out", required=True)
    tasks.add_argument("--limit", type=int)

    trials = sub.add_parser("harbor-trials", help="Fetch per-trial results from a public Harbor Hub job page")
    trials.add_argument("--job-url", required=True)
    trials.add_argument("--out", required=True)
    trials.add_argument("--pages", type=int, help="Override number of pages; otherwise inferred from page 1")
    trials.add_argument("--page-size", type=int, default=100)
    trials.add_argument("--raw-dir", help="Optional directory for raw HTML snapshots")
    return parser.parse_args()


def export_tasks(repo: Path, out: Path, limit: int | None) -> None:
    task_root = repo / "tasks"
    rows: list[dict[str, Any]] = []
    for task_dir in sorted(p for p in task_root.iterdir() if p.is_dir()):
        instruction_path = task_dir / "instruction.md"
        toml_path = task_dir / "task.toml"
        if not instruction_path.exists() or not toml_path.exists():
            continue
        instruction = instruction_path.read_text(encoding="utf-8", errors="replace").strip()
        task_toml = toml_path.read_text(encoding="utf-8", errors="replace")
        row = {
            "item_id": task_dir.name,
            "task": instruction,
            "context": {
                "task_toml": task_toml,
                "repo_path": str(task_dir),
                "has_tests": (task_dir / "tests").exists(),
                "has_environment": (task_dir / "environment").exists(),
                "has_solution": (task_dir / "solution").exists(),
            },
            "output_contract": {
                "type": "terminal_task",
                "instruction_files": ["instruction.md"],
                "task_config": "task.toml",
                "expected_artifacts": parse_artifacts(task_toml),
            },
            "evaluator": {
                "type": "terminal_bench_verifier",
                "verifier_timeout_sec": parse_float_field(task_toml, "timeout_sec", section="verifier"),
            },
            "metadata": {
                "benchmark": "terminal-bench-2-1",
                "category": parse_string_field(task_toml, "category"),
                "difficulty": parse_string_field(task_toml, "difficulty"),
                "allow_internet": parse_bool_field(task_toml, "allow_internet"),
                "docker_image": parse_string_field(task_toml, "docker_image"),
                "agent_timeout_sec": parse_float_field(task_toml, "timeout_sec", section="agent"),
                "verifier_timeout_sec": parse_float_field(task_toml, "timeout_sec", section="verifier"),
                "raw_task_toml_path": str(toml_path),
                "raw_instruction_path": str(instruction_path),
            },
            "raw": {
                "task_id": task_dir.name,
                "task_toml": task_toml,
                "instruction": instruction,
            },
        }
        rows.append(row)
        if limit is not None and len(rows) >= limit:
            break
    write_jsonl(out, rows)
    print(f"wrote {len(rows)} Terminal-Bench tasks to {out}")


def fetch_harbor_trials(job_url: str, out: Path, pages: int | None, page_size: int, raw_dir: Path | None) -> None:
    first_html = fetch_url(with_page(job_url, 1))
    total_pages = pages or parse_total_pages(first_html) or 1
    rows: list[dict[str, Any]] = []
    for page in range(1, total_pages + 1):
        html = first_html if page == 1 else fetch_url(with_page(job_url, page))
        if raw_dir:
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / f"page_{page}.html").write_text(html, encoding="utf-8")
        page_rows = parse_trial_rows(html)
        rows.extend(page_rows)
        print(f"page {page}/{total_pages}: {len(page_rows)} rows")
        if pages is None and len(page_rows) < page_size:
            break
    write_jsonl(out, rows)
    print(f"wrote {len(rows)} Harbor trial rows to {out}")


def fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def with_page(job_url: str, page: int) -> str:
    sep = "&" if "?" in job_url else "?"
    # Replace an existing page parameter if present.
    if re.search(r"([?&])page=\d+", job_url):
        return re.sub(r"([?&])page=\d+", rf"\1page={page}", job_url)
    return f"{job_url}{sep}page={page}"


def parse_trial_rows(html: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in TRIAL_PATTERN.findall(html):
        (
            trial_id,
            trial_name,
            task_name,
            source,
            agent_name,
            agent_version,
            model_provider,
            model_name,
            reward,
            error_type,
            attempt,
            n_attempts,
            is_scored,
        ) = match
        rows.append(
            {
                "trial_id": trial_id,
                "trial_name": trial_name,
                "task_id": task_name.removeprefix("terminal-bench/"),
                "task_name": task_name,
                "source": source,
                "agent": agent_name,
                "agent_version": agent_version,
                "model_provider": model_provider,
                "model": model_name,
                "reward": None if reward == "null" else float(reward),
                "error_type": None if error_type == "null" else error_type.strip('\\"'),
                "attempt": int(attempt),
                "n_attempts": int(n_attempts),
                "is_scored": is_scored == "true",
            }
        )
    return rows


def parse_total_pages(html: str) -> int | None:
    match = re.search(r'\\"total_pages\\":([0-9]+)', html)
    return int(match.group(1)) if match else None


def parse_string_field(text: str, field: str) -> str | None:
    match = re.search(rf"^{re.escape(field)}\s*=\s*\"([^\"]*)\"", text, re.M)
    return match.group(1) if match else None


def parse_bool_field(text: str, field: str) -> bool | None:
    match = re.search(rf"^{re.escape(field)}\s*=\s*(true|false)", text, re.M)
    if not match:
        return None
    return match.group(1) == "true"


def parse_float_field(text: str, field: str, section: str | None = None) -> float | None:
    scope = text
    if section:
        match = re.search(rf"^\[{re.escape(section)}\]\s*$", text, re.M)
        if not match:
            return None
        start = match.end()
        next_section = re.search(r"^\[", text[start:], re.M)
        end = start + next_section.start() if next_section else len(text)
        scope = text[start:end]
    match = re.search(rf"^{re.escape(field)}\s*=\s*([0-9.]+)", scope, re.M)
    return float(match.group(1)) if match else None


def parse_artifacts(text: str) -> list[str]:
    match = re.search(r"^artifacts\s*=\s*\[(.*?)\]", text, re.M | re.S)
    if not match:
        return []
    return re.findall(r'"([^"]+)"', match.group(1))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    if args.command == "tasks":
        export_tasks(Path(args.repo), Path(args.out), args.limit)
    elif args.command == "harbor-trials":
        fetch_harbor_trials(
            args.job_url,
            Path(args.out),
            args.pages,
            args.page_size,
            Path(args.raw_dir) if args.raw_dir else None,
        )


if __name__ == "__main__":
    main()

