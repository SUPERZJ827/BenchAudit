import tempfile
import unittest
from pathlib import Path

from benchcore.auditor import audit_items_with_ledger
from benchcore.execution import (
    CommandSpec,
    ContainerRunner,
    ExecutionPolicy,
    ExecutionRefused,
    LocalProcessRunner,
    RunResult,
)
from benchcore.schema import BenchmarkItem
from benchcore.value_recompute import (
    ValueRecomputeChecker,
    computed_values,
    execute_code,
    input_file_paths,
    is_uninformative,
    reproduced,
    run_code,
)


class FakeClient:
    """Returns a fixed recompute code block regardless of prompt."""

    def __init__(self, code: str) -> None:
        self._code = code
        self.user_prompts: list[str] = []

    def chat_json(self, system: str, user: str) -> dict:
        self.user_prompts.append(user)
        return {"code": self._code}


def unsafe_local_policy(timeout: float = 15) -> ExecutionPolicy:
    return ExecutionPolicy(
        timeout_seconds=timeout,
        allow_local_process=True,
        allowed_environment=frozenset(),
    )


class FailedDependencyRunner:
    def run(self, command: CommandSpec, policy: ExecutionPolicy | None = None) -> RunResult:
        return RunResult(
            argv=command.argv,
            exit_code=1,
            stdout="",
            stderr="ModuleNotFoundError: No module named 'pandas'",
            elapsed_seconds=0.01,
            timed_out=False,
            isolation="ephemeral_container_readonly_workspace",
            backend="docker",
        )


class InspectingContainerRunner:
    """Structural container test without requiring a daemon in CI."""

    def __init__(self, output: str = "total=299") -> None:
        self.output = output
        self.container_argv: tuple[str, ...] | None = None
        self.workspace_files: list[str] = []
        self.script = ""

    def run(self, command: CommandSpec, policy: ExecutionPolicy | None = None) -> RunResult:
        assert command.cwd is not None
        assert policy is not None
        self.workspace_files = sorted(
            str(path.relative_to(command.cwd))
            for path in command.cwd.rglob("*")
            if path.is_file()
        )
        self.script = (command.cwd / "recompute_probe.py").read_text(encoding="utf-8")
        builder = ContainerRunner("benchcore-value:latest", engine="/usr/bin/docker")
        self.container_argv = builder.build_argv(command, policy)
        return RunResult(
            argv=command.argv,
            exit_code=0,
            stdout=self.output,
            stderr="",
            elapsed_seconds=0.02,
            timed_out=False,
            isolation="ephemeral_container_readonly_workspace",
            backend="docker",
        )


class ReproducedTest(unittest.TestCase):
    def test_tolerates_thousands_separators_but_flags_real_gap(self):
        self.assertEqual(reproduced([299.0], "total=299"), [])
        self.assertEqual(reproduced([15102.0], "n=15,102"), [])       # thousands separator
        self.assertEqual(reproduced([300.0], "total=299"), [])        # within ±1 tolerance
        self.assertEqual(reproduced([350.0], "total=299"), [350.0])   # real mismatch

    def test_ignores_numbers_in_labels(self):
        # 'centers_10_29_beds' must not leak 10/29 into the comparison
        self.assertEqual(reproduced([3640.0], "centers_10_29_beds=0"), [3640.0])
        self.assertEqual(computed_values("a_1_9=0\nb_10_29=0"), [0.0, 0.0])
        self.assertEqual(computed_values("debug row 350\ntotal=299"), [299.0])


class IsUninformativeTest(unittest.TestCase):
    def test_nan_and_all_zero_are_uninformative(self):
        self.assertTrue(is_uninformative("top1=nan", [3200.0]))
        self.assertTrue(is_uninformative("debug output 3200", [3200.0]))
        self.assertTrue(is_uninformative("a=0\nb=0", [3640.0, 611.0]))   # failed recompute
        self.assertFalse(is_uninformative("count=27", [27.0]))
        self.assertFalse(is_uninformative("errors=0", [0.0]))            # genuine zero result


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
            paths = input_file_paths(item, root=None, allowed_roots=(Path(d),))
            self.assertEqual(sorted(p.name for p in paths), ["data.csv", "notes.txt"])


class RunCodeTest(unittest.TestCase):
    def test_refuses_host_execution_by_default(self):
        with self.assertRaises(ExecutionRefused):
            run_code("print('x=1')")

    def test_generated_code_can_read_non_tabular_via_read_file(self):
        # Explicit unsafe-local execution remains available only for trusted unit tests.
        with tempfile.TemporaryDirectory() as d:
            txt = Path(d) / "report.txt"
            txt.write_text("negative-variance items: 8\n", encoding="utf-8")
            out = run_code(
                "t = read_file('/workspace/inputs/0000_report.txt', 20000)\n"
                "print('has8=' + str('8' in t))",
                runner=LocalProcessRunner(),
                policy=unsafe_local_policy(),
                input_paths=[txt],
                allow_unsafe_local=True,
            )
            self.assertIn("has8=True", out)

    def test_requires_both_local_acknowledgements(self):
        with self.assertRaisesRegex(ExecutionRefused, "allow_unsafe_local"):
            run_code(
                "print('x=1')",
                runner=LocalProcessRunner(),
                policy=unsafe_local_policy(),
            )
        with self.assertRaisesRegex(ExecutionRefused, "ExecutionPolicy"):
            run_code(
                "print('x=1')",
                runner=LocalProcessRunner(),
                policy=ExecutionPolicy(),
                allow_unsafe_local=True,
            )

    def test_container_workspace_contains_only_script_and_explicit_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "private-host-prefix.csv"
            source.write_text("x\n1\n", encoding="utf-8")
            runner = InspectingContainerRunner()
            result = execute_code(
                "print('total=299')",
                runner=runner,
                input_paths=[source],
            )

        self.assertEqual(result.output, "total=299")
        self.assertEqual(
            runner.workspace_files,
            ["inputs/0000_private-host-prefix.csv", "recompute_probe.py"],
        )
        self.assertNotIn(str(Path(__file__).resolve().parents[1]), runner.script)
        self.assertNotIn(str(source.parent), runner.script)
        joined = " ".join(runner.container_argv or ())
        self.assertIn("--network none", joined)
        self.assertIn("--read-only", runner.container_argv or ())
        self.assertIn("readonly", joined)
        self.assertNotIn(str(Path(__file__).resolve().parents[1]), joined)


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
            checker = ValueRecomputeChecker(
                FakeClient(code),
                runner=LocalProcessRunner(),
                policy=unsafe_local_policy(),
                allow_unsafe_local=True,
                allowed_roots=(Path(d),),
            )
            return list(checker.check(self._item(rubric, csv), root=None))

    def test_reproduced_value_yields_no_violation(self):
        self.assertEqual(self._run("输出文件中生日礼金的总人数是否为299人？", 'print("total=299")'), [])

    def test_checker_without_runner_is_security_blocked_before_llm_call(self):
        with tempfile.TemporaryDirectory() as d:
            csv = Path(d) / "data.csv"
            csv.write_text("x\n1\n", encoding="utf-8")
            client = FakeClient('print("total=299")')
            checker = ValueRecomputeChecker(client, allowed_roots=(Path(d),))
            result = audit_items_with_ledger(
                [self._item("总数是否为299？", csv)],
                checkers=[checker],
            )

        self.assertEqual(result.ledger[0].status, "security_blocked")
        self.assertFalse(result.ledger[0].attempted)
        self.assertEqual(client.user_prompts, [])

    def test_mismatch_yields_rubric_target_error(self):
        v = self._run("输出文件中生日礼金的总人数是否为350人？", 'print("total=299")')
        self.assertEqual([x.defect_type for x in v], ["rubric_target_error"])
        self.assertTrue(v[0].review_only)
        self.assertEqual(v[0].evidence["missing_values"], [350.0])

    def test_data_not_available_is_operational_unknown(self):
        v = self._run("输出文件中生日礼金的总人数是否为299人？", 'print("DATA_NOT_AVAILABLE")')
        self.assertEqual([row.defect_type for row in v], ["llm_audit_failure"])
        self.assertEqual(v[0].defect_scope, "operational")
        self.assertEqual(v[0].evidence["failure_kind"], "inconclusive_recompute")

    def test_non_numeric_rubric_is_skipped(self):
        # a coverage rubric asserts no substantive value -> never recomputed
        self.assertEqual(self._run("输出文件中是否包含2024年1月至12月每个月的数据？", 'print("x=1")'), [])

    def test_unrunnable_code_is_operational_unknown(self):
        v = self._run("输出文件中生日礼金的总人数是否为299人？", 'raise ValueError("boom")')
        self.assertEqual([row.defect_type for row in v], ["llm_audit_failure"])
        self.assertEqual(v[0].defect_scope, "operational")

    def test_missing_container_dependency_is_not_silent_clean(self):
        with tempfile.TemporaryDirectory() as d:
            csv = Path(d) / "data.csv"
            csv.write_text("x\n1\n", encoding="utf-8")
            checker = ValueRecomputeChecker(
                FakeClient('print("total=299")'),
                runner=FailedDependencyRunner(),
                allowed_roots=(Path(d),),
            )
            result = audit_items_with_ledger(
                [self._item("输出文件中生日礼金的总人数是否为299人？", csv)],
                checkers=[checker],
            )

        self.assertEqual(result.ledger[0].status, "operational_failed")
        self.assertFalse(result.ledger[0].completed)
        self.assertEqual([row.defect_type for row in result.violations], ["llm_audit_failure"])

    def test_prompt_uses_sandbox_path_not_host_path(self):
        with tempfile.TemporaryDirectory() as d:
            csv = Path(d) / "sensitive.csv"
            csv.write_text("x\n1\n", encoding="utf-8")
            client = FakeClient('print("total=299")')
            checker = ValueRecomputeChecker(
                client,
                runner=InspectingContainerRunner(),
                allowed_roots=(Path(d),),
            )
            list(checker.check(self._item("总数是否为299？", csv)))

        self.assertIn("/workspace/inputs/0000_sensitive.csv", client.user_prompts[0])
        self.assertNotIn(str(csv.parent), client.user_prompts[0])

    def test_path_escape_is_security_blocked_before_execution(self):
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as outside:
            csv = Path(outside) / "secret.csv"
            csv.write_text("x\n1\n", encoding="utf-8")
            runner = InspectingContainerRunner()
            checker = ValueRecomputeChecker(
                FakeClient('print("total=299")'),
                runner=runner,
                allowed_roots=(Path(allowed),),
            )
            result = audit_items_with_ledger(
                [self._item("总数是否为299？", csv)],
                checkers=[checker],
            )

        self.assertEqual(result.ledger[0].status, "security_blocked")
        self.assertFalse(result.ledger[0].attempted)
        self.assertEqual(runner.workspace_files, [])


if __name__ == "__main__":
    unittest.main()
