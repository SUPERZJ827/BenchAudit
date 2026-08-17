from benchcore.reference_schema import ReferenceSchemaChecker, reference_schema_issues
from benchcore.schema import BenchmarkItem


def _item(reference, parameters):
    return BenchmarkItem(
        item_id="schema",
        raw={"reference_solution": {"make": reference}},
        task="Call make.",
        context={"available_functions": [{"name": "make", "parameters": parameters}]},
    )


def test_reference_schema_finds_nested_enum_mismatch():
    item = _item(
        {"steps": [{"start": "07:30"}]},
        {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"start": {"type": "string", "enum": ["07:00", "08:00"]}},
                        "required": ["start"],
                    },
                }
            },
            "required": ["steps"],
        },
    )
    issues = reference_schema_issues(item)
    assert issues == [{
        "path": "make.steps[0].start",
        "kind": "enum_mismatch",
        "value": "07:30",
        "allowed": ["07:00", "08:00"],
    }]
    findings = list(ReferenceSchemaChecker().check(item))
    assert [finding.defect_type for finding in findings] == ["reference_schema_mismatch"]
    assert findings[0].evidence_tier == "review"


def test_reference_schema_accepts_valid_nested_call():
    item = _item(
        {"steps": [{"start": "07:00"}]},
        {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"start": {"type": "string", "enum": ["07:00", "08:00"]}},
                        "required": ["start"],
                    },
                }
            },
            "required": ["steps"],
        },
    )
    assert reference_schema_issues(item) == []


def test_reference_schema_keeps_integer_distinct_from_boolean():
    item = _item({"count": True}, {"type": "object", "properties": {"count": {"type": "integer"}}})
    assert reference_schema_issues(item)[0]["kind"] == "type_mismatch"
