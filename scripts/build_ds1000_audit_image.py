#!/usr/bin/env python3
"""Build and print a digest-pinned DS-1000 audit image.

The image intentionally contains only the numerical libraries required by the
supported DS-1000 families.  Audit execution itself still mounts an empty,
read-only workspace and disables network access in ``ContainerRunner``.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="localhost:5000/ds1000-audit:scipy-sklearn-v1")
    parser.add_argument("--engine", default="docker")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    if shutil.which(args.engine) is None:
        raise RuntimeError(f"container engine not found: {args.engine}")
    dockerfile = REPO / "docker" / "ds1000-audit" / "Dockerfile"
    command = [args.engine, "build", "--tag", args.tag]
    if args.no_cache:
        command.append("--no-cache")
    command.extend(["--file", str(dockerfile), str(dockerfile.parent)])
    subprocess.run(command, check=True)
    inspect = subprocess.run(
        [args.engine, "image", "inspect", args.tag, "--format", "{{json .RepoDigests}}"],
        check=True, text=True, capture_output=True,
    )
    digests = json.loads(inspect.stdout.strip() or "[]")
    if not digests:
        print(
            "Built local image but it has no registry digest yet. Push it to the "
            "chosen registry, then inspect the pushed image and use NAME@sha256:..."
        )
        return 0
    print("\n".join(digests))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
