import tempfile
import unittest
from pathlib import Path

from benchcore.schema import BenchmarkItem
from benchcore.value_recompute import (
    ValueRecomputeChecker,
    input_file_paths,
    reproduced,
    run_code,
)


class FakeClient:
    """Returns a fixed recompute code block regardless of prompt."""

    def __init__(self, code: str) -> None:
        self._code = code

    def chat_json(self, system: str, user: str) -> dict:
        return {"code": self._code}


class ReproducedTest(unittest.TestCase):
    def test_tolerates_thousands_separators_but_flags_real_gap(self):
        self.assertEqual(reproduced([299.0], "total=299"), [])
        self.assertEqual(reproduced([15102.0], "n=15,102"), [])       # thousands separator
        self.assertEqual(reproduced([300.0], "total=299"), [])        # within ±1 tolerance
        self.assertEqual(reproduced([350.0], "total=299"), [350.0])   # real mismatch


class InputFilePathsTest(unittest.TestCase):
    def test_keeps_all_existing_files_drops_missing(self):
        # non-tabular inputs are kept too -- the recompute reads them via read_file.
        with tempfile.TemporaryDirectory() as d:
            csv = Path(d) / "data.csv"
            csv.write_text("a,b\n1,2\n", encoding="utf-8")
            txt = Path(d) / "notes.txt"
            txt.write_text("hello", encoding="utf-8")
            item = BenchmarkItem(
                item_id="t",
                raw={},
                context={"files": [str(csv), str(txt), str(Path(d) / "missing.csv")]},
            )
            paths = input_file_paths(item, root=None)
            self.assertEqual(sorted(p.name for p in paths), ["data.csv", "notes.txt"])


class RunCodeTest(unittest.TestCase):
    def test_generated_code_can_read_non_tabular_via_read_file(self):
        # run_code preloads read_file so recompute can pull numbers from text inputs.
        with tempfile.TemporaryDirectory() as d:
            txt = Path(d) / "report.txt"
            txt.write_text("negative-variance items: 8\n", encoding="utf-8")
            out = run_code(f"t = read_file({str(txt)!r}, 20000)\nprint('has8=' + str('8' in t))")
            self.assertIn("has8=True", out)


class ValueRecomputeCheckerTest(unittest.TestCase):
    def _item(self, rubric: str, csv: Path) -> BenchmarkItem:
        return BenchmarkItem(
            item_id="t",
            raw={"rubrics": [rubric]},
            context={"files": [str(csv)]},
        )

    def _run(self, rubric: str, code: str):
        with tempfile.TemporaryDirectory() as d:
            csv = Path(d) / "data.csv"
            csv.write_text("x\n1\n", encoding="utf-8")  # only needs to exist
            checker = ValueRecomputeChecker(FakeClient(code))
            return list(checker.check(self._item(rubric, csv), root=None))

    def test_reproduced_value_yields_no_violation(self):
        self.assertEqual(self._run("输出文件中生日礼金的总人数是否为299人？", 'print("total=299")'), [])

    def test_mismatch_yields_wrong_gold_answer(self):
        v = self._run("输出文件中生日礼金的总人数是否为350人？", 'print("total=299")')
        self.assertEqual([x.defect_type for x in v], ["wrong_gold_answer"])
        self.assertTrue(v[0].review_only)
        self.assertEqual(v[0].evidence["missing_values"], [350.0])

    def test_data_not_available_is_silent(self):
        # inconclusive recompute (data likely in a non-tabular input) is not a rubric defect;
        # data-gap detection is owned by the grounded-rubric checker.
        v = self._run("输出文件中生日礼金的总人数是否为299人？", 'print("DATA_NOT_AVAILABLE")')
        self.assertEqual(v, [])

    def test_non_numeric_rubric_is_skipped(self):
        # a coverage rubric asserts no substantive value -> never recomputed
        self.assertEqual(self._run("输出文件中是否包含2024年1月至12月每个月的数据？", 'print("x=1")'), [])

    def test_unrunnable_code_is_silent(self):
        v = self._run("输出文件中生日礼金的总人数是否为299人？", 'raise ValueError("boom")')
        self.assertEqual(v, [])


if __name__ == "__main__":
    unittest.main()
