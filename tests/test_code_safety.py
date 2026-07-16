import unittest

from benchcore.code_safety import UnsafeGeneratedCode, validate_generated_table_code
from benchcore.code_verifier import CodeExecVerifier, _run_code
from benchcore.execution import RunResult
from benchcore.schema import BenchmarkItem


class _SuccessfulRunner:
    def run(self, command, policy):
        assert command.argv[-1] == "compute.py"
        assert command.cwd is not None
        assert policy.network_enabled is False
        assert policy.allow_local_process is False
        return RunResult(
            argv=command.argv,
            exit_code=0,
            stdout="3\n",
            stderr="",
            elapsed_seconds=0.01,
            timed_out=False,
            isolation="test_container",
            backend="test",
        )


class _UnusedClient:
    def chat_json(self, *args, **kwargs):
        raise AssertionError("eligibility must refuse before any LLM call")


def test_generated_table_code_accepts_normal_dataframe_computation():
    validate_generated_table_code(
        "values = pd.to_numeric(df['amount'])\nprint(values.sum())"
    )


def test_generated_table_code_rejects_escape_primitives():
    unsafe_examples = [
        "import os\nprint(os.getcwd())",
        "print(open('/etc/passwd').read())",
        "print((1).__class__.__mro__)",
        "pd.read_pickle('/tmp/input')\nprint(1)",
        "exec('print(1)')",
    ]
    for code in unsafe_examples:
        with unittest.TestCase().assertRaises(UnsafeGeneratedCode):
            validate_generated_table_code(code)


def test_run_code_rejects_unsafe_code_before_execution():
    output, error = _run_code("amount\n1\n", "print(open('/etc/passwd').read())")

    assert output is None
    assert error is not None and error.startswith("unsafe_code:")


def test_run_code_refuses_safe_code_without_an_explicit_runner():
    output, error = _run_code("amount\n1\n", "print(1)")

    assert output is None
    assert error == "execution_refused: no execution runner configured"


def test_code_exec_verifier_declares_missing_runner_security_blocked():
    item = BenchmarkItem(
        item_id="table-1",
        task="sum amount",
        gold="3",
        raw={"table": "| amount |\n|---|\n| 1 |\n| 2 |"},
    )

    eligibility = CodeExecVerifier(_UnusedClient()).audit_eligibility(item)

    assert eligibility.eligible is False
    assert eligibility.status == "security_blocked"


def test_run_code_computes_simple_dataframe_result():
    output, error = _run_code(
        "amount\n1\n2\n",
        "print(pd.to_numeric(df['amount']).sum())",
        runner=_SuccessfulRunner(),
    )

    assert error is None
    assert output == "3"
