import unittest

from benchcore.code_safety import UnsafeGeneratedCode, validate_generated_table_code
from benchcore.code_verifier import _run_code


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


def test_run_code_computes_simple_dataframe_result():
    output, error = _run_code("amount\n1\n2\n", "print(pd.to_numeric(df['amount']).sum())")

    assert error is None
    assert output == "3"
