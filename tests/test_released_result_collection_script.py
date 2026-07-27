from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.audit_released_result_collection import (
    _parse_exec_file,
    _parse_match_file,
    _wilson_interval,
)


class ReleasedResultCollectionParserTest(unittest.TestCase):
    def test_structured_match_and_execution_files_are_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match = root / "match.txt"
            execution = root / "exec.txt"
            match.write_text(
                "Match OK   easy pred: SELECT 1\n"
                "           easy gold: SELECT 1\n---\n",
                encoding="utf-8",
            )
            execution.write_text(
                "Exec  Fail easy pred: SELECT 1\n"
                "           easy gold: SELECT 1\n---\n",
                encoding="utf-8",
            )

            match_rows = _parse_match_file(match)
            execution_rows = _parse_exec_file(execution)

        self.assertEqual(match_rows[0]["match_verdict"], True)
        self.assertEqual(execution_rows[0]["exec_verdict"], False)
        self.assertEqual(match_rows[0]["prediction"], "SELECT 1")
        self.assertEqual(execution_rows[0]["reference"], "SELECT 1")

    def test_semicolon_evaluator_format_is_supported_for_both_channels(self) -> None:
        payload = "Pred OK  ;easy;db;SELECT 1;SELECT 1\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match = root / "match.txt"
            execution = root / "exec.txt"
            match.write_text(payload, encoding="utf-8")
            execution.write_text(payload.replace("OK  ", "Fail"), encoding="utf-8")

            match_rows = _parse_match_file(match)
            execution_rows = _parse_exec_file(execution)

        self.assertEqual(match_rows[0]["match_verdict"], True)
        self.assertEqual(execution_rows[0]["exec_verdict"], False)

    def test_wilson_interval_contains_observed_rate(self) -> None:
        low, high = _wilson_interval(60, 316)
        self.assertLess(low, 60 / 316)
        self.assertGreater(high, 60 / 316)


if __name__ == "__main__":
    unittest.main()
