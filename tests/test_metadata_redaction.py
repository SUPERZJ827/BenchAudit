import unittest

from benchcore.llm_auditor import strip_verified_metadata


class MetadataRedactionTest(unittest.TestCase):
    def test_platinum_supervision_is_not_sent_to_llm(self) -> None:
        metadata = {
            "audit_label": "wrong_gold",
            "cleaning_status": "revised",
            "platinum_target": "6",
            "human_defect": True,
            "problem_type": "Addition",
        }
        self.assertEqual(
            strip_verified_metadata(metadata),
            {"problem_type": "Addition"},
        )


if __name__ == "__main__":
    unittest.main()
