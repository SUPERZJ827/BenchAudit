import unittest

from scripts.output_l1_verifier import rubric_values


class RubricValuesTest(unittest.TestCase):
    """rubric_values() keeps only substantive numeric CLAIMS and drops the numbers that
    caused B2 false positives (identifiers, indices, years, filenames, thresholds/ranges).
    These cases trace to reports/verified_defects.md and the 2026-07-04 broad-scan FP classes."""

    def test_keeps_plain_asserted_counts(self):
        self.assertEqual(rubric_values("Does the report clearly count 27 purchase orders pending approval?"), [27.0])
        self.assertEqual(rubric_values("Is the total number of hospitals in the eastern region 15,102?"), [15102.0])

    def test_drops_identifier_numbers_keeps_the_count(self):
        # the '6' is the asserted count; PO #1013 ... are identifiers, not recompute targets.
        self.assertEqual(
            rubric_values("count 6 approved purchase orders, namely PO #1013, #1006, #1007, #1012"),
            [6.0])

    def test_drops_threshold_numbers(self):
        # 'at least 10' is a minimum condition, never a value a recompute reproduces.
        self.assertEqual(rubric_values("Does the report provide at least 10 specific improvement suggestions?"), [])
        # a >=50% share is a threshold; 729 is the real value (broad-scan id=108 FP class).
        self.assertEqual(rubric_values("clearly indicate that the unique order count is 729, a >=50% share"), [729.0])

    def test_drops_range_keeps_specific_value(self):
        # '35%-45%' is a tolerance range; '40%' is the asserted result.
        self.assertEqual(rubric_values("Is the sample proportion within the range of 35%-45%, specifically 40%?"), [40.0])

    def test_drops_filenames_codes_ordinals_years(self):
        self.assertEqual(rubric_values("Was 4-financial-table.xlsx generated for Partner 3 in 2024, code SR-021?"), [])

    def test_drops_chinese_year_and_month_keeps_the_count(self):
        # 2024年 / 01月 are calendar references; 13 is the asserted headcount (仓敏_5 B2 FP class).
        self.assertEqual(rubric_values("输出文件中2024年01月的生日礼金人数是否为13人？"), [13.0])
        self.assertEqual(rubric_values("输出文件中2024年12月的年终奖励人数是否为84人？"), [84.0])

    def test_drops_chinese_month_range_leaves_no_value(self):
        # a month-coverage check asserts no numeric result -- must not be recomputed at all.
        self.assertEqual(rubric_values("输出文件中是否包含2024年1月至12月每个月的福利数据？"), [])


if __name__ == "__main__":
    unittest.main()
