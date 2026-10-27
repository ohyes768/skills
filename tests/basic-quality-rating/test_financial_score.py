import importlib.util
import itertools
import math
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "finance-macro/basic-quality-rating/scripts/financial_score.py"
)
spec = importlib.util.spec_from_file_location("financial_score", SCRIPT)
financial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(financial)


def stock(**changes):
    data = {
        "code": "000001",
        "name": "虚构制造公司",
        "sw_level1": "机械设备",
        "sw_level2": "专用设备",
        "roe_avg_3y": 18,
        "roe_year": 2025,
        "roe_history": [
            {"year": 2023, "value": 15},
            {"year": 2024, "value": 17},
            {"year": 2025, "value": 18},
        ],
        "annual_profit_year": 2025,
        "net_profit_ex_non_recurring_yoy": 8,
        "previous_quarter_yoy_pct": 6,
        "previous_quarter_label": "2026Q1",
        "latest_quarter_yoy_pct": 7,
        "latest_quarter_label": "2026Q2",
        "debt_asset_ratio": 20,
    }
    data.update(changes)
    return data


class FinancialScoreTests(unittest.TestCase):
    def test_complete_stock_and_trace(self):
        result = financial.score_financial(stock())
        self.assertEqual(result["score"], 5)
        self.assertEqual(result["status"], "scored")
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["sector"], "ordinary")
        self.assertEqual(
            {c["rule"] for c in result["checks"]},
            {"roe_base", "debt", "earnings", "roe_trend", "severe_weaknesses"},
        )
        for check in result["checks"]:
            self.assertIn("input", check)
            self.assertIn("period", check)
            self.assertIn("reason", check)

    def test_roe_thresholds_including_zero_and_negatives(self):
        for value, expected in (
            (-1, 1),
            (0, 1),
            (4.9999, 1),
            (5, 2),
            (7.9999, 2),
            (8, 3),
            (11.9999, 3),
            (12, 4),
            (14.9999, 4),
            (15, 5),
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    financial.score_financial(stock(roe_avg_3y=value))["score"],
                    expected,
                )

    def test_debt_thresholds_by_industry(self):
        for sector, values in (
            (
                "机械设备",
                ((40, 5), (40.0001, 4), (60, 4), (60.0001, 4), (75, 4), (75.0001, 2)),
            ),
            (
                "公用事业",
                ((55, 5), (55.0001, 4), (70, 4), (70.0001, 4), (80, 4), (80.0001, 2)),
            ),
            ("交通运输", ((55, 5), (55.0001, 4), (80, 4), (81, 2))),
        ):
            for value, expected in values:
                with self.subTest(sector=sector, value=value):
                    self.assertEqual(
                        financial.score_financial(
                            stock(sw_level1=sector, debt_asset_ratio=value)
                        )["score"],
                        expected,
                    )

    def test_profit_sign_combinations(self):
        for annual, previous, latest in itertools.product((-1, 0, 1), repeat=3):
            expected = (
                2
                if previous < 0 and latest < 0
                else 3
                if previous < 0 or latest < 0
                else 5
                if annual > 0 and previous > 0 and latest > 0
                else 4
            )
            with self.subTest(values=(annual, previous, latest)):
                self.assertEqual(
                    financial.score_financial(
                        stock(
                            net_profit_ex_non_recurring_yoy=annual,
                            previous_quarter_yoy_pct=previous,
                            latest_quarter_yoy_pct=latest,
                        )
                    )["score"],
                    expected,
                )

    def test_roe_trends(self):
        for values, expected in (
            ((15, 16, 17), 5),
            ((18, 17, 18), 5),
            ((15, 18, 17), 4),
            ((18, 17, 16), 2),
        ):
            history = [
                {"year": year, "value": value}
                for year, value in zip((2023, 2024, 2025), values)
            ]
            with self.subTest(values=values):
                self.assertEqual(
                    financial.score_financial(stock(roe_history=history))["score"],
                    expected,
                )

    def test_all_severe_weakness_combinations(self):
        for weak_roe, weak_debt, weak_profit, weak_trend in itertools.product(
            (False, True), repeat=4
        ):
            changes = {
                "roe_avg_3y": 6 if weak_roe else 18,
                "debt_asset_ratio": 90 if weak_debt else 20,
                "previous_quarter_yoy_pct": -1 if weak_profit else 1,
                "latest_quarter_yoy_pct": -1 if weak_profit else 1,
                "roe_history": [
                    {"year": y, "value": v}
                    for y, v in zip(
                        (2023, 2024, 2025), (18, 17, 16) if weak_trend else (16, 17, 18)
                    )
                ],
            }
            weak_count = sum((weak_roe, weak_debt, weak_profit, weak_trend))
            expected = 1 if weak_count >= 2 else 2 if weak_count else 5
            self.assertEqual(
                financial.score_financial(stock(**changes))["score"], expected
            )

    def test_missing_and_invalid_required_numeric_values_are_not_zero(self):
        for field in (
            "roe_avg_3y",
            "debt_asset_ratio",
            "net_profit_ex_non_recurring_yoy",
            "previous_quarter_yoy_pct",
            "latest_quarter_yoy_pct",
        ):
            for value in (None, True, "18", math.nan, math.inf, -math.inf):
                with self.subTest(field=field, value=value):
                    result = financial.score_financial(stock(**{field: value}))
                    self.assertIsNone(result["score"])
                    self.assertEqual(result["status"], "insufficient_data")
                    self.assertTrue(any(field in issue for issue in result["issues"]))

    def test_missing_history_anchored_window_and_conflicts(self):
        histories = (
            None,
            [],
            [{"year": 2024, "value": 17}, {"year": 2025, "value": 18}],
            [
                {"year": 2022, "value": 16},
                {"year": 2023, "value": 17},
                {"year": 2024, "value": 18},
            ],
            [
                {"year": 2023, "value": 15},
                {"year": 2024, "value": None},
                {"year": 2025, "value": 18},
            ],
            stock()["roe_history"] + [{"year": 2024, "value": 99}],
            stock()["roe_history"] + [{"year": "invalid", "value": 3}],
        )
        for history in histories:
            with self.subTest(history=history):
                self.assertIsNone(
                    financial.score_financial(stock(roe_history=history))["score"]
                )

    def test_old_history_missing_values_and_equal_duplicates_do_not_block(self):
        history = stock()["roe_history"] + [
            {"year": 2020, "value": None},
            {"year": 2024, "value": 17},
        ]
        self.assertEqual(
            financial.score_financial(stock(roe_history=history))["score"], 5
        )

    def test_periods_and_adjacent_quarters(self):
        for previous, latest in (
            ("2025Q4", "2026Q1"),
            ("2026年第1季度", "2026年第2季度"),
            ("2026年一季报", "2026年半年报（单季）"),
            ("2026年半年报（单季）", "2026年三季报（单季）"),
        ):
            with self.subTest(previous=previous, latest=latest):
                self.assertEqual(
                    financial.score_financial(
                        stock(
                            previous_quarter_label=previous, latest_quarter_label=latest
                        )
                    )["score"],
                    5,
                )
        for previous, latest in (
            (None, "2026Q2"),
            ("2026Q1", "2026Q3"),
            ("2026Q2", "2026Q1"),
            ("2026Q1", "2026Q2累计"),
            ("2026Q1", "2026年半年报"),
            ("2026Q1", "2026Q1"),
            ("2026Q1", "2026Q5"),
        ):
            with self.subTest(previous=previous, latest=latest):
                self.assertIsNone(
                    financial.score_financial(
                        stock(
                            previous_quarter_label=previous, latest_quarter_label=latest
                        )
                    )["score"]
                )
        for field in ("roe_year", "annual_profit_year"):
            for value in (None, True, 2025.5, "2025Q4"):
                self.assertIsNone(
                    financial.score_financial(stock(**{field: value}))["score"]
                )
        self.assertIsNone(
            financial.score_financial(stock(annual_profit_year=2024))["score"]
        )

    def test_sector_rules_and_unknown_sector(self):
        for level1, level2, sector in (
            ("银行", "股份制银行Ⅱ", "bank"),
            ("非银金融", "保险Ⅱ", "insurance"),
            ("非银金融", "证券Ⅱ", "nonbank_financial"),
            (None, "城商行Ⅱ", "bank"),
        ):
            with self.subTest(level1=level1, level2=level2):
                result = financial.score_financial(
                    stock(sw_level1=level1, sw_level2=level2, debt_asset_ratio=95)
                )
                self.assertIsNone(result["score"])
                self.assertEqual(result["sector"], sector)
                self.assertEqual(result["status"], "not_applicable")
                self.assertFalse(
                    any(
                        c["rule"] == "debt" and c.get("cap") == 2
                        for c in result["checks"]
                    )
                )
        for data in (
            stock(sw_level1=None, sw_level2=None),
            stock(sw_level1="未知行业"),
            stock(sw_level1="机械设备", sw_level2="股份制银行Ⅱ"),
        ):
            self.assertIsNone(financial.score_financial(data)["score"])

    def test_known_weaknesses_remain_visible_when_other_data_missing(self):
        result = financial.score_financial(
            stock(debt_asset_ratio=90, latest_quarter_yoy_pct=None)
        )
        self.assertIsNone(result["score"])
        self.assertTrue(any("负债" in risk for risk in result["risks"]))

    def test_invalid_quarter_periods_do_not_establish_continuous_decline(self):
        for previous, latest in (
            ("2026Q1", "2026Q3"),
            ("2026Q1", None),
            ("2026Q1", "2026年半年报"),
            ("2026Q2", "2026Q1"),
        ):
            with self.subTest(previous=previous, latest=latest):
                result = financial.score_financial(
                    stock(
                        previous_quarter_label=previous,
                        latest_quarter_label=latest,
                        previous_quarter_yoy_pct=-1,
                        latest_quarter_yoy_pct=-2,
                    )
                )
                self.assertIsNone(result["score"])
                earnings = next(c for c in result["checks"] if c["rule"] == "earnings")
                severe = next(
                    c for c in result["checks"] if c["rule"] == "severe_weaknesses"
                )
                self.assertIsNone(earnings["result"])
                self.assertIsNone(earnings["cap"])
                self.assertFalse(severe["input"]["earnings"])
                self.assertEqual(severe["result"], 0)
                self.assertFalse(any("连续两季" in risk for risk in result["risks"]))
                self.assertTrue(any("为负" in risk for risk in result["risks"]))

    def test_missing_annual_period_does_not_produce_an_earnings_grade(self):
        result = financial.score_financial(stock(annual_profit_year=None))
        earnings = next(c for c in result["checks"] if c["rule"] == "earnings")
        self.assertIsNone(earnings["period"]["annual"])
        self.assertIsNone(earnings["result"])
        self.assertIsNone(earnings["cap"])

    def test_ascii_roman_three_suffix_is_removed_as_one_suffix(self):
        for suffix in ("II", "III", "Ⅱ", "Ⅲ"):
            with self.subTest(suffix=suffix):
                result = financial.score_financial(
                    stock(
                        sw_level1=None,
                        sw_level2="城商行" + suffix,
                    )
                )
                self.assertEqual(result["sector"], "bank")

    def test_background_fields_are_not_required(self):
        self.assertEqual(
            financial.score_financial(
                stock(
                    eps=None,
                    gross_profit_margin=None,
                    annual_net_profit_ex_non_recurring=None,
                )
            )["score"],
            5,
        )

    def test_wrong_top_level_type_is_an_input_error(self):
        for value in (None, [], "stock"):
            with self.assertRaises(TypeError):
                financial.score_financial(value)


if __name__ == "__main__":
    unittest.main()
