#!/usr/bin/env python3
"""Inventory local machine-readable MMLU item exposure without reading labels.

Implements the frozen G0 preflight protocol. The source dataset is handled by a
selective, anchored byte extractor: dataset rows are never JSON-decoded.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, BinaryIO, Iterable


PROTOCOL = Path("docs/research/MMLU_HOLDOUT_CONTAMINATION_INVENTORY_PROTOCOL_20260803.md")
EXPECTED_DATASET_SHA256 = "0c8ccf09cbb422e4cd999524aa581e3bd3040c9dcd75f1c0b2408a49ef66b3d4"
ID_LITERAL_RE = re.compile(
    rb'^\s*\{\s*"id"\s*:\s*("(?:\\["\\/bfnrt]|\\u[0-9a-fA-F]{4}|[^"\\])*")'
)
MMLU_ID_RE = re.compile(
    rb"(?<![A-Za-z0-9_.-])mmlu-redux-[A-Za-z0-9_.-]+-[0-9]+(?![A-Za-z0-9_.-])"
)
OPAQUE_KEY_RE = re.compile(r"^[0-9a-fA-F]+$")
UNSUPPORTED_SUFFIXES = {
    ".7z",
    ".bz2",
    ".gz",
    ".lz",
    ".lz4",
    ".rar",
    ".tar",
    ".tgz",
    ".xz",
    ".zst",
}
EXCLUDED_DIR_NAMES = {".git", ".pytest_cache", "__pycache__"}


class InventoryError(RuntimeError):
    """A required scan or integrity condition failed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def git(*args: str, input_bytes: bytes | None = None) -> bytes:
    process = subprocess.run(
        ["git", *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode:
        raise InventoryError(
            f"git {' '.join(args)} failed ({process.returncode}): "
            f"{process.stderr.decode('utf-8', 'replace').strip()}"
        )
    return process.stdout


def extract_universe_ids(dataset: Path) -> tuple[str, ...]:
    """Extract the first `id` field without decoding the JSON row."""
    ids: list[str] = []
    seen: set[str] = set()
    with dataset.open("rb") as handle:
        for lineno, line in enumerate(handle, 1):
            if not line.strip():
                continue
            match = ID_LITERAL_RE.match(line)
            if match is None:
                raise InventoryError(f"dataset row {lineno} does not begin with a valid id field")
            try:
                item_id = json.loads(match.group(1))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise InventoryError(f"dataset row {lineno} has an invalid id string") from exc
            if not isinstance(item_id, str) or not MMLU_ID_RE.fullmatch(item_id.encode("ascii", "strict")):
                raise InventoryError(f"dataset row {lineno} has an invalid MMLU id")
            if item_id in seen:
                raise InventoryError(f"duplicate dataset id: {item_id}")
            seen.add(item_id)
            ids.append(item_id)
    if len(ids) != 5700:
        raise InventoryError(f"dataset contains {len(ids)} unique IDs, expected 5700")
    return tuple(ids)


def find_ids_in_chunks(chunks: Iterable[bytes], universe: set[str]) -> set[str]:
    found: set[str] = set()
    overlap = b""
    for chunk in chunks:
        data = overlap + chunk
        for match in MMLU_ID_RE.finditer(data):
            value = match.group().decode("ascii")
            if value in universe:
                found.add(value)
        overlap = data[-256:]
    return found


def file_chunks(handle: BinaryIO) -> Iterable[bytes]:
    while True:
        chunk = handle.read(1024 * 1024)
        if not chunk:
            return
        yield chunk


def scan_bytes(data: bytes, universe: set[str]) -> set[str]:
    return find_ids_in_chunks((data,), universe)


def relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def should_exclude(path: Path, root: Path, output: Path) -> bool:
    try:
        path.relative_to(output)
        return True
    except ValueError:
        pass
    relative = path.relative_to(root)
    return any(part in EXCLUDED_DIR_NAMES for part in relative.parts)


def scan_zip(
    path: Path,
    source_prefix: str,
    universe: set[str],
) -> tuple[set[str], list[dict[str, Any]]]:
    found: set[str] = set()
    members: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(path) as archive:
            for info in sorted(archive.infolist(), key=lambda value: value.filename):
                if info.is_dir():
                    continue
                if info.flag_bits & 0x1:
                    raise InventoryError(f"encrypted ZIP member: {source_prefix}!{info.filename}")
                try:
                    with archive.open(info) as handle:
                        member_data = handle.read()
                except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                    raise InventoryError(
                        f"unreadable ZIP member: {source_prefix}!{info.filename}"
                    ) from exc
                member_found = scan_bytes(member_data, universe)
                found.update(member_found)
                members.append(
                    {
                        "member": info.filename,
                        "bytes": len(member_data),
                        "sha256": hashlib.sha256(member_data).hexdigest(),
                        "matched_ids": sorted(member_found),
                    }
                )
    except zipfile.BadZipFile as exc:
        raise InventoryError(f"corrupt ZIP: {source_prefix}") from exc
    return found, members


def cache_shape(path: Path) -> dict[str, Any] | None:
    entries = 0
    keys: set[str] = set()
    lengths: Counter[int] = Counter()
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict) or set(value) != {"key", "response"}:
                    return None
                key = value.get("key")
                if not isinstance(key, str) or not OPAQUE_KEY_RE.fullmatch(key):
                    return None
                entries += 1
                keys.add(key)
                lengths[len(key)] += 1
    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
        return None
    if entries == 0:
        return None
    return {
        "entries": entries,
        "distinct_keys": len(keys),
        "key_length_histogram": {str(key): lengths[key] for key in sorted(lengths)},
    }


def scan_working_tree(
    root: Path,
    output: Path,
    universe: set[str],
) -> tuple[list[dict[str, Any]], dict[str, list[str]], list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    sources: dict[str, list[str]] = defaultdict(list)
    opaque_caches: list[dict[str, Any]] = []
    unsupported: list[str] = []

    paths: list[Path] = []
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(
            name
            for name in dirs
            if not should_exclude(current_path / name, root, output)
            and not (current_path / name).is_symlink()
        )
        for name in sorted(files):
            path = current_path / name
            if should_exclude(path, root, output) or path.is_symlink():
                continue
            if path.is_file():
                paths.append(path)

    for path in sorted(paths, key=lambda value: relative_posix(value, root)):
        rel = relative_posix(path, root)
        try:
            size = path.stat().st_size
            digest = sha256_file(path)
        except OSError as exc:
            raise InventoryError(f"unreadable regular file: {rel}") from exc

        suffix = path.suffix.casefold()
        if suffix in UNSUPPORTED_SUFFIXES:
            unsupported.append(rel)
            records.append(
                {"path": rel, "bytes": size, "sha256": digest, "disposition": "unsupported"}
            )
            continue

        member_records: list[dict[str, Any]] = []
        if zipfile.is_zipfile(path):
            found, member_records = scan_zip(path, rel, universe)
            disposition = "zip_scanned"
            for member in member_records:
                source = f"{rel}!{member['member']}"
                for item_id in member["matched_ids"]:
                    sources[item_id].append(source)
        elif suffix == ".zip":
            raise InventoryError(f"corrupt ZIP: {rel}")
        else:
            try:
                with path.open("rb") as handle:
                    found = find_ids_in_chunks(file_chunks(handle), universe)
            except OSError as exc:
                raise InventoryError(f"unreadable regular file: {rel}") from exc
            disposition = "bytes_scanned"
            for item_id in found:
                sources[item_id].append(rel)

        record: dict[str, Any] = {
            "path": rel,
            "bytes": size,
            "sha256": digest,
            "disposition": disposition,
            "matched_id_count": len(found),
        }
        if member_records:
            record["zip_members"] = member_records
        records.append(record)

        if path.suffix.casefold() == ".jsonl":
            shape = cache_shape(path)
            if shape is not None:
                opaque_caches.append(
                    {
                        "path": rel,
                        "sha256": digest,
                        **shape,
                        "literal_item_ids": sorted(found),
                        "companion_machine_readable_mapping": False,
                        "status": "linked_by_literal_id" if found else "opaque_unlinkable",
                    }
                )

    return records, sources, opaque_caches, unsupported


def local_refs() -> list[dict[str, str]]:
    output = git("for-each-ref", "--format=%(refname)%09%(objectname)").decode()
    refs = []
    for line in output.splitlines():
        if not line:
            continue
        name, object_id = line.split("\t", 1)
        refs.append({"name": name, "object_id": object_id})
    if not refs:
        raise InventoryError("no local Git refs found")
    return sorted(refs, key=lambda value: value["name"])


def reachable_blob_ids() -> list[str]:
    lines = git("rev-list", "--objects", "--all").decode().splitlines()
    object_ids = sorted({line.split(" ", 1)[0] for line in lines if line})
    request = ("\n".join(object_ids) + "\n").encode()
    checks = git("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)", input_bytes=request)
    blobs: list[str] = []
    for line in checks.decode().splitlines():
        parts = line.split()
        if len(parts) != 3:
            raise InventoryError(f"unexpected git batch-check row: {line}")
        if parts[1] == "blob":
            blobs.append(parts[0])
    return sorted(blobs)


def read_git_blobs(blob_ids: list[str]) -> Iterable[tuple[str, bytes]]:
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdin is not None and process.stdout is not None
    try:
        process.stdin.write(("\n".join(blob_ids) + "\n").encode())
        process.stdin.close()
        for expected in blob_ids:
            header = process.stdout.readline().decode("ascii", "strict").rstrip("\n")
            parts = header.split()
            if len(parts) != 3 or parts[0] != expected or parts[1] != "blob":
                raise InventoryError(f"unexpected git cat-file header: {header}")
            size = int(parts[2])
            data = process.stdout.read(size)
            delimiter = process.stdout.read(1)
            if len(data) != size or delimiter != b"\n":
                raise InventoryError(f"truncated git blob: {expected}")
            yield expected, data
        return_code = process.wait()
        if return_code:
            stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
            raise InventoryError(f"git cat-file failed ({return_code}): {stderr.strip()}")
    finally:
        if process.poll() is None:
            process.kill()


def scan_git_history(
    universe: set[str],
) -> tuple[list[dict[str, Any]], dict[str, list[str]], list[dict[str, str]]]:
    refs = local_refs()
    blob_ids = reachable_blob_ids()
    records: list[dict[str, Any]] = []
    sources: dict[str, list[str]] = defaultdict(list)
    for oid, data in read_git_blobs(blob_ids):
        found = scan_bytes(data, universe)
        records.append(
            {
                "oid": oid,
                "bytes": len(data),
                "content_sha256": hashlib.sha256(data).hexdigest(),
                "matched_id_count": len(found),
            }
        )
        for item_id in found:
            sources[item_id].append(oid)
    return records, sources, refs


def render_report(inventory: dict[str, Any]) -> str:
    counts = inventory["counts"]
    opaque = inventory["opaque_cache_summary"]
    unsupported = inventory["unsupported_files"]
    lines = [
        "# MMLU holdout contamination inventory",
        "",
        f"- Outcome: **{inventory['outcome']}**",
        f"- Frozen universe: **{counts['universe_ids']}** IDs",
        f"- Exact-ID exposed: **{counts['exposed_ids']}**",
        f"- Repo-artifact-unseen candidates: **{counts['candidate_ids']}**",
        f"- Git refs / unique blobs: **{counts['git_refs']} / {counts['git_blobs']}**",
        f"- Working-tree regular files: **{counts['working_tree_files']}**",
        f"- Opaque-unlinkable caches: **{opaque['opaque_unlinkable_files']} files / "
        f"{opaque['opaque_unlinkable_entries']} entries**",
        f"- Unsupported files: **{len(unsupported)}**",
        "",
        "## Claim boundary",
        "",
        "The candidate set means only that no exact item ID was found in the scanned local Git "
        "history or current filesystem snapshot. It is not a holdout manifest and has not been "
        "passed to an auditor. Absolute blindness is not identifiable: unrecorded human exposure "
        "and digest-only cache entries cannot be ruled out.",
        "",
    ]
    if unsupported:
        lines += ["## Unsupported inputs", ""] + [f"- `{path}`" for path in unsupported] + [""]
    return "\n".join(lines)


def git_head() -> str:
    return git("rev-parse", "HEAD").decode().strip()


def run(args: argparse.Namespace) -> None:
    root = Path(args.repo_root).resolve()
    dataset = Path(args.dataset).resolve()
    output = Path(args.out).resolve()
    if sha256_file(dataset) != EXPECTED_DATASET_SHA256:
        raise InventoryError("frozen dataset SHA-256 mismatch")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise InventoryError(f"output directory must be empty: {output}")

    ids = extract_universe_ids(dataset)
    universe = set(ids)
    git_records, git_sources, refs = scan_git_history(universe)
    file_records, file_sources, opaque_caches, unsupported = scan_working_tree(
        root, output, universe
    )

    all_exposed = set(git_sources) | set(file_sources)
    candidate_ids = universe - all_exposed
    opaque_unlinkable = [cache for cache in opaque_caches if cache["status"] == "opaque_unlinkable"]
    if unsupported:
        outcome = "NOT_IDENTIFIABLE_SCAN_COVERAGE"
    elif not candidate_ids:
        outcome = "NO_SCOPED_CANDIDATES"
    else:
        outcome = "PASS_SCOPED_POOL_AVAILABLE"

    exposure_rows = []
    for item_id in sorted(all_exposed):
        exposure_rows.append(
            {
                "item_id": item_id,
                "git_history_sources": sorted(git_sources.get(item_id, [])),
                "working_tree_sources": sorted(file_sources.get(item_id, [])),
            }
        )
    inventory = {
        "schema_version": "mmlu-holdout-contamination-inventory-v1",
        "outcome": outcome,
        "scope": "exact_item_id_exposure_in_local_git_history_and_working_tree_snapshot",
        "dataset_rows_json_decoded": False,
        "candidate_question_gold_or_label_emitted": False,
        "holdout_manifest_generated": False,
        "auditor_executed": False,
        "absolute_blindness_identifiable": False,
        "counts": {
            "universe_ids": len(universe),
            "exposed_ids": len(all_exposed),
            "candidate_ids": len(candidate_ids),
            "git_refs": len(refs),
            "git_blobs": len(git_records),
            "working_tree_files": len(file_records),
        },
        "exposures": exposure_rows,
        "candidate_ids": sorted(candidate_ids),
        "local_refs": refs,
        "git_blob_records": git_records,
        "working_tree_file_records": file_records,
        "opaque_caches": sorted(opaque_caches, key=lambda value: value["path"]),
        "opaque_cache_summary": {
            "opaque_unlinkable_files": len(opaque_unlinkable),
            "opaque_unlinkable_entries": sum(cache["entries"] for cache in opaque_unlinkable),
        },
        "unsupported_files": sorted(unsupported),
        "caveats": [
            "Exact-ID absence does not prove absence of human exposure.",
            "Digest-only cache keys cannot be linked to items without reconstructing historical prompts.",
            "Candidate IDs are not a frozen holdout and must not be audited before a later protocol.",
        ],
    }
    if len(all_exposed & candidate_ids) or len(all_exposed | candidate_ids) != 5700:
        raise InventoryError("exposed/candidate partition is inconsistent")

    inventory_bytes = stable_json_bytes(inventory)
    report_bytes = render_report(inventory).encode()
    (output / "inventory.json").write_bytes(inventory_bytes)
    (output / "REPORT.md").write_bytes(report_bytes)
    receipt = {
        "schema_version": "mmlu-holdout-contamination-receipt-v1",
        "outcome": outcome,
        "git_commit": git_head(),
        "api_attempts": 0,
        "network_attempts": 0,
        "dataset_rows_json_decoded": False,
        "candidate_question_gold_or_label_emitted": False,
        "dataset_sha256": sha256_file(dataset),
        "protocol_sha256": sha256_file((root / PROTOCOL).resolve()),
        "scanner_sha256": sha256_file(Path(__file__).resolve()),
        "environment": {
            "python": platform.python_version(),
            "git": git("--version").decode().strip(),
        },
        "outputs": {
            "inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        },
    }
    (output / "receipt.json").write_bytes(stable_json_bytes(receipt))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    try:
        run(parse_args())
    except (InventoryError, OSError, UnicodeError) as exc:
        print(f"NOT_IDENTIFIABLE_SCAN_COVERAGE: {exc}", file=sys.stderr)
        raise SystemExit(2)
