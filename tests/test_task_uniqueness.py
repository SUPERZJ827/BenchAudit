"""Tests for the task-output multiplicity classifier.

Cases are drawn from the real DS-1000 prompts that produced false-positive
"surviving mutant" signals in the 200-item pilot (ids 340 / 348 / 376), plus a
genuine unique-output task that must NOT be deprioritised.
"""
from benchcore.task_uniqueness import classify_task_multiplicity, triage_rank


def test_order_agnostic_is_declared_high():
    # DS-1000 id=340
    v = classify_task_multiplicity(
        "I want to iterate through all elements and store them in result (a 1D "
        "list). I do not care about the order. How do I achieve this?"
    )
    assert v.verdict == "declared"
    assert v.confidence == "high"
    assert v.triage == "by_design"
    assert any(s.category == "order_agnostic" for s in v.signals)


def test_existential_one_of_is_declared_high():
    # DS-1000 id=348
    v = classify_task_multiplicity(
        "How to get one maximal set of linearly independent vectors of a matrix a?"
    )
    assert v.verdict == "declared"
    assert v.confidence == "high"
    assert any(s.category == "existential" for s in v.signals)


def test_randomness_is_declared_low():
    # DS-1000 id=376
    v = classify_task_multiplicity(
        "I want to generate a random array of size N which only contains 0 and 1, "
        "with 90% of the array being 1 and randomly placed."
    )
    assert v.verdict == "declared"
    assert v.confidence == "low"
    assert v.triage == "ambiguous"


def test_unique_output_task_is_priority():
    # DS-1000 id=11 style: a specific, unique required transformation.
    v = classify_task_multiplicity(
        "I have a DataFrame with a timezone-aware datetime column. I want to "
        "remove the timezone information so the column becomes timezone-naive."
    )
    assert v.verdict == "none_found"
    assert v.triage == "priority"
    assert v.signals == []


def test_setup_randomness_in_code_block_is_ignored():
    # "random" only appears in the given setup code, not the requested output.
    prompt = (
        "I have a 2D array X and want the row sums.\n<code>\n"
        "X = np.random.randint(0, 9, (5, 6))\n</code>\nresult = ...\nBEGIN SOLUTION"
    )
    v = classify_task_multiplicity(prompt)
    assert v.verdict == "none_found"


def test_empty_prompt():
    v = classify_task_multiplicity("")
    assert v.verdict == "none_found"
    assert v.confidence == "none"


def test_broad_markers_do_not_fire_on_question_content():
    # These phrasings describe question content, not output multiplicity. They
    # produced cross-benchmark false positives before the existential markers
    # were tightened, and within DS-1000 too.
    for content in [
        "Which is an example of a physical change?",            # ARC (MCQ)
        "Brendan has a bag of marbles. One of them is red.",    # GSM8K narrative
        "Here is an example of converting a categorical column.",  # DS-1000 id=20
        "sorting a MultiIndexed DataFrame by one of the indexers",  # DS-1000 id=276
    ]:
        assert classify_task_multiplicity(content).verdict == "none_found", content
    # But a genuine output-multiplicity declaration still fires.
    assert classify_task_multiplicity(
        "get one maximal set of linearly independent vectors"
    ).verdict == "declared"


def test_triage_rank_orders_priority_first():
    # A review queue sorted by this key must surface priority above by_design.
    order = sorted(["by_design", "priority", "ambiguous"], key=triage_rank)
    assert order == ["priority", "ambiguous", "by_design"]
    # Unknown/missing triage must not sink below real suspects.
    assert triage_rank("unknown") == triage_rank("priority")
