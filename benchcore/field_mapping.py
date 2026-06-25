from __future__ import annotations

from typing import Any

from .schema import FieldMapping


ID_FIELDS = ("item_id", "id", "instance_id", "task_id", "question_id", "uid")
TASK_FIELDS = (
    "question",
    "prompt",
    "instruction",
    "task",
    "task_description",
    "problem",
    "problem_statement",
    "user_query",
    "query",
    "input",
)
CONTEXT_FIELDS = (
    "context",
    "passage",
    "article",
    "document",
    "documents",
    "schema",
    "database_schema",
    "db_schema",
    "hkb",
    "metadata_files",
    "attachments",
    "files",
    "image",
    "images",
    "table",
    "tables",
    "repo",
    "repository",
)
CHOICE_FIELDS = ("choices", "options", "answer_choices", "candidates")
GOLD_FIELDS = (
    "gold",
    "answer",
    "correct_answer",
    "gold_answer",
    "final_answer",
    "target",
    "label",
    "gold_sql",
    "reference",
    "reference_solution",
)
ALIAS_FIELDS = ("aliases", "accepted_answers", "acceptable_answers", "equivalent_outputs")
OUTPUT_FIELDS = (
    "output_contract",
    "expected_output",
    "output_format",
    "answer_type",
    "submission_format",
)
EVALUATOR_FIELDS = (
    "evaluator",
    "evaluation",
    "metric",
    "rubric",
    "tests",
    "test_cases",
    "checker",
    "scoring",
)
METADATA_FIELDS = (
    "metadata",
    "task_type",
    "subject",
    "domain",
    "category",
    "source",
    "split",
    "version",
    "error_type",
    "verified_gold",
    "verified_answer_text",
)


def _first_present(keys: tuple[str, ...], row: dict[str, Any]) -> str | None:
    lowered = {k.lower(): k for k in row}
    for key in keys:
        if key in lowered:
            return lowered[key]
    return None


def _present_many(keys: tuple[str, ...], row: dict[str, Any]) -> list[str]:
    lowered = {k.lower(): k for k in row}
    return [lowered[key] for key in keys if key in lowered]


def infer_mapping(rows: list[dict[str, Any]]) -> FieldMapping:
    sample: dict[str, Any] = {}
    for row in rows[:100]:
        sample.update(row)
    return FieldMapping(
        item_id=_first_present(ID_FIELDS, sample),
        task=_first_present(TASK_FIELDS, sample),
        context=_present_many(CONTEXT_FIELDS, sample),
        choices=_first_present(CHOICE_FIELDS, sample),
        gold=_first_present(GOLD_FIELDS, sample),
        aliases=_first_present(ALIAS_FIELDS, sample),
        output_contract=_first_present(OUTPUT_FIELDS, sample),
        evaluator=_first_present(EVALUATOR_FIELDS, sample),
        metadata=_present_many(METADATA_FIELDS, sample),
    )


def mapping_from_dict(data: dict[str, Any]) -> FieldMapping:
    return FieldMapping(
        item_id=data.get("item_id"),
        task=data.get("task"),
        context=list(data.get("context", [])),
        choices=data.get("choices"),
        gold=data.get("gold"),
        aliases=data.get("aliases"),
        output_contract=data.get("output_contract"),
        evaluator=data.get("evaluator"),
        metadata=list(data.get("metadata", [])),
    )
