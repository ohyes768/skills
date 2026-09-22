import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('collector', Path(__file__).parents[1]/'scripts/fetch_snapshot.py')
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


def indicator(value, stamp, key='m2_yoy', **extra):
    return {'key': key, 'value': value, 'data_date': stamp, 'status': 'ok', 'unit': '%', **extra}


def response(periods=None, rows=None, asof='2026-09-21'):
    return {'success': True, 'data': {'schema_version': '1.0',
        'monthly': {'periods': periods or []},
        'daily': {'as_of': asof, 'cards': [{'id': 'liquidity', 'status': 'ok', 'indicators': rows or []}]}}}


def period(month, row):
    return {'month': month, 'status': 'ok', 'cards': [
        {'id': 'money_supply', 'status': 'ok', 'indicators': [row]}]}


class EvidenceTests(unittest.TestCase):
    def test_latest_published_month_and_percentage_points(self):
        current = response([period('2026-09', indicator(None, '2026-09')),
                            period('2026-08', indicator(8.5, '2026-08')),
                            period('2026-07', indicator(8.0, '2026-07')),
                            period('2026-06', indicator(7.5, '2026-06'))])
        result = collector.prepare({'analysis_date': '2026-09-21', 'current': current})
        series = result['monthly']['money_supply.m2_yoy']
        self.assertEqual(series['observations'][0]['data_date'], '2026-08')
        self.assertEqual(series['latest_change']['difference'], .5)
        self.assertEqual(series['latest_change']['unit'], '百分点')
        self.assertEqual(len(series['observations']), 3)

    def test_repeated_fallback_is_one_observation(self):
        row = indicator(1.5, '2026-09-01', 'dr007', is_asof_fallback=True)
        result = collector.prepare({'analysis_date': '2026-09-21', 'current': response(rows=[row]),
            'history': [{'requested_date': '2026-09-14', 'response': response(rows=[row], asof='2026-09-14')}]})
        series = result['daily']['liquidity.dr007']
        self.assertEqual(len(series['observations']), 1)
        self.assertIsNone(series['latest_change'])

    def test_future_and_post_analysis_rows_excluded(self):
        current = response([period('2026-08', indicator(8, '2026-08', analyzed_at='2026-09-22'))],
                           [indicator(2, '2026-09-22', 'dr007')])
        result = collector.prepare({'analysis_date': '2026-09-21', 'current': current})
        self.assertFalse(result['monthly']['money_supply.m2_yoy']['observations'])
        self.assertFalse(result['daily']['liquidity.dr007']['observations'])

    def test_mismatched_history_date_excluded(self):
        result = collector.prepare({'analysis_date': '2026-09-21', 'current': response(),
            'history': [{'requested_date': '2026-09-14', 'response': response(rows=[indicator(2, '2026-09-14', 'dr007')])}]})
        self.assertFalse(result['daily']['liquidity.dr007']['observations'])
        self.assertTrue(any('mismatch' in w for w in result['warnings']))

    def test_missing_month_does_not_fabricate_adjacent_change(self):
        current = response([period('2026-08', indicator(8, '2026-08')),
                            period('2026-06', indicator(7, '2026-06'))])
        result = collector.prepare({'analysis_date': '2026-09-21', 'current': current})
        self.assertEqual(result['monthly']['money_supply.m2_yoy']['latest_change']['calendar_gap_days'], 61)
        self.assertFalse(result['monthly']['money_supply.m2_yoy']['latest_change']['adjacent_months'])

    def test_history_network_failure_preserves_current_evidence(self):
        current = response([period('2026-08', indicator(8, '2026-08'))])
        with patch.object(collector, 'fetch', side_effect=[current, current] + [OSError('offline')]*4):
            bundle = collector.collect('2026-09-21')
        self.assertEqual(len(bundle['warnings']), 4)
        self.assertEqual(bundle['history'], [])
        self.assertEqual(collector.prepare(bundle)['monthly']['money_supply.m2_yoy']['observations'][0]['value'], 8)

    def test_invalid_values_and_status_are_not_evidence(self):
        for value, state in [(True, 'ok'), (float('nan'), 'ok'), ('8', 'ok'), (8, 'stale')]:
            current = response([period('2026-08', indicator(value, '2026-08', status=state))])
            result = collector.prepare({'analysis_date': '2026-09-21', 'current': current})
            self.assertFalse(result['monthly']['money_supply.m2_yoy']['observations'])

    def test_version_rejected_and_year_boundary(self):
        payload = response()
        payload['data']['schema_version'] = '2.0'
        with self.assertRaises(ValueError):
            collector.validate(payload)
        self.assertEqual(collector.months_before(collector.date(2026, 1, 1), 3), ['2026-01', '2025-12', '2025-11'])


if __name__ == '__main__':
    unittest.main()
