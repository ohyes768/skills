import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('bond_collector', Path(__file__).parents[1]/'scripts/fetch_snapshot.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def row(stamp, value, unit='%'):
    return {'normalized_date': stamp, 'value': value, 'unit': unit}


def evidence(longs, spreads):
    return {'daily': {'liquidity.cn_10y': {'observations': longs},
                      'liquidity.cn_10y_2y': {'observations': spreads}}}


class BondEvidenceTest(unittest.TestCase):
    def test_same_date_derivation_and_bp_conversion(self):
        result = module.term_structure(evidence(
            [row('2026-09-18', 1.7), row('2026-09-11', 1.8)],
            [row('2026-09-18', .4), row('2026-09-11', .3)]))
        self.assertEqual(result['observations'][0]['cn_2y_derived_pct'], 1.3)
        self.assertEqual(result['latest_change']['cn_10y_change_bp'], -10)
        self.assertEqual(result['latest_change']['cn_2y_derived_change_bp'], -20)
        self.assertEqual(result['latest_change']['slope_change_bp'], 10)
        self.assertEqual(result['latest_change']['observed_slope'], 'steeper')

    def test_mismatched_dates_do_not_derive(self):
        result = module.term_structure(evidence([row('2026-09-18', 1.7)], [row('2026-09-17', .4)]))
        self.assertEqual(result['observations'], [])
        self.assertIsNone(result['latest_change'])

    def test_unknown_units_do_not_derive(self):
        result = module.term_structure(evidence([row('2026-09-18', 1.7)], [row('2026-09-18', 40, 'bp')]))
        self.assertFalse(result['observations'])

    def test_one_pair_is_not_a_trend(self):
        result = module.term_structure(evidence([row('2026-09-18', 1.7)], [row('2026-09-18', .4)]))
        self.assertEqual(len(result['observations']), 1)
        self.assertIsNone(result['latest_change'])


if __name__ == '__main__':
    unittest.main()
