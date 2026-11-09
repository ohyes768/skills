"""Fictional arithmetic examples; no real security recommendation."""
import importlib.util
import sys
import unittest
from decimal import Decimal, localcontext
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
if importlib.util.find_spec("valuation_math"):
    from valuation_math import evaluate, level_metrics, round_price
else:
    def evaluate(*args, **kwargs):
        raise AssertionError("valuation_math.evaluate is not implemented")

    def level_metrics(*args, **kwargs):
        raise AssertionError("valuation_math.level_metrics is not implemented")

    def round_price(*args, **kwargs):
        raise AssertionError("valuation_math.round_price is not implemented")


def cash(**changes):
    result = {"method": "equity_cashflow_pv", "cashflows": ["1", "1"],
              "discount_rate": "0.1", "cashflow_basis": "dividend",
              "finite_life": False, "terminal": {"kind": "value", "value": "20"}}
    result.update(changes)
    return result


class ArithmeticTests(unittest.TestCase):
    def test_pe(self):
        self.assertEqual(evaluate({"method": "pe_multiple", "eps": "2", "multiple": "10"}), Decimal(20))

    def test_pb(self):
        self.assertEqual(evaluate({"method": "pb_multiple", "bvps": "10", "multiple": "0.8"}), Decimal(8))

    def test_margin(self):
        self.assertEqual(evaluate({"method": "pe_multiple", "eps": "2", "multiple": "10", "margin": "0.2"}), Decimal(16))

    def test_future_price_discounted_and_dividends_once(self):
        self.assertAlmostEqual(evaluate(cash()), Decimal("18.26446280991735537190082645"), places=25)
        self.assertNotEqual(evaluate(cash()), Decimal(22))

    def test_exit_pe_same_terminal_value(self):
        self.assertAlmostEqual(evaluate(cash(terminal={"kind": "exit_pe", "eps": "2", "multiple": "10"})), Decimal("18.26446280991735537190082645"), places=25)

    def test_perpetuity_uses_next_year_then_discounts_n_years(self):
        node = cash(cashflows=["1"], terminal={"kind": "perpetuity", "next_cashflow": "2", "growth": "0"})
        self.assertAlmostEqual(evaluate(node), Decimal("19.09090909090909090909090909"), places=25)

    def test_negative_cashflow_is_not_clipped(self):
        self.assertAlmostEqual(evaluate(cash(cashflows=["-1", "2"], finite_life=True)), Decimal("17.27272727272727272727272727"), places=25)

    def test_fcfe_not_duplicated_with_dividends(self):
        self.assertAlmostEqual(evaluate(cash(cashflow_basis="fcfe")), Decimal("18.26446280991735537190082645"), places=25)
        with self.assertRaises(ValueError):
            evaluate(cash(cashflow_basis="fcfe", dividends=["1", "1"]))

    def test_finite_life_zero_terminal(self):
        self.assertEqual(evaluate(cash(cashflows=["11"], finite_life=True, terminal={"kind": "value", "value": "0"})), Decimal(10))

    def test_round_half_up_only_at_price_boundary(self):
        exact = evaluate({"method": "pe_multiple", "eps": "1.005", "multiple": "1"})
        self.assertEqual(exact, Decimal("1.005"))
        self.assertEqual(round_price(exact), Decimal("1.01"))

    def test_calculation_independent_of_global_precision(self):
        with localcontext() as ctx:
            ctx.prec = 6
            self.assertAlmostEqual(evaluate(cash()), Decimal("18.26446280991735537190082645"), places=25)

    def test_metrics_ttm_and_percentage(self):
        self.assertEqual(level_metrics(Decimal(16), "1.6", "4", "0.8"),
                         {"pe": Decimal("10.0000"), "pb": Decimal("4.0000"), "dividend_yield_pct": Decimal("5.0000")})

    def test_metrics_missing_nonpositive_and_zero_dps(self):
        self.assertEqual(level_metrics("10", "-2", "0", "0"),
                         {"pe": None, "pb": None, "dividend_yield_pct": Decimal("0.0000")})
        self.assertEqual(level_metrics("10", None, None, None),
                         {"pe": None, "pb": None, "dividend_yield_pct": None})

    def test_metrics_round_price_before_division(self):
        self.assertEqual(level_metrics("1.005", "1", "1", "1")["pe"], Decimal("1.0100"))

    def test_metrics_reject_negative_dps_and_invalid_inputs(self):
        for args in [("10", "1", "1", "-1"), ("0", None, None, None), ("10", True, None, None), ("10", None, "NaN", None)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                level_metrics(*args)

    def test_reject_invalid_numeric_values(self):
        for value in [True, False, None, "", " ", "NaN", "Infinity", "-Infinity", float("nan"), float("inf"), "1+2", "1_000", "1e999999", "1e-999999", "9" * 257, [], {}]:
            with self.subTest(value=str(value)[:40]), self.assertRaises(ValueError):
                evaluate({"method": "pe_multiple", "eps": value, "multiple": "10"})

    def test_reject_nonpositive_inputs_and_bad_margin(self):
        for field, value in [("eps", "0"), ("eps", "-1"), ("multiple", "0"), ("margin", "-0.1"), ("margin", "1")]:
            node = {"method": "pe_multiple", "eps": "2", "multiple": "10", field: value}
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                evaluate(node)
        with self.assertRaises(ValueError):
            evaluate({"method": "pb_multiple", "bvps": "-1", "multiple": "1"})

    def test_reject_missing_unknown_and_expression_methods(self):
        for node in [{}, {"method": "eval", "expression": "2*10"}, {"method": "pe_multiple", "eps": "2"}, {"method": "pe_multiple", "eps": "2", "multiple": "10", "x": 1}, None, [], {"method": []}]:
            with self.subTest(node=node), self.assertRaises(ValueError):
                evaluate(node)

    def test_reject_bad_cashflow_contract(self):
        for change in [{"cashflows": []}, {"cashflows": ["1"] * 101}, {"cashflows": "1"}, {"cashflows": [True]}, {"discount_rate": "0"}, {"finite_life": "false"}, {"cashflow_basis": "fcff"}, {"terminal": {"kind": "value", "value": "-1"}}, {"cashflows": ["-100"], "terminal": {"kind": "value", "value": "0"}}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                evaluate(cash(**change))

    def test_reject_bad_or_mixed_terminal(self):
        for terminal in [{"kind": "unknown"}, {"kind": "value", "value": "1", "eps": "1"}, {"kind": "exit_pe", "eps": "0", "multiple": "1"}, {"kind": "perpetuity", "next_cashflow": "1", "growth": "0.1"}, {"kind": "perpetuity", "next_cashflow": "1", "growth": "-1"}, {"kind": "perpetuity", "next_cashflow": "0", "growth": "0"}]:
            with self.subTest(terminal=terminal), self.assertRaises(ValueError):
                evaluate(cash(terminal=terminal))

    def test_finite_life_rejects_perpetuity(self):
        with self.assertRaises(ValueError):
            evaluate(cash(finite_life=True, terminal={"kind": "perpetuity", "next_cashflow": "1", "growth": "0"}))


if __name__ == "__main__":
    unittest.main()
