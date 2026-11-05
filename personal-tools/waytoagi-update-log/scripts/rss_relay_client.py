"""Generated compatibility shim: locates the public CLI; never sends HTTP itself.

Canonical source: knowledge/rss-relay-publish/scripts/rss_relay_client.py.
Copies in existing consumers allow independently installed skill packages to run.
New consumers should call rss_publish.py directly instead of copying this shim.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def locate_script():
    configured = os.environ.get('RSS_RELAY_SKILL_DIR')
    if configured:
        path = Path(configured).expanduser() / 'scripts/rss_publish.py'
        if not path.is_file():
            raise ValueError('RSS_RELAY_SKILL_DIR must contain scripts/rss_publish.py')
        return path.resolve()
    for parent in Path(__file__).resolve().parents:
        for relative in ('scripts/rss_publish.py', 'rss-relay-publish/scripts/rss_publish.py',
                         'knowledge/rss-relay-publish/scripts/rss_publish.py'):
            path = parent / relative
            if path.is_file() and path.parent.parent.name == 'rss-relay-publish':
                return path
    for root in (Path.home() / '.hermes/skills', Path.home() / '.codex/skills', Path.home() / '.agents/skills'):
        path = root / 'rss-relay-publish/scripts/rss_publish.py'
        if path.is_file():
            return path
    raise ValueError('Install rss-relay-publish and set RSS_RELAY_SKILL_DIR to its package directory')


def publish(payload, key, *, endpoint=None, verify=True, ca_file=None, timeout=20):
    args = [sys.executable, str(locate_script()), 'publish', '--file', '-', '--title', payload['title'],
            '--channel', payload['channel'], '--source', payload['source'], '--url', payload.get('url') or '',
            '--dedupe-key', key, '--timeout', str(timeout)]
    if endpoint:
        if not endpoint.endswith('/post'):
            raise ValueError('RSS endpoint must end with /post')
        args.extend(['--base-url', endpoint[:-5]])
    if not verify:
        args.append('--insecure')
    if ca_file:
        args.extend(['--ca-file', str(ca_file)])
    # CLI performs bounded HTTP calls. Do not kill it at a parent timeout after POST.
    proc = subprocess.run(args, input=payload['content'].encode('utf-8'), capture_output=True)
    try:
        data = json.loads(proc.stdout.decode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ValueError('Public RSS CLI returned no valid result; inspect receipts before retrying') from exc
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('Unsupported public RSS CLI result')
    if proc.returncode != 0 or data.get('status') not in ('published', 'duplicate') or not data.get('id'):
        raise ValueError('RSS publication not confirmed: ' + json.dumps(data, ensure_ascii=False))
    return data
