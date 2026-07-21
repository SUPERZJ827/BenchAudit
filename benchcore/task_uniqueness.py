"""Task-output multiplicity classifier — a triage oracle, never a confirmation.

When an execution audit finds that a benchmark's harness *accepts an output that
differs from the reference* (a surviving mutant), that is only a defect if the
task actually demands a **unique** output. Many tasks legitimately admit several
correct outputs — "return the elements in any order", "generate a random array",
"find one maximal independent set" — and there the lenient harness is *correct*,
not buggy. Distinguishing the two is a semantic judgement about the task, so it
can NEVER promote anything to `confirmed`; the promotion red line stands. What it
*can* do is triage the review queue:

  * a task that *declares* multiplicity  -> the surviving mutant is expected;
    tag it `by_design` so a human (or a downstream filter) can skip it;
  * a task with *no* multiplicity markers -> the surviving mutant is a genuine
    over-leniency suspect; tag it `priority` so a human triages it first.

This raises the precision of the `underconstrained_evaluator_risk` review queue
and puts the deciding evidence (the exact task phrase) in front of the reviewer.

The classifier is deterministic and lexical on purpose: every verdict carries the
matched phrase as its justification, so a reviewer can override it at a glance. An
LLM layer could later escalate the `none_found` cases, but is intentionally left
out of v1 to keep the signal explainable.

Scope: calibrated for imperative "how do I compute X" code-task prompts (DS-1000
style), where a multiplicity phrase refers to the requested output. It is NOT a
general question classifier -- on multiple-choice/QA phrasings ("which is an
example of ...", "one of them has 10 marbles") the same words describe question
content, so the markers were tightened to output-declaring forms and the caller
should not rely on it outside code-task auditing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Each pattern is grounded in real DS-1000 phrasings. Categories are ranked by how
# reliably they imply the *output* (not merely a test input) may take many forms.
# High-confidence categories assert multiplicity of the answer directly; the
# randomness category is weaker because "random" often describes given test data.
_HIGH_CONFIDENCE: dict[str, tuple[str, ...]] = {
    "order_agnostic": (
        r"do(?:es)?\s+n(?:o|')t\s+(?:care|matter)[^.]{0,40}?\border\b",
        r"\bin\s+any\s+order\b",
        r"\border\s+(?:does\s*n(?:o|')t|is\s+not)\s+(?:matter|important)\b",
        r"\bregardless\s+of\s+(?:the\s+)?order\b",
        r"\border[-\s]?independent\b",
        r"\bunordered\b",
    ),
    # Only phrasings that qualify the requested OUTPUT as one of several valid
    # ones ("one maximal set", "any valid solution"). Broad phrases like "an
    # example of" or "one of the columns" describe question content, not output
    # multiplicity -- they produced false positives both across other benchmarks
    # (ARC "which is an example of...", GSM8K "one of them has 10 marbles") and
    # within DS-1000 ("here is an example of input", "sort by one of the
    # indexers"), so they are deliberately excluded.
    "existential": (
        r"\b(?:one|any|a)\s+(?:maximal|possible|valid|such)\b",
        r"\bany\s+valid\s+(?:answer|solution|output|result|combination)\b",
    ),
    "explicit_multiple": (
        r"\bmultiple\s+(?:valid\s+)?(?:answers?|solutions?|outputs?|results?)\b",
        r"\bmore\s+than\s+one\s+(?:answer|solution|way|result)\b",
        r"\b(?:several|many)\s+(?:valid\s+)?(?:answers?|solutions?|ways)\b",
    ),
}
_LOW_CONFIDENCE: dict[str, tuple[str, ...]] = {
    "randomness": (
        r"\brandom(?:ly|ized)?\b",
        r"\bshuffl(?:e|ed|ing)\b",
    ),
}

_HIGH = {c: tuple(re.compile(p, re.IGNORECASE) for p in ps)
         for c, ps in _HIGH_CONFIDENCE.items()}
_LOW = {c: tuple(re.compile(p, re.IGNORECASE) for p in ps)
        for c, ps in _LOW_CONFIDENCE.items()}


@dataclass
class MultiplicitySignal:
    category: str
    phrase: str


@dataclass
class TaskMultiplicity:
    """Verdict on whether a task's correct output is plausibly non-unique."""

    verdict: str  # "declared" (markers found) | "none_found"
    confidence: str  # "high" | "low" | "none"
    signals: list[MultiplicitySignal] = field(default_factory=list)

    @property
    def triage(self) -> str:
        """How a reviewer should prioritise a surviving-mutant on this task."""
        if self.verdict == "declared":
            return "by_design" if self.confidence == "high" else "ambiguous"
        return "priority"

    def as_evidence(self) -> dict:
        return {
            "task_multiplicity": self.verdict,
            "task_multiplicity_confidence": self.confidence,
            "task_multiplicity_triage": self.triage,
            "task_multiplicity_signals": [
                {"category": s.category, "phrase": s.phrase} for s in self.signals
            ],
        }


# Lower rank = review it first. Used to order a review queue so genuine
# over-leniency suspects surface above tasks that declare their own multiplicity.
_TRIAGE_ORDER = {"priority": 0, "ambiguous": 1, "by_design": 2}


def triage_rank(triage: str) -> int:
    """Sort key for a review queue; unknown triage sorts with `priority`."""
    return _TRIAGE_ORDER.get(triage, 0)


def _natural_language(prompt: str) -> str:
    """Keep only the natural-language ask.

    DS-1000 prompts interleave the problem statement with ``<code>`` setup blocks
    and a trailing ``BEGIN SOLUTION`` scaffold. Stripping those avoids matching
    multiplicity words that belong to given test *inputs* (e.g. a setup line
    ``X = np.random.randint(...)``) rather than the requested output.
    """
    text = re.split(r"BEGIN\s+SOLUTION", prompt, maxsplit=1, flags=re.IGNORECASE)[0]
    text = re.sub(r"<code>.*?</code>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    return text


def classify_task_multiplicity(prompt: str) -> TaskMultiplicity:
    """Classify whether a task plausibly admits multiple correct outputs.

    Deterministic and lexical: the returned signals ARE the justification. A
    "declared" verdict is a reason to *deprioritise* a surviving-mutant finding,
    never to suppress it silently and never to confirm a defect.
    """
    if not prompt:
        return TaskMultiplicity("none_found", "none")
    text = _natural_language(prompt)
    signals: list[MultiplicitySignal] = []
    for category, patterns in _HIGH.items():
        for pat in patterns:
            m = pat.search(text)
            if m:
                signals.append(MultiplicitySignal(category, m.group(0).strip()))
                break
    high_hit = bool(signals)
    for category, patterns in _LOW.items():
        for pat in patterns:
            m = pat.search(text)
            if m:
                signals.append(MultiplicitySignal(category, m.group(0).strip()))
                break
    if high_hit:
        return TaskMultiplicity("declared", "high", signals)
    if signals:  # only low-confidence markers matched
        return TaskMultiplicity("declared", "low", signals)
    return TaskMultiplicity("none_found", "none")
