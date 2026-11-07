#!/usr/bin/env python3
"""Publish prepared WaytoAGI entries through the shared RSS CLI, recording each token."""
import argparse
from contextlib import closing
import sqlite3
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
from runpy import run_path
import tempfile

relay_publish = run_path(str(Path(__file__).with_name('rss_relay_client.py')))['publish']


def resolve_ca_file():
    """Return a CA bundle for the relay's self-signed certificate, or None.

    The relay host serves a self-signed certificate, so the public CLI's TLS
    verification against the system trust store fails with
    "preflight_failed: Could not read remote posts; nothing published".
    Read the environment on every call so a late export still applies.
    """
    candidates = (
        os.environ.get('RSS_RELAY_CA_FILE'),
        os.path.expanduser('~/.local/state/rss-relay-publish/relay_ca.pem'),
        os.path.expanduser('~/.config/rss-relay-publish/ca.pem'),
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def read_receipts(path):
    data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'articles': {}}
    if not isinstance(data, dict) or not isinstance(data.get('articles'), dict):
        raise ValueError('Invalid WaytoAGI receipts; refusing to discard previous tokens')
    return data


def record(path, token):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Serialize the complete read/merge/replace, including writers from other processes.
    with closing(sqlite3.connect(str(path) + '.lock.sqlite3', timeout=20)) as lock:
        lock.execute('BEGIN IMMEDIATE')
        name = None
        try:
            data = read_receipts(path)
            data['articles'][token] = datetime.now(timezone(timedelta(hours=8))).isoformat()
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as output:
                name = output.name
                json.dump(data, output, ensure_ascii=False, indent=2)
            os.replace(name, path)
            lock.commit()
        finally:
            if name and Path(name).exists():
                Path(name).unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--articles-json', required=True, help='JSON array: token/title/content/url')
    parser.add_argument('--receipts', type=Path, default=Path(__file__).resolve().parents[1] / 'data/pushed_articles.json')
    parser.add_argument('--endpoint')
    args = parser.parse_args(argv)
    results = []
    try:
        articles = json.loads(Path(args.articles_json).read_text(encoding='utf-8-sig'))
        if not isinstance(articles, list) or any(not isinstance(a, dict) or any(not isinstance(a.get(k), str) or not a[k].strip() for k in ('token', 'title', 'content', 'url')) for a in articles):
            raise ValueError('Expected an array of nonempty token/title/content/url entries')
        for article in articles:
            token = article['token']
            if token in read_receipts(args.receipts)['articles']:
                results.append({'token': token, 'status': 'skipped'})
                continue
            payload = {k: article[k] for k in ('title', 'content', 'url')}
            payload.update(channel='waytoagi', source='waytoagi-daily')
            response = relay_publish(payload, 'article:' + token, endpoint=args.endpoint,
                                     ca_file=resolve_ca_file())
            record(args.receipts, token)
            results.append(dict(response, token=token))
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({'ok': False, 'results': results, 'error': str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({'ok': True, 'results': results}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
