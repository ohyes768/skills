#!/usr/bin/env python3
"""Send markdown to a DingTalk group robot with conservative, durable receipts.

Canonical transport for DingTalk pushes; consumers keep business content,
titles and authorization here and must not embed another HTTP sender.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from http.client import HTTPException
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import sqlite3
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT = 20
EXIT_CODES = {'sent': 0, 'duplicate': 0, 'preview': 0, 'failed': 2, 'unknown': 3, 'conflict': 4}


def result(status, *, errcode=None, errmsg=None, dedupe_key=None, verification='none', code=None, message=None):
    return {'schema_version': 1, 'status': status, 'errcode': errcode, 'errmsg': errmsg,
            'dedupe_key': dedupe_key, 'verification': verification,
            'error': {'code': code, 'message': redact(message) if message else None} if code else None}


def redact(value):
    """Webhook tokens must never leak into output, errors or logs."""
    return re.sub(r'(access_token=)[^&\s"\']+', r'\1***', str(value))


def normalize_webhook(value):
    parsed = urlsplit(value.strip())
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('webhook must be an HTTP(S) robot URL without credentials')
    return value.strip()


def default_state_dir():
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local') / 'dingtalk-push'
    return Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'dingtalk-push'


def load_env_file(path):
    values = {}
    for raw in Path(path).read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, _, value = line.partition('=')
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def open_receipts(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state_dir / 'receipts.sqlite3', timeout=10)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS receipts ('
                     'identity TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL, '
                     'updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


def is_timeout(exc):
    reason = getattr(exc, 'reason', exc)
    if isinstance(reason, TimeoutError):
        return True
    return 'timed out' in str(reason).lower() or 'timeout' in str(reason).lower()


def post(webhook, payload, timeout):
    """One bounded POST; returns parsed robot JSON or raises for classification."""
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = Request(webhook, data=data, headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
    return json.loads(body.decode('utf-8'))


def send_message(title, text, webhook, state_dir, *, keyword=None, key=None, timeout=DEFAULT_TIMEOUT, dry_run=False):
    if not title.strip() or not text.strip():
        raise ValueError('title and text must not be blank')
    if keyword and keyword not in title and keyword not in text:
        # DingTalk keyword security rejects such sends with errcode 310000;
        # retrying unchanged content cannot succeed, so refuse before POST.
        return result('failed', code='keyword_missing',
                      message=f'keyword {keyword!r} is absent from both title and text; adjust content, do not retry unchanged')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be a finite positive number')
    payload = {'msgtype': 'markdown', 'markdown': {'title': title, 'text': text}}
    dedupe_key = key if key is not None else 'auto:' + hashlib.sha256((title + '\n' + text).encode('utf-8')).hexdigest()[:16]
    if dry_run:
        return dict(result('preview', dedupe_key=dedupe_key), payload=payload)

    webhook = normalize_webhook(webhook)
    # Only a digest of the webhook is stored, never the URL with its token.
    identity = hashlib.sha256(webhook.encode('utf-8')).hexdigest()[:16] + '|' + dedupe_key
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    with closing(open_receipts(Path(state_dir))) as conn:
        with conn:
            cursor = conn.execute('INSERT OR IGNORE INTO receipts(identity,digest,state) VALUES(?,?,?)',
                                  (identity, digest, 'pending'))
            claimed = cursor.rowcount == 1
            row = conn.execute('SELECT digest,state FROM receipts WHERE identity=?', (identity,)).fetchone()
        if row[0] != digest:
            return result('conflict', dedupe_key=dedupe_key, code='key_conflict',
                          message='same identity has different content; use an explicit new version key')
        if row[1] == 'confirmed':
            return result('duplicate', dedupe_key=dedupe_key, verification='historical')
        if not claimed:
            # Another invocation claimed this identity and never confirmed.
            # DingTalk offers no readback, so hold pending and never blind-retry.
            return result('unknown', dedupe_key=dedupe_key, code='pending',
                          message='previous request remains unconfirmed; no automatic repost')

        try:
            body = post(webhook, payload, timeout)
        except HTTPError as exc:
            detail = b''
            try:
                detail = exc.read()
            except OSError:
                pass
            try:
                robot = json.loads(detail.decode('utf-8'))
            except (ValueError, UnicodeDecodeError, OSError):
                robot = None
            if robot is not None and isinstance(robot.get('errcode'), int):
                with conn:
                    conn.execute('DELETE FROM receipts WHERE identity=?', (identity,))
                return result('failed', errcode=robot['errcode'], errmsg=robot.get('errmsg'),
                              dedupe_key=dedupe_key, code='robot_rejected',
                              message='robot rejected the message; fix content or configuration before retrying')
            if exc.code < 500:
                with conn:
                    conn.execute('DELETE FROM receipts WHERE identity=?', (identity,))
                return result('failed', dedupe_key=dedupe_key, code='http_rejected',
                              message=f'robot endpoint rejected the request (HTTP {exc.code})')
            return result('unknown', dedupe_key=dedupe_key, code='server_error',
                          message='server error after request; delivery unconfirmed, no automatic repost')
        except (URLError, TimeoutError, OSError, HTTPException) as exc:
            if not is_timeout(exc):
                # Connection never established: nothing was sent; release the claim.
                with conn:
                    conn.execute('DELETE FROM receipts WHERE identity=?', (identity,))
                return result('failed', dedupe_key=dedupe_key, code='transport_failed',
                              message='request could not be sent (connection error); safe to retry after fixing')
            return result('unknown', dedupe_key=dedupe_key, code='unconfirmed',
                          message='request may have been delivered; timeout, no automatic repost')
        except (ValueError, UnicodeDecodeError):
            return result('unknown', dedupe_key=dedupe_key, code='unconfirmed',
                          message='response could not be parsed; delivery unconfirmed, no automatic repost')

        errcode = body.get('errcode') if isinstance(body, dict) else None
        if errcode == 0:
            with conn:
                conn.execute('UPDATE receipts SET state=?, updated_at=CURRENT_TIMESTAMP WHERE identity=?',
                             ('confirmed', identity))
            return result('sent', errcode=0, errmsg=body.get('errmsg'), dedupe_key=dedupe_key)
        if isinstance(errcode, int):
            with conn:
                conn.execute('DELETE FROM receipts WHERE identity=?', (identity,))
            return result('failed', errcode=errcode, errmsg=body.get('errmsg'), dedupe_key=dedupe_key,
                          code='robot_rejected',
                          message='robot rejected the message; fix content or configuration before retrying')
        return result('unknown', dedupe_key=dedupe_key, code='malformed_response',
                      message='robot response had no usable errcode; delivery unconfirmed')


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    command = commands.add_parser('send')
    command.add_argument('--title', required=True)
    group = command.add_mutually_exclusive_group(required=True)
    group.add_argument('--text')
    group.add_argument('--file')
    command.add_argument('--keyword', default=os.environ.get('DINGTALK_KEYWORD'))
    command.add_argument('--dedupe-key')
    command.add_argument('--webhook', default=os.environ.get('DINGTALK_WEBHOOK'))
    command.add_argument('--env-file')
    command.add_argument('--state-dir', default=os.environ.get('DINGTALK_PUSH_STATE_DIR'))
    command.add_argument('--timeout', type=float, default=os.environ.get('DINGTALK_PUSH_TIMEOUT', str(DEFAULT_TIMEOUT)))
    command.add_argument('--dry-run', action='store_true')
    try:
        args = parser.parse_args(argv)
        if args.text is not None:
            text = args.text
        elif args.file == '-':
            text = sys.stdin.read()
        else:
            text = Path(args.file).read_text(encoding='utf-8-sig')
        webhook = args.webhook
        if args.env_file:
            webhook = webhook or load_env_file(args.env_file).get('DINGTALK_WEBHOOK')
        if not webhook:
            raise ValueError('no webhook: pass --webhook, set DINGTALK_WEBHOOK or provide --env-file')
        response = send_message(args.title, text, webhook, args.state_dir or default_state_dir(),
                                keyword=args.keyword, key=args.dedupe_key,
                                timeout=args.timeout, dry_run=args.dry_run)
    except (OSError, ValueError, HTTPException, sqlite3.Error) as exc:
        response = result('failed', code='invalid_input_or_state',
                          message=type(exc).__name__ + ': check input, configuration and state directory')
    print(json.dumps(response, ensure_ascii=False))
    return EXIT_CODES[response['status']]


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', newline='')
    raise SystemExit(main())
