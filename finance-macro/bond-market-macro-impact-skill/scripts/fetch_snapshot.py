"""Read-only macro evidence collector. Python standard library only."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import ssl
import sys
from urllib.parse import urlencode
from urllib.request import urlopen

URL = 'https://web.duomi77.cn:9443/api/macro/analysis/snapshot'
MONTHLY = {
    'monetary_policy': 'lpr_1y lpr_5y mlf_net_yi'.split(),
    'money_supply': 'm2_yoy m1_yoy social_yoy m2_m1_spread spread_change_pp'.split(),
    'entity_economy': 'pmi_manufacturing industrial_yoy fai_yoy retail_yoy'.split(),
    'inflation': 'cpi_yoy ppi_yoy'.split(),
}
DAILY = {
    'liquidity': 'dr001 dr007 cn_10y cn_10y_2y'.split(),
    'external_pressure': 'dollar_index usd_cny ted_spread hibor_overnight north_today_yi north_7d_avg_yi north_7d_change_pct cn_us_10y_spread vix'.split(),
    'market_sentiment': 'volume turnover margin south_net_yi'.split(),
}


def months_before(anchor, count=12):
    index = anchor.year * 12 + anchor.month - 1
    return [f'{(index-i)//12:04d}-{(index-i)%12+1:02d}' for i in range(count)]


def parse_day(value):
    try:
        if not isinstance(value, str):
            return None
        return date.fromisoformat(value[:10] + ('-01' if len(value) == 7 else ''))
    except ValueError:
        return None


def fetch(params):
    ctx = ssl._create_unverified_context()
    with urlopen(URL + '?' + urlencode(params), timeout=30, context=ctx) as response:
        payload = json.load(response)
    return validate(payload)


def validate(payload):
    if not isinstance(payload, dict) or payload.get('success') is not True:
        raise ValueError('API success is not true')
    data = payload.get('data', {})
    if data.get('schema_version') != '1.0':
        raise ValueError('Unsupported schema_version')
    if not isinstance(data.get('monthly', {}).get('periods'), list):
        raise ValueError('Missing monthly periods')
    if not isinstance(data.get('daily', {}).get('cards'), list):
        raise ValueError('Missing daily cards')
    if parse_day(data['daily'].get('as_of')) is None:
        raise ValueError('Invalid daily as_of')
    return payload


def prepare(bundle):
    current = validate(bundle['current'])['data']
    anchor = date.fromisoformat(bundle['analysis_date'])
    warnings = list(bundle.get('warnings', []))
    monthly = {f'{card}.{key}': [] for card, keys in MONTHLY.items() for key in keys}
    daily = {f'{card}.{key}': [] for card, keys in DAILY.items() for key in keys}

    def add(target, card, indicator, source, cutoff):
        name = f"{card.get('id')}.{indicator.get('key')}"
        if name not in target:
            return
        stamp = parse_day(indicator.get('data_date'))
        value = indicator.get('value')
        status = indicator.get('status')
        if (stamp is None or stamp > cutoff or status != 'ok'
                or isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)):
            warnings.append(f'{name}: unusable observation at {source}')
            return
        analyzed = parse_day(indicator.get('analyzed_at'))
        if analyzed and analyzed > anchor:
            warnings.append(f'{name}: analyzed after requested date; excluded')
            return
        if card.get('status') != 'ok':
            warnings.append(f'{name}: card status {card.get("status")}; inspect raw snapshot')
        target[name].append({**indicator, 'source_period': source,
                             'normalized_date': stamp.isoformat(),
                             'age_calendar_days': (anchor-stamp).days})

    for period in current['monthly']['periods']:
        period_day = parse_day(period.get('month'))
        if period_day is None or period_day > anchor or period.get('status') == 'unavailable':
            continue
        for card in period.get('cards', []):
            for indicator in card.get('indicators', []):
                add(monthly, card, indicator, period['month'], anchor)

    for item in [{'requested_date': anchor.isoformat(), 'response': bundle['current']},
                 *bundle.get('history', [])]:
        data = validate(item['response'])['data']
        requested = date.fromisoformat(item['requested_date'])
        returned = date.fromisoformat(data['daily']['as_of'])
        if returned != requested:
            warnings.append(f'Daily date mismatch {requested} vs {returned}; excluded')
            continue
        for card in data['daily']['cards']:
            for indicator in card.get('indicators', []):
                add(daily, card, indicator, requested.isoformat(), min(requested, anchor))

    def summarize(series, is_monthly):
        results = {}
        for name, rows in series.items():
            unique = {}
            for row in sorted(rows, key=lambda r: r['source_period'], reverse=True):
                key = row['normalized_date'][:7] if is_monthly else row['normalized_date']
                if key in unique and unique[key]['value'] != row['value']:
                    warnings.append(f'{name}: conflicting values for {key}; newest source retained')
                unique.setdefault(key, row)
            observations = [unique[k] for k in sorted(unique, reverse=True)]
            if is_monthly:
                observations = observations[:3]
            comparison = None
            if len(observations) >= 2:
                latest, previous = observations[:2]
                if latest.get('unit') == previous.get('unit'):
                    comparison = {
                        'from': previous['data_date'], 'to': latest['data_date'],
                        'difference': latest['value']-previous['value'],
                        'unit': '指数点' if name.endswith('pmi_manufacturing') else
                                ('百分点' if latest.get('unit') in ('%', 'pp') else latest.get('unit')),
                        'calendar_gap_days': (parse_day(latest['data_date'])-parse_day(previous['data_date'])).days,
                    }
                    if is_monthly:
                        newer, older = parse_day(latest['data_date']), parse_day(previous['data_date'])
                        gap = (newer.year-older.year)*12 + newer.month-older.month
                        comparison['month_gap'] = gap
                        comparison['adjacent_months'] = gap == 1
                        if gap != 1:
                            warnings.append(f'{name}: non-adjacent months; not a month-on-month comparison')
                else:
                    warnings.append(f'{name}: unit mismatch; comparison omitted')
            if not observations:
                warnings.append(f'{name}: no usable evidence')
            elif not comparison:
                warnings.append(f'{name}: insufficient comparable observations for change')
            results[name] = {'observations': observations, 'latest_change': comparison}
        return results

    month_result = summarize(monthly, True)
    day_result = summarize(daily, False)
    return {
        'analysis_date': anchor.isoformat(), 'outlook_end': (anchor+timedelta(days=28)).isoformat(),
        'collected_at': bundle.get('collected_at'), 'monthly': month_result, 'daily': day_result,
        'api_quality': current.get('quality'),
        'warnings': sorted(set(warnings)),
        'limitations': ['Historical snapshots may be revised; not a point-in-time backtest.',
                       'Calendar age is descriptive, not an automatic stale classification.',
                       'Daily samples are weekly observations, not complete daily trends.'],
    }


def collect(requested_date=None):
    first = fetch({'date': requested_date} if requested_date else {})
    anchor = date.fromisoformat(requested_date or first['data']['daily']['as_of'])
    current = fetch({'date': anchor.isoformat(), 'months': ','.join(months_before(anchor))})
    bundle = {'analysis_date': anchor.isoformat(),
              'collected_at': datetime.now(timezone.utc).isoformat(),
              'current': current, 'history': [], 'warnings': []}
    for days in (7, 14, 21, 28):
        previous = (anchor-timedelta(days=days)).isoformat()
        try:
            response = fetch({'date': previous, 'months': anchor.strftime('%Y-%m')})
            bundle['history'].append({'requested_date': previous, 'response': response})
        except (OSError, ValueError) as exc:
            bundle['warnings'].append(f'History {previous} unavailable: {exc}')
    return bundle


def term_structure(evidence):
    """Pair dates exactly; never substitute a funding rate for a bond yield."""
    daily = evidence['daily']
    long_rows = daily['liquidity.cn_10y']['observations']
    spread_rows = daily['liquidity.cn_10y_2y']['observations']
    spreads = {r['normalized_date']: r for r in spread_rows}
    pairs = []
    skipped = []
    for long in long_rows:
        stamp = long['normalized_date']
        spread = spreads.get(stamp)
        if not spread or long.get('unit') != '%' or spread.get('unit') not in ('%', 'pp'):
            skipped.append(stamp)
            continue
        pairs.append({'date': stamp, 'cn_10y_pct': long['value'],
                      'cn_2y_derived_pct': round(long['value']-spread['value'], 8),
                      'spread_pp': spread['value']})
    pairs.sort(key=lambda row: row['date'], reverse=True)
    change = None
    if len(pairs) >= 2:
        latest, previous = pairs[:2]
        long_bp = round((latest['cn_10y_pct']-previous['cn_10y_pct'])*100, 6)
        short_bp = round((latest['cn_2y_derived_pct']-previous['cn_2y_derived_pct'])*100, 6)
        slope_bp = round((latest['spread_pp']-previous['spread_pp'])*100, 6)
        change = {'from': previous['date'], 'to': latest['date'],
                  'cn_10y_change_bp': long_bp, 'cn_2y_derived_change_bp': short_bp,
                  'slope_change_bp': slope_bp,
                  'observed_slope': 'steeper' if slope_bp > 0 else 'flatter' if slope_bp < 0 else 'unchanged'}
    return {'observations': pairs, 'latest_change': change,
            'unpaired_or_invalid_unit_dates': skipped,
            'note': '2Y is derived from same-date 10Y minus 10Y-2Y; historical observation, not a forecast.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', type=date.fromisoformat)
    parser.add_argument('--input', type=Path, help='Offline raw_snapshots.json bundle')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    try:
        if args.input and args.date:
            raise ValueError('--input preserves its analysis_date; do not combine with --date')
        bundle = json.loads(args.input.read_text(encoding='utf-8')) if args.input else collect(
            args.date.isoformat() if args.date else None)
        evidence = prepare(bundle)
        evidence['term_structure'] = term_structure(evidence)
        folder = args.output_dir or (Path(__file__).resolve().parents[2] / 'output' /
            'bond-market-macro-impact-skill' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        folder.mkdir(parents=True, exist_ok=False)
        for name, content in [('raw_snapshots.json', bundle), ('evidence.json', evidence)]:
            (folder/name).write_text(json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        print(str(folder.resolve()))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'Collection failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
