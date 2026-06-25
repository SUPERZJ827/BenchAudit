import json
from pathlib import Path
import tempfile
import unittest

from benchcore.sampling import build_sample, load_rows_from_manifest, write_manifest


class SamplingTest(unittest.TestCase):
    def test_sampling_is_deterministic_and_manifest_reloads(self) -> None:
        rows = [
            {
                "id": f"item-{idx}",
                "metadata": {
                    "subject": "a" if idx % 2 == 0 else "b",
                    "label": "ok" if idx < 10 else "error",
                },
            }
            for idx in range(20)
        ]
        source = Path("examples/sample_core_benchmark.jsonl")
        first, manifest = build_sample(
            rows,
            source_path=source,
            size=10,
            seed=7,
            stratify_fields=["metadata.subject"],
            label_field="metadata.label",
            clean_values={"ok"},
            defect_fraction=0.5,
        )
        second, _ = build_sample(
            rows,
            source_path=source,
            size=10,
            seed=7,
            stratify_fields=["metadata.subject"],
            label_field="metadata.label",
            clean_values={"ok"},
            defect_fraction=0.5,
        )
        self.assertEqual(
            [row["id"] for row in first],
            [row["id"] for row in second],
        )

        manifest["source_sha256"] = None
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            write_manifest(path, manifest)
            loaded = load_rows_from_manifest(rows, source, path, verify_hash=False)
        self.assertEqual(
            [row["id"] for row in first],
            [row["id"] for row in loaded],
        )


if __name__ == "__main__":
    unittest.main()

