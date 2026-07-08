from scripts.audit_terminal_bench21_static import (
    created_test_paths,
    duplicate_numbered_steps,
    extract_instruction_output_paths,
    extract_test_exists_paths,
)


def test_extract_test_exists_paths_resolves_pathlib_joins():
    text = '''
from pathlib import Path
app_dir = Path("/app")
ars_file = app_dir / "ars.R"
assert ars_file.exists()
'''

    assert extract_test_exists_paths(text) == {"/app/ars.R"}


def test_test_created_paths_excludes_temporary_pathlib_files():
    text = '''
from pathlib import Path
app_dir = Path("/app")
tmp_file = app_dir / "run_test.R"
tmp_file.write_text("source('ars.R')")
tmp_file.unlink()
'''

    assert created_test_paths(text) == {"/app/run_test.R"}


def test_duplicate_numbered_steps_detects_repeated_labels():
    instruction = """
1) Do the first thing.
2) Do the second thing.
2) Do a repeated second thing.
"""

    assert duplicate_numbered_steps(instruction) == ["2"]


def test_instruction_output_paths_ignore_versions_urls_and_classes():
    instruction = """
Generate a report comparing version 1.36.8 with example.com references.
Include SetValRequest and KVStore examples in the writeup.
"""

    assert extract_instruction_output_paths(instruction) == set()


def test_instruction_output_paths_keep_explicit_relative_files():
    instruction = """
Write the final answer to `result.json`.
Create a binary executable called `doomgeneric_mips`.
The input file `data.txt` is already provided.
"""

    assert extract_instruction_output_paths(instruction) == {"/app/result.json", "/app/doomgeneric_mips"}


def test_instruction_output_paths_skip_inputs_before_or_after_output_clause():
    instruction = """
You're given an image at `/app/code.png`. Write the result to `/app/output.txt`.
Create a file called "/app/solution.txt" with the word found in "secret_file.txt" in the "secrets.7z" archive.
"""

    assert extract_instruction_output_paths(instruction) == {"/app/output.txt", "/app/solution.txt"}
