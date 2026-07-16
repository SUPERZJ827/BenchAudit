from benchcore.schema import BenchmarkItem
from benchcore.swe_leak import SolutionLeakChecker


class FakeLLMClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def chat_json(self, system, user):
        self.calls.append((system, user))
        return dict(self.response)


def make_item() -> BenchmarkItem:
    return BenchmarkItem(
        item_id="django__django-16527",
        raw={
            "repo": "django/django",
            "problem_statement": "The fix is to add `and has_add_permission`.",
            "hints_text": "A comment mentions other_code = value.",
            "patch": """diff --git a/x.py b/x.py
--- a/x.py
+++ b/x.py
@@
+and has_add_permission
+other_code = value
""",
        },
        task="The fix is to add `and has_add_permission`.",
    )


def test_solution_leak_checker_emits_review_literal_candidate_without_llm():
    violations = list(SolutionLeakChecker().check(make_item()))

    by_type = {violation.defect_type: violation for violation in violations}
    assert "solution_leak" in by_type
    assert by_type["solution_leak"].review_only
    assert by_type["solution_leak"].detection_method == "solution_leak_literal"
    assert by_type["solution_leak"].evidence["matched_lines"] == ["and has_add_permission"]
    assert "hints_only_solution_leak" not in by_type


def test_solution_leak_checker_emits_hints_only_when_problem_statement_is_clean():
    item = make_item()
    item.raw["problem_statement"] = "The issue describes a bug without the repair line."
    item.task = item.raw["problem_statement"]

    violations = list(SolutionLeakChecker().check(item))

    assert [violation.defect_type for violation in violations] == [
        "hints_only_solution_leak"
    ]


def test_solution_leak_checker_keeps_llm_semantic_verdict_at_review_tier():
    client = FakeLLMClient(
        {
            "verdict": "solution_leaked",
            "evidence": "The issue explicitly says to add the matched line.",
        }
    )

    violations = list(SolutionLeakChecker(client).check(make_item()))

    finding = next(v for v in violations if v.defect_type == "solution_leak")
    assert finding.review_only
    assert finding.evidence_tier == "review"
    assert finding.proof_kind == "model_judgment"
    assert finding.severity == "major"
    assert finding.detection_method == "solution_leak_literal+llm_confirm"
    assert finding.evidence["llm_result"]["verdict"] == "solution_leaked"
    assert client.calls


def test_solution_leak_checker_suppresses_incidental_problem_match():
    client = FakeLLMClient(
        {
            "verdict": "reproduction_or_incidental",
            "evidence": "The match is only traceback context.",
        }
    )

    violations = list(SolutionLeakChecker(client, report_hints_only=False).check(make_item()))

    assert [violation.defect_type for violation in violations] == []
