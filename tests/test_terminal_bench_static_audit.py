from scripts.audit_terminal_bench21_static import (
    audit_repo,
    created_test_paths,
    derive_generated_instruction_paths,
    duplicate_numbered_steps,
    extract_paths,
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


def test_unquoted_sentence_final_output_filename_is_extracted():
    instruction = "The output fasta file should be titled primers.fasta."

    assert extract_instruction_output_paths(instruction) == {"/app/primers.fasta"}
    assert extract_paths(instruction, include_relative=True) == {"/app/primers.fasta"}


def test_relative_path_extraction_rejects_versions_and_python_method_names():
    text = 'Install grpcio 1.73.0 and call terminal.send_keystrokes("echo ok").'

    assert extract_paths(text, include_relative=True) == set()


def test_test_generated_paths_include_shell_redirection_and_command_output_flags():
    text = '''
terminal.send_keystrokes("echo ok > /app/test.txt")
subprocess.run(["povray", "+O/app/render.tga"])
assert Path("/app/test.txt").exists()
assert Path("/app/render.tga").exists()
'''

    assert created_test_paths(text) >= {"/app/test.txt", "/app/render.tga"}


def test_test_generated_paths_resolve_list_style_output_and_env_indirection():
    text = '''
cmd = ["tool", "--output_path", "/app/result.csv", "-o", "binary"]
terminal.send_keystrokes("export SECRET=/app/secret.txt")
terminal.send_keystrokes("echo ok > $SECRET")
terminal.send_keystrokes("vim /app/edited.txt")
'''

    assert created_test_paths(text) >= {
        "/app/result.csv",
        "/app/binary",
        "/app/secret.txt",
        "/app/edited.txt",
    }


def test_test_generated_paths_resolve_helper_writes_and_shell_cwd():
    text = '''
tmp_script = Path("/app/_probe.vim")
_write_probe(source, tmp_script)
cd ocaml
make test | tee tests.txt
'''

    assert created_test_paths(text) >= {
        "/app/_probe.vim",
        "/app/ocaml/tests.txt",
    }


def test_relative_quoted_directory_covers_files_below_it():
    assert extract_paths("Inspect files in `warriors/`.", include_relative=True) == {
        "/app/warriors"
    }


def test_protobuf_generation_derives_conventional_python_artifacts():
    instruction = """
Create /app/kv-store.proto and generate the Python protobuf and gRPC files.
"""
    paths = extract_paths(instruction, include_relative=True)

    assert derive_generated_instruction_paths(instruction, paths) == {
        "/app/kv_store_pb2.py",
        "/app/kv_store_pb2_grpc.py",
    }


def test_audit_does_not_flag_verifier_generated_or_declared_outputs(tmp_path):
    task = tmp_path / "tasks" / "example"
    (task / "tests").mkdir(parents=True)
    (task / "instruction.md").write_text(
        "Write the final output to result.txt.", encoding="utf-8"
    )
    (task / "tests" / "test_outputs.py").write_text(
        '''
from pathlib import Path
import subprocess
subprocess.run(["tool", "+O/app/probe.tga"])
assert Path("/app/probe.tga").exists()
assert Path("/app/result.txt").exists()
''',
        encoding="utf-8",
    )

    assert audit_repo(tmp_path, None) == []
