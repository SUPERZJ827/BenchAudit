"""Static contract audit for Terminal-Bench style tasks.

This is intentionally conservative: it emits review signals, not confirmed
defects. It checks whether instruction-level output path requirements align
with verifier/test path checks.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


APP_PATH_RE = re.compile(r"/app/[A-Za-z0-9._/\-]+")
NUMBERED_STEP_RE = re.compile(r"^\s*(\d+)[.)]\s+", re.M)
OUTPUT_VERBS_RE = re.compile(
    r"\b(save|write|create|generate|place|output|produce|store|include|"
    r"named|called|file named|file called|implementation in|solution in)\b",
    re.I,
)
INPUT_CONTEXT_RE = re.compile(
    r"\b(given|provided|located|available|already|input|database|do not modify|"
    r"usage|run|execute|verify|test|read from)\b",
    re.I,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Path to terminal-bench-2-1 repository")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--limit", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = Path(args.repo)
    findings = audit_repo(repo, args.limit)
    payload = {
        "benchmark": "terminal-bench-2-1",
        "repo": str(repo),
        "n_findings": len(findings),
        "findings": findings,
        "summary": summarize(findings),
    }
    write_json(Path(args.out_json), payload)
    write_markdown(Path(args.out_md), payload)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


def audit_repo(repo: Path, limit: int | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    task_dirs = sorted(p for p in (repo / "tasks").iterdir() if p.is_dir())
    for task_dir in task_dirs[:limit]:
        instruction_path = task_dir / "instruction.md"
        if not instruction_path.exists():
            continue
        instruction = instruction_path.read_text(encoding="utf-8", errors="replace")
        test_text = read_test_text(task_dir)
        instruction_paths = extract_paths(instruction)
        output_paths = extract_instruction_output_paths(instruction)
        test_exist_paths = extract_test_exists_paths(test_text)
        hidden = sorted(test_exist_paths - instruction_paths - created_test_paths(test_text))
        untested = sorted(output_paths - extract_paths(test_text))
        duplicate_steps = duplicate_numbered_steps(instruction)
        for path in hidden:
            findings.append(
                finding(
                    task_dir.name,
                    "hidden_test_path_contract",
                    "major",
                    0.7,
                    f"Verifier checks `{path}`, but the instruction does not mention this /app path.",
                    {
                        "path": path,
                        "instruction_paths": sorted(instruction_paths),
                        "test_exists_paths": sorted(test_exist_paths),
                    },
                )
            )
        for path in untested:
            if likely_input_path(path, instruction):
                continue
            findings.append(
                finding(
                    task_dir.name,
                    "instruction_output_may_be_untested",
                    "review",
                    0.45,
                    f"Instruction appears to require output `{path}`, but tests do not directly reference it.",
                    {
                        "path": path,
                        "instruction_output_paths": sorted(output_paths),
                        "test_paths": sorted(extract_paths(test_text)),
                    },
                )
            )
        if duplicate_steps:
            findings.append(
                finding(
                    task_dir.name,
                    "instruction_structure_issue",
                    "minor",
                    0.75,
                    f"Instruction has duplicated numbered step labels: {', '.join(duplicate_steps)}.",
                    {"duplicate_step_numbers": duplicate_steps},
                )
            )
    return findings


def read_test_text(task_dir: Path) -> str:
    chunks: list[str] = []
    for path in sorted((task_dir / "tests").rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".py", ".sh", ".sql", ".txt", ".json", ".yaml", ".yml"}:
            continue
        try:
            chunks.append(f"\n# FILE: {path.relative_to(task_dir)}\n{path.read_text(encoding='utf-8', errors='replace')}")
        except OSError:
            continue
    return "\n".join(chunks)


def extract_paths(text: str) -> set[str]:
    paths = {clean_path(match.group(0)) for match in APP_PATH_RE.finditer(text)}
    paths.update(extract_pathlib_join_paths(text).values())
    return {path for path in paths if path not in {"/app", "/app/"}}


def clean_path(path: str) -> str:
    return path.rstrip(".,;:)'\"`]")


def extract_instruction_output_paths(instruction: str) -> set[str]:
    paths: set[str] = set()
    for line in instruction.splitlines():
        line_paths = extract_paths(line)
        if not line_paths:
            continue
        if OUTPUT_VERBS_RE.search(line):
            paths.update(line_paths)
    return paths


def extract_test_exists_paths(test_text: str) -> set[str]:
    paths: set[str] = set()
    lines = test_text.splitlines()
    for index, line in enumerate(lines):
        for path in extract_paths(line):
            window = "\n".join(lines[index : index + 8])
            if ".exists(" in window or "exists()" in window or "test -f" in window or "assert_file_exists" in window:
                paths.add(path)
    path_vars = extract_pathlib_join_paths(test_text, include_vars=True)
    for var, path in path_vars.items():
        if re.search(rf"\b{re.escape(var)}\.exists\s*\(", test_text):
            paths.add(path)
    return paths


def created_test_paths(test_text: str) -> set[str]:
    paths: set[str] = set()
    lines = test_text.splitlines()
    for index, line in enumerate(lines):
        for path in extract_paths(line):
            window = "\n".join(lines[index : index + 5])
            if ".write_text(" in window or ".unlink(" in window or "touch " in window:
                paths.add(path)
    path_vars = extract_pathlib_join_paths(test_text, include_vars=True)
    for var, path in path_vars.items():
        if re.search(rf"\b{re.escape(var)}\.(write_text|unlink)\s*\(", test_text):
            paths.add(path)
    return paths


def extract_pathlib_join_paths(text: str, *, include_vars: bool = False) -> dict[str, str]:
    """Resolve simple pathlib assignments used in Terminal-Bench tests.

    Covers patterns like:
      app_dir = Path("/app")
      ars_file = app_dir / "ars.R"
    """
    roots: dict[str, str] = {}
    paths: dict[str, str] = {}
    for match in re.finditer(r"\b(\w+)\s*=\s*Path\(\s*['\"](/app[^'\"]*)['\"]\s*\)", text):
        var, root = match.groups()
        root = clean_path(root)
        roots[var] = root
        paths[var] = root
    assignments = list(re.finditer(r"\b(\w+)\s*=\s*(\w+)\s*/\s*['\"]([^'\"]+)['\"]", text))
    for _ in range(len(assignments) + 1):
        changed = False
        for match in assignments:
            var, base_var, child = match.groups()
            base = paths.get(base_var) or roots.get(base_var)
            if not base:
                continue
            value = f"{base.rstrip('/')}/{child.lstrip('/')}"
            if paths.get(var) != value:
                paths[var] = value
                changed = True
        if not changed:
            break
    for match in re.finditer(r"Path\(\s*['\"](/app[^'\"]*)['\"]\s*\)\s*/\s*['\"]([^'\"]+)['\"]", text):
        root, child = match.groups()
        key = f"__expr_{len(paths)}"
        paths[key] = f"{clean_path(root).rstrip('/')}/{child.lstrip('/')}"
    if include_vars:
        return {var: path for var, path in paths.items() if not var.startswith("__expr_") and path not in {"/app", "/app/"}}
    return {var: path for var, path in paths.items() if path not in {"/app", "/app/"}}


def likely_input_path(path: str, instruction: str) -> bool:
    for line in instruction.splitlines():
        if path in line and INPUT_CONTEXT_RE.search(line) and not OUTPUT_VERBS_RE.search(line):
            return True
    return False


def duplicate_numbered_steps(instruction: str) -> list[str]:
    counts: dict[str, int] = {}
    for match in NUMBERED_STEP_RE.finditer(instruction):
        counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    return sorted(number for number, count in counts.items() if count > 1)


def finding(
    task_id: str,
    defect_type: str,
    severity: str,
    confidence: float,
    message: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "defect_type": defect_type,
        "severity": severity,
        "confidence": confidence,
        "message": message,
        "evidence": evidence,
        "review_only": severity == "review",
    }


def summarize(findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    affected_tasks = set()
    for item in findings:
        by_type[item["defect_type"]] = by_type.get(item["defect_type"], 0) + 1
        by_severity[item["severity"]] = by_severity.get(item["severity"], 0) + 1
        affected_tasks.add(item["task_id"])
    return {
        "n_findings": len(findings),
        "affected_tasks": len(affected_tasks),
        "by_type": by_type,
        "by_severity": by_severity,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Terminal-Bench 2.1 Static Contract Audit",
        "",
        "This report contains review signals, not confirmed defects.",
        "",
        "## Summary",
        "",
        f"- Findings: {payload['summary']['n_findings']}",
        f"- Affected tasks: {payload['summary']['affected_tasks']}",
        f"- By type: `{json.dumps(payload['summary']['by_type'], ensure_ascii=False)}`",
        f"- By severity: `{json.dumps(payload['summary']['by_severity'], ensure_ascii=False)}`",
        "",
        "## Findings",
        "",
        "| Task | Type | Severity | Confidence | Message |",
        "|---|---|---:|---:|---|",
    ]
    for item in payload["findings"]:
        lines.append(
            "| {task_id} | {defect_type} | {severity} | {confidence:.2f} | {message} |".format(
                **{**item, "message": item["message"].replace("|", "\\|")}
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
