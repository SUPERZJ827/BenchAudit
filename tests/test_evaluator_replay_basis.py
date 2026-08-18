from __future__ import annotations

import unittest

from benchcore.evaluators import ITEM_SCORING_KEY
from benchcore.methods import EvaluatorReplayChecker
from benchcore.schema import BenchmarkItem


def item(evaluator: str | None = None, scoring: dict | None = None) -> BenchmarkItem:
    """A record whose declared comparison rejects its own non-numeric gold."""
    metadata: dict = {}
    if scoring is not None:
        metadata[ITEM_SCORING_KEY] = scoring
    return BenchmarkItem(
        item_id="x::1",
        raw={},
        task="q",
        context={},
        gold="hello",
        aliases=[],
        evaluator=evaluator,
        metadata=metadata,
    )


class EvaluatorReplayBasisTest(unittest.TestCase):
    def replay(self, **kwargs) -> list:
        return list(EvaluatorReplayChecker().check(item(**kwargs)))

    def test_adapter_label_basis_is_review_only(self) -> None:
        # The comparison came from a string the adapter wrote, not from anything
        # the benchmark established, so it cannot carry a critical verdict.
        found = self.replay(evaluator="numeric")
        self.assertEqual([v.defect_type for v in found], ["gold_rejected_by_evaluator"])
        self.assertEqual(found[0].severity, "review")
        self.assertTrue(found[0].review_only)
        self.assertEqual(found[0].evidence["contract_basis"], "adapter_label")

    def test_profile_basis_stays_critical(self) -> None:
        # A profile read the benchmark's own rows, so the rejection is a claim
        # about the benchmark rather than about our labelling.  The declared
        # label is present too; the profile is what decided the comparison.
        found = self.replay(evaluator="numeric", scoring={"comparison": "numeric_tolerance"})
        self.assertEqual(found[0].severity, "critical")
        self.assertEqual(found[0].evidence["contract_basis"], "profile")

    def test_no_basis_confirms_without_running_the_real_evaluator(self) -> None:
        # Severity says how bad the claim would be; the promotion policy still
        # keeps every modelled replay at review, because the benchmark's own
        # scoring was never run.
        for kwargs in ({"evaluator": "numeric"},
                       {"evaluator": "numeric", "scoring": {"comparison": "numeric_tolerance"}}):
            with self.subTest(**kwargs):
                self.assertTrue(self.replay(**kwargs)[0].review_only)


if __name__ == "__main__":
    unittest.main()
