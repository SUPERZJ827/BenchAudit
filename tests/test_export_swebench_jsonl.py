from scripts.export_swebench_jsonl import with_benchcore_fields


def test_with_benchcore_fields_preserves_raw_and_adds_generic_artifacts():
    row = {
        "instance_id": "repo__repo-1",
        "repo": "org/repo",
        "problem_statement": "Fix the bug.",
        "patch": "diff --git a/x.py b/x.py\n+value = 1\n",
        "test_patch": "diff --git a/test_x.py b/test_x.py\n+def test_bug(): pass\n",
        "FAIL_TO_PASS": ["test_x.py::test_bug"],
        "PASS_TO_PASS": ["test_x.py::test_old"],
        "base_commit": "abc123",
    }

    out = with_benchcore_fields(row)

    assert out["instance_id"] == "repo__repo-1"
    assert out["item_id"] == "repo__repo-1"
    assert out["task"] == "Fix the bug."
    assert out["gold"] == row["patch"]
    assert out["output_contract"]["type"] == "git_patch"
    assert out["evaluator"]["type"] == "swebench_pytest"
    assert out["evaluator"]["fail_to_pass"] == ["test_x.py::test_bug"]
    assert out["metadata"]["repo"] == "org/repo"
    assert out["metadata"]["base_commit"] == "abc123"
