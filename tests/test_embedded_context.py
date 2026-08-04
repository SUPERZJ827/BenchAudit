"""Where a referenced passage is looked for, and what this layer may claim.

The task statement is the most basic context a benchmark can carry and many
datasets ship nothing else, so the task text is checked before any attached
artifact.  Only an explicit label counts as inline material: an earlier
length-based fallback let a task that merely *described* a passage pass as if
it contained one, hiding a genuine omission.

Whether an attached artifact is the *right* material needs semantics, so any
non-empty match counts as present.  A deterministic checker may claim "nothing
is here"; it may not claim "the wrong thing is here".
"""

from __future__ import annotations

from benchcore.checkers import _has_embedded_context, locate_referenced_context
from benchcore.schema import BenchmarkItem

LABELLED = (
    "Answer the question using the context.\n\n"
    "Context: The war is known by several names. \"Polish-Soviet War\" is the "
    "most common but other names include Russo-Polish War of 1919-1921, and "
    "several further variants are discussed at length in the literature.\n\n"
    "Question: which name is most common?"
)
DESCRIBES_ONLY = (
    "Read the passage above. The passage discusses post-war European economic "
    "conditions including reconstruction efforts, currency reform, and the "
    "effects of the Marshall Plan on industrial output across many countries."
)
BARE = "According to the paragraph, what is the author's main claim?"


def _item(task: str, context: dict | None = None) -> BenchmarkItem:
    return BenchmarkItem(
        item_id="x", task=task, gold="g", context=context or {}, raw={}
    )


def test_labelled_inline_material_is_found_in_the_task():
    assert _has_embedded_context(LABELLED, "passage")
    assert locate_referenced_context(_item(LABELLED), LABELLED, "passage") == "task_text"


def test_task_that_only_describes_the_passage_is_not_treated_as_containing_it():
    """The length fallback used to pass this, hiding a real omission."""
    assert not _has_embedded_context(DESCRIBES_ONLY, "passage")
    assert locate_referenced_context(_item(DESCRIBES_ONLY), DESCRIBES_ONLY, "passage") == "not_found"


def test_bare_reference_reports_missing():
    assert locate_referenced_context(_item(BARE), BARE, "passage") == "not_found"


def test_any_attached_context_counts_as_present():
    """Deliberately loose: correspondence cannot be checked without semantics."""
    item = _item(BARE, {"context": "something.txt"})
    assert locate_referenced_context(item, BARE, "passage") == "attached_artifact"


def test_task_text_wins_over_an_attached_artifact():
    item = _item(LABELLED, {"context": "unrelated.png"})
    assert locate_referenced_context(item, LABELLED, "passage") == "task_text"


def test_non_inline_references_never_resolve_to_task_text():
    """An image, a file or a database cannot live in the task text."""
    for name in ("figure", "file", "database"):
        assert not _has_embedded_context(LABELLED, name)


def test_inline_table_is_recognised():
    task = (
        "Use the table below to answer.\n\n"
        "Table: | year | value |\n| 2020 | 11 |\n| 2021 | 14 |\n\n"
        "Which year was higher?"
    )
    assert _has_embedded_context(task, "table")
