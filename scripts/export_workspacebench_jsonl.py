"""Export Workspace-Bench HuggingFace splits to local JSONL for benchcore audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DATASET_PRESETS = {
    "lite": ("Workspace-Bench/Workspace-Bench-Lite", "lite"),
    "full": ("Workspace-Bench/Workspace-Bench", "full"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=sorted(DATASET_PRESETS), default="lite")
    parser.add_argument("--out-dir", default="datasets/workspacebench")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--download-inputs",
        action="store_true",
        help="Download task data directories from HuggingFace and expose local files as input_files",
    )
    return parser.parse_args()


def rows_for_dataset(
    path: str,
    split: str,
    limit: int | None,
    *,
    download_inputs: bool = False,
) -> list[dict[str, Any]]:
    from datasets import load_dataset

    ds = load_dataset(path, split=split)
    rows = []
    for index, row in enumerate(ds):
        if limit is not None and index >= limit:
            break
        rows.append(
            with_benchcore_fields(
                dict(row),
                dataset_path=path,
                download_inputs=download_inputs,
            )
        )
    return rows


def with_benchcore_fields(
    row: dict[str, Any],
    *,
    dataset_path: str = "Workspace-Bench/Workspace-Bench-Lite",
    download_inputs: bool = False,
) -> dict[str, Any]:
    """Add generic BenchCore fields while preserving original Workspace-Bench fields."""
    out = dict(row)
    absolute_id = row.get("absolute_id")
    rubrics = parse_json_field(row.get("rubrics"), default=[])
    rubric_types = parse_json_field(row.get("rubric_types"), default=[])
    output_files = parse_json_field(row.get("output_files"), default=[])
    data_manifest = parse_json_field(row.get("data_manifest"), default=[])
    file_dep_graph = parse_json_field(row.get("file_dep_graph"), default=[])
    tested_capabilities = parse_json_field(row.get("tested_capabilities"), default=[])

    out.setdefault("item_id", f"workspacebench-{absolute_id}")
    out.setdefault("task", row.get("task"))
    out["rubrics"] = rubrics
    out.setdefault(
        "output_contract",
        {
            "type": "workspace_files",
            "required_files": output_files,
            "description": "Create the requested workspace files and satisfy task-specific rubrics.",
        },
    )
    out.setdefault(
        "evaluator",
        {
            "type": "workspacebench_rubric",
            "rubrics": rubrics,
            "rubric_types": rubric_types,
        },
    )
    out["context"] = {
        "output_files": output_files,
        "data_manifest": data_manifest,
        "file_dep_graph": file_dep_graph,
        "tested_capabilities": tested_capabilities,
    }
    if download_inputs and absolute_id is not None:
        input_files = workspace_input_files(dataset_path, int(absolute_id))
        out["input_files"] = [str(path) for path in input_files]

    metadata = out.get("metadata") if isinstance(out.get("metadata"), dict) else {}
    metadata = dict(metadata)
    for key in ("absolute_id", "language", "persona", "task_diff"):
        if key in row:
            metadata.setdefault(key, row.get(key))
    out["metadata"] = metadata
    return out


def workspace_input_files(dataset_path: str, absolute_id: int) -> list[Path]:
    from huggingface_hub import snapshot_download

    if dataset_path.endswith("Workspace-Bench-Lite"):
        task_dirs = ["task_lite_clean_en"]
    else:
        # The full benchmark stores both English and Chinese task folders. The
        # rows exported by HuggingFace here are English, so prefer task_clean_en
        # and keep task_clean_cn as a fallback for future variants.
        task_dirs = ["task_clean_en", "task_clean_cn"]
    root = snapshot_download(
        dataset_path,
        repo_type="dataset",
        allow_patterns=[f"{task_dir}/{absolute_id}/**" for task_dir in task_dirs],
    )
    for task_dir in task_dirs:
        data_dir = Path(root) / task_dir / str(absolute_id) / "data"
        if data_dir.exists():
            return sorted(path for path in data_dir.iterdir() if path.is_file())
    return []


def parse_json_field(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    args = parse_args()
    dataset_path, split = DATASET_PRESETS[args.suite]
    rows = rows_for_dataset(
        dataset_path,
        split,
        args.limit,
        download_inputs=args.download_inputs,
    )
    suffix = f"_{args.limit}" if args.limit is not None else ""
    out_path = Path(args.out_dir) / f"{args.suite}{suffix}.jsonl"
    write_jsonl(out_path, rows)
    print(f"{args.suite}: wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
