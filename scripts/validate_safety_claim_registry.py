#!/usr/bin/env python3
"""Validate that every registered safety claim points to a real mutation test."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "benchaudit-safety-claims-v1"


def _function_sources(path: Path) -> dict[str, list[str]]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    result: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            segment = ast.get_source_segment(source, node) or ""
            result.setdefault(node.name, []).append(segment)
    return result


def validate_registry(registry_path: Path, repository_root: Path) -> list[str]:
    errors: list[str] = []
    try:
        document = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read registry: {exc}"]
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        return [f"registry schema_version must be {SCHEMA_VERSION!r}"]
    claims = document.get("claims")
    if not isinstance(claims, list) or not claims:
        return ["registry claims must be a non-empty list"]

    seen_ids: set[str] = set()
    source_cache: dict[Path, dict[str, list[str]]] = {}
    for index, claim in enumerate(claims):
        prefix = f"claims[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{prefix} must be an object")
            continue
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            errors.append(f"{prefix}.claim_id must be non-empty")
        elif claim_id in seen_ids:
            errors.append(f"{prefix}.claim_id is duplicated: {claim_id}")
        else:
            seen_ids.add(claim_id)
        if not isinstance(claim.get("statement"), str) or not claim["statement"].strip():
            errors.append(f"{prefix}.statement must be non-empty")

        enforcement_paths = claim.get("enforcement_paths")
        if not isinstance(enforcement_paths, list) or not enforcement_paths:
            errors.append(f"{prefix}.enforcement_paths must be non-empty")
        else:
            for relative in enforcement_paths:
                path = repository_root / str(relative)
                if not path.is_file():
                    errors.append(f"{prefix} enforcement path does not exist: {relative}")

        mutation = claim.get("mutation_test")
        if not isinstance(mutation, dict):
            errors.append(f"{prefix}.mutation_test must be an object")
            continue
        relative_test = mutation.get("file")
        function = mutation.get("function")
        kind = mutation.get("kind")
        tokens = mutation.get("required_tokens")
        if (
            not isinstance(relative_test, str)
            or not relative_test.startswith("tests/")
            or ".." in Path(relative_test).parts
        ):
            errors.append(f"{prefix} mutation test must be under tests/")
            continue
        if not isinstance(function, str) or not function.startswith("test_"):
            errors.append(f"{prefix} mutation test function must start with test_")
            continue
        if not isinstance(kind, str) or not kind:
            errors.append(f"{prefix} mutation kind must be non-empty")
        if (
            not isinstance(tokens, list)
            or not tokens
            or not all(isinstance(token, str) and token for token in tokens)
        ):
            errors.append(f"{prefix} required_tokens must be non-empty strings")
            continue

        test_path = repository_root / relative_test
        if not test_path.is_file():
            errors.append(f"{prefix} mutation test file does not exist: {relative_test}")
            continue
        if test_path not in source_cache:
            source_cache[test_path] = _function_sources(test_path)
        matches = source_cache[test_path].get(function, [])
        if len(matches) != 1:
            errors.append(
                f"{prefix} mutation function must exist exactly once: "
                f"{relative_test}::{function}"
            )
            continue
        missing = [token for token in tokens if token not in matches[0]]
        if missing:
            errors.append(
                f"{prefix} mutation function lacks required tokens: {missing}"
            )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("docs/security_claims_registry.json"),
    )
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    args = parser.parse_args()
    errors = validate_registry(
        args.registry.resolve(), args.repository_root.resolve(),
    )
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"safety claim registry valid: {args.registry}")


if __name__ == "__main__":
    main()
