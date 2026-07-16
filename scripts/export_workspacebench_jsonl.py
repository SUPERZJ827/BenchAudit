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

TASK_LAYOUTS = {
    "lite": {"en": "task_lite_clean_en", "cn": "task_lite_clean_cn"},
    "full": {"en": "task_clean_en", "cn": "task_clean_cn"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=sorted(DATASET_PRESETS), default="lite")
    parser.add_argument("--language", choices=("en", "cn"), default="en")
    parser.add_argument(
        "--revision",
        help="Pinned Hugging Face dataset commit. Strongly recommended for experiments.",
    )
    parser.add_argument("--out-dir", default="datasets/workspacebench")
    parser.add_argument("--out-name", help="Explicit output filename under --out-dir")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--download-inputs",
        action="store_true",
        help="Download task data directories from HuggingFace and expose local files as input_files",
    )
    parser.add_argument(
        "--require-complete-inputs", action="store_true",
        help="Fail if any data_manifest row has no materialized task input",
    )
    return parser.parse_args()


def rows_for_dataset(
    path: str,
    split: str,
    limit: int | None,
    *,
    download_inputs: bool = False,
    suite: str = "lite",
    language: str = "en",
    revision: str | None = None,
    require_complete_inputs: bool = False,
) -> list[dict[str, Any]]:
    # The datasets-server split historically exposed English rows only.  When
    # files or another language are requested, load metadata and data from the
    # *same pinned task directory* to prevent cross-language artifact mixing.
    if download_inputs or language != "en":
        return rows_for_snapshot(
            path,
            suite=suite,
            language=language,
            revision=revision,
            limit=limit,
            require_complete_inputs=require_complete_inputs,
        )
    from datasets import load_dataset

    ds = load_dataset(path, split=split, revision=revision)
    rows = []
    for index, row in enumerate(ds):
        if limit is not None and index >= limit:
            break
        rows.append(
            with_benchcore_fields(
                dict(row),
                dataset_path=path,
                download_inputs=download_inputs,
                source_revision=revision,
            )
        )
    return rows


def rows_for_snapshot(
    dataset_path: str,
    *,
    suite: str,
    language: str,
    revision: str | None,
    limit: int | None,
    require_complete_inputs: bool,
) -> list[dict[str, Any]]:
    from huggingface_hub import snapshot_download

    task_layout = TASK_LAYOUTS[suite][language]
    root = Path(snapshot_download(
        repo_id=dataset_path,
        repo_type="dataset",
        revision=revision,
        allow_patterns=[f"{task_layout}/**"],
    ))
    metadata_paths = sorted(
        (root / task_layout).glob("*/metadata.json"),
        key=lambda path: _task_sort_key(path.parent.name),
    )
    if limit is not None:
        metadata_paths = metadata_paths[:limit]
    rows: list[dict[str, Any]] = []
    for metadata_path in metadata_paths:
        value = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"metadata is not a JSON object: {metadata_path}")
        row = dict(value)
        task_id = row.get("absolute_id", metadata_path.parent.name)
        row.setdefault("absolute_id", int(task_id) if str(task_id).isdigit() else task_id)
        row.setdefault("language", language)
        input_files = sorted(
            path for path in (metadata_path.parent / "data").rglob("*") if path.is_file()
        )
        out = with_benchcore_fields(
            row,
            dataset_path=dataset_path,
            download_inputs=False,
            source_revision=revision,
            source_task_layout=task_layout,
        )
        # Keep the snapshot filename: ``resolve()`` follows Hugging Face cache
        # symlinks to opaque blob hashes and destroys manifest reconciliation.
        out["input_files"] = [str(path.absolute()) for path in input_files]
        _validate_materialized_inputs(
            out, metadata_path, require_complete=require_complete_inputs,
        )
        rows.append(out)
    if not rows:
        raise ValueError(
            f"no metadata found for {dataset_path}@{revision or 'main'}:{task_layout}"
        )
    return rows


def with_benchcore_fields(
    row: dict[str, Any],
    *,
    dataset_path: str = "Workspace-Bench/Workspace-Bench-Lite",
    download_inputs: bool = False,
    source_revision: str | None = None,
    source_task_layout: str | None = None,
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
        input_files = workspace_input_files(
            dataset_path, int(absolute_id), revision=source_revision,
        )
        out["input_files"] = [str(path) for path in input_files]

    metadata = out.get("metadata") if isinstance(out.get("metadata"), dict) else {}
    metadata = dict(metadata)
    for key in ("absolute_id", "language", "persona", "task_diff"):
        if key in row:
            metadata.setdefault(key, row.get(key))
    metadata["source_dataset"] = dataset_path
    if source_revision:
        metadata["source_revision"] = source_revision
    if source_task_layout:
        metadata["source_task_layout"] = source_task_layout
    out["metadata"] = metadata
    return out


def workspace_input_files(
    dataset_path: str,
    absolute_id: int,
    *,
    language: str = "en",
    revision: str | None = None,
) -> list[Path]:
    from huggingface_hub import snapshot_download

    if dataset_path.endswith("Workspace-Bench-Lite"):
        task_dirs = [TASK_LAYOUTS["lite"][language]]
    else:
        task_dirs = [TASK_LAYOUTS["full"][language]]
    root = snapshot_download(
        dataset_path,
        repo_type="dataset",
        revision=revision,
        allow_patterns=[f"{task_dir}/{absolute_id}/**" for task_dir in task_dirs],
    )
    for task_dir in task_dirs:
        data_dir = Path(root) / task_dir / str(absolute_id) / "data"
        if data_dir.exists():
            return sorted(path for path in data_dir.iterdir() if path.is_file())
    return []


def _task_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def _validate_materialized_inputs(
    row: dict[str, Any], metadata_path: Path, *, require_complete: bool,
) -> None:
    paths = [Path(value) for value in row.get("input_files") or []]
    missing_files = [str(path) for path in paths if not path.is_file()]
    manifest = row.get("context", {}).get("data_manifest") or []
    physical = {path.name.casefold() for path in paths if path.is_file()}
    logical = {
        (path.name.split("_", 1)[1] if _has_hash_prefix(path.name) else path.name).casefold()
        for path in paths if path.is_file()
    }
    unresolved = []
    for entry in manifest:
        if not isinstance(entry, dict):
            unresolved.append(entry)
            continue
        filename = Path(str(entry.get("filename") or "")).name.casefold()
        stored = Path(str(entry.get("stored_relpath") or "")).name.casefold()
        if not ((filename and filename in logical) or (stored and stored in physical)):
            unresolved.append(entry)
    if require_complete and (missing_files or unresolved):
        raise ValueError(
            f"incomplete task package {metadata_path}: missing_files={len(missing_files)}, "
            f"unresolved_manifest={len(unresolved)}"
        )


def _has_hash_prefix(name: str) -> bool:
    prefix, separator, _ = name.partition("_")
    return bool(separator and len(prefix) == 16 and all(ch in "0123456789abcdefABCDEF" for ch in prefix))


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
        suite=args.suite,
        language=args.language,
        revision=args.revision,
        require_complete_inputs=args.require_complete_inputs,
    )
    suffix = f"_{args.limit}" if args.limit is not None else ""
    language_suffix = "" if args.language == "en" else f"_{args.language}"
    filename = args.out_name or f"{args.suite}{language_suffix}{suffix}.jsonl"
    out_path = Path(args.out_dir) / filename
    write_jsonl(out_path, rows)
    print(f"{args.suite}: wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
