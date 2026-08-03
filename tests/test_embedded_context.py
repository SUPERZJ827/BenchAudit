"""The task statement is the most basic context a benchmark can carry.

Many datasets ship nothing but a task. Looking only for a separate context
artifact reports every self-contained item as missing its own content: on one
held-out benchmark this produced 242 false "missing context" findings because
the label used was "Context:", which the phrase list did not contain.
"""

from __future__ import annotations

from benchcore.checkers import _has_embedded_context

SQUAD = (
    "Answer the question using the information in the context.\n\n"
    "Context: The war is known by several names. \"Polish-Soviet War\" is the "
    "most common but other names include Russo-Polish War of 1919-1921, and "
    "several further variants are discussed at length in the literature.\n\n"
    "Question: which name is most common?"
)
BARE_REFERENCE = "According to the passage, what is the author's main claim?"


def test_labelled_inline_context_is_recognised():
    assert _has_embedded_context(SQUAD, "passage")


def test_unlabelled_but_substantial_task_is_recognised():
    """A phrase list can never be complete, so length beyond the reference
    sentence also counts."""
    task = (
        "The treaty reshaped the region for a generation and its terms were "
        "debated for decades afterwards by historians of several schools. "
        "What does the paragraph say about the outcome?"
    )
    assert _has_embedded_context(task, "passage")


def test_bare_reference_without_material_still_fires():
    assert not _has_embedded_context(BARE_REFERENCE, "passage")


def test_non_inline_references_are_unaffected():
    """An image, a file or a database cannot live in the task text, so the
    artifact check must still stand for them."""
    for name in ("figure", "file", "database"):
        assert not _has_embedded_context(SQUAD, name)


def test_inline_table_is_recognised():
    task = (
        "Use the table below to answer.\n\n"
        "Table: | year | value |\n| 2020 | 11 |\n| 2021 | 14 |\n\n"
        "Which year was higher?"
    )
    assert _has_embedded_context(task, "table")
