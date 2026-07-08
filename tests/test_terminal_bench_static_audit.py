from scripts.audit_terminal_bench21_static import (
    created_test_paths,
    duplicate_numbered_steps,
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
