#!/usr/bin/env python3
"""Inspect one primitive-only Platinum paper cache without emitting prompts."""

from __future__ import annotations

import json
import pickle
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    path = Path(sys.argv[1])
    with path.open("rb") as handle:
        value = pickle.load(handle)
    if not isinstance(value, dict):
        raise SystemExit("cache root is not a dict")

    key_lengths: Counter[int] = Counter()
    key_type_shapes: Counter[tuple[str, ...]] = Counter()
    value_types: Counter[str] = Counter()
    position_values: list[set[object]] = []
    for key, cached_value in value.items():
        if not isinstance(key, tuple):
            raise SystemExit("cache key is not a tuple")
        key_lengths[len(key)] += 1
        key_type_shapes[tuple(type(part).__name__ for part in key)] += 1
        value_types[type(cached_value).__name__] += 1
        while len(position_values) < len(key):
            position_values.append(set())
        for index, part in enumerate(key):
            position_values[index].add(part)

    model_positions: list[int] = []
    prompt_like_positions: list[int] = []
    for index, values in enumerate(position_values):
        if values and all(isinstance(item, str) for item in values):
            lengths = [len(item) for item in values]
            if max(lengths) < 100 and 5 <= len(values) <= 100:
                model_positions.append(index)
            if max(lengths) >= 100:
                prompt_like_positions.append(index)

    result = {
        "root_type": type(value).__name__,
        "entry_count": len(value),
        "key_length_counts": {str(k): v for k, v in sorted(key_lengths.items())},
        "key_type_shape_counts": {
            ",".join(k): v for k, v in sorted(key_type_shapes.items())
        },
        "value_type_counts": dict(sorted(value_types.items())),
        "position_unique_counts": [len(values) for values in position_values],
        "model_positions": model_positions,
        "model_count": (
            len(position_values[model_positions[0]]) if len(model_positions) == 1 else None
        ),
        "prompt_like_positions": prompt_like_positions,
        "explicit_item_identity_present": False,
    }
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
