from scripts.swe_leak_scan import added_lines, issue_hit_context, scan_instance, scan_rows


def test_added_lines_keeps_identifier_phrase_regression():
    patch = """diff --git a/x.py b/x.py
--- a/x.py
+++ b/x.py
@@
+and has_add_permission
+return None
+pass
+obj.value = calculate_total()
"""
    assert added_lines(patch) == [
        "and has_add_permission",
        "obj.value = calculate_total()",
    ]


def test_scan_instance_separates_problem_statement_from_hints_only():
    row = {
        "instance_id": "demo__repo-1",
        "patch": """diff --git a/x.py b/x.py
--- a/x.py
+++ b/x.py
@@
+if has_permission:
+result = fallback_value
""",
        "problem_statement": "The correct fix is to add if has_permission: before returning.",
        "hints_text": "A maintainer suggested result = fallback_value in a later comment.",
    }

    scanned = scan_instance(row)

    assert scanned is not None
    assert scanned["problem_statement_hits"] == ["if has_permission:"]
    assert scanned["hints_only_hits"] == ["result = fallback_value"]


def test_scan_rows_counts_hints_only_separately():
    rows = [
        {
            "instance_id": "ps-hit",
            "patch": "+value = calculate_total()\n",
            "problem_statement": "Please use value = calculate_total().",
            "hints_text": "",
        },
        {
            "instance_id": "hint-hit",
            "patch": "+value = calculate_total()\n",
            "problem_statement": "A bug happens.",
            "hints_text": "Maybe value = calculate_total() is right.",
        },
    ]

    candidates, hints_only = scan_rows(rows)

    assert [item["instance_id"] for item in candidates] == ["ps-hit"]
    assert [item["instance_id"] for item in hints_only] == ["hint-hit"]


def test_issue_hit_context_keeps_late_match():
    issue = "intro " + ("x" * 5000) + " use and has_add_permission in this condition"

    context = issue_hit_context(issue, ["and has_add_permission"], 1000)

    assert "and has_add_permission" in context
    assert context.startswith("[match context 1]")
    assert "preceding issue text omitted" in context
