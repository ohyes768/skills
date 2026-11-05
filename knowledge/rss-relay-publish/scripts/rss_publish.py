#!/usr/bin/env python3
"""Publish unchanged Markdown to RSS Relay with durable, conservative receipts."""
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
import sqlite3
import ssl
import sys
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler

DEFAULT_BASE = 'https://web.duomi77.cn:9443/rss/api/rss-relay'
FIELDS = ('title', 'content', 'channel', 'source', 'url')
EXIT_CODES = {'published': 0, 'duplicate': 0, 'preview': 0, 'failed': 2, 'unknown': 3, 'conflict': 4}
REJECTED_CODES = {400, 401, 403, 404, 405, 409, 413, 415, 422}


def result(status, *, post_id=None, detail_url=None, verification='none', code=None, message=None):
    return {'schema_version': 1, 'status': status, 'id': post_id, 'detail_url': detail_url,
            'verified': verification == 'current', 'verification': verification,
            'error': {'code': code, 'message': message} if code else None}


def normalize_base(value):
    parsed = urlsplit(value.strip().rstrip('/'))
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('base-url must be an HTTP(S) API base without credentials, query or fragment')
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip('/'), '', ''))


def default_state_dir():
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local') / 'rss-relay-publish'
    return Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'rss-relay-publish'


def same_payload(post, payload):
    # The relay's text-file reader normalizes CRLF/CR. Preserve transmitted text,
    # but allow only that storage normalization when verifying it.
    def normalized(value):
        return value.replace('\r\n', '\n').replace('\r', '\n') if isinstance(value, str) else value
    return all(normalized(post.get(k)) == normalized(payload[k]) if k == 'content'
               else post.get(k) == payload[k] for k in FIELDS)


class NoRedirect(HTTPRedirectHandler):
    # Redirects can change POST into GET; an unexpected redirect is not success.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    def __init__(self, base, timeout, ca_file=None, insecure=False):
        self.base = base
        self.timeout = timeout
        context = ssl._create_unverified_context() if insecure else ssl.create_default_context(cafile=ca_file)
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=context))

    def request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        request = Request(self.base + path, data=data, headers={'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=self.timeout) as response:
            status = response.status
            body = json.load(response)
        if not isinstance(body, dict):
            raise ValueError('Expected a JSON object')
        return status, body

    def matches(self, payload):
        _, response = self.request('/posts?' + urlencode({'limit': 200, 'channel': payload['channel']}))
        posts = response.get('posts')
        if not isinstance(posts, list) or any(not isinstance(p, dict) for p in posts):
            raise ValueError('Invalid posts list')
        return [p for p in posts if same_payload(p, payload)]

    def verify(self, post_id, payload):
        if not isinstance(post_id, str) or not post_id.strip():
            return False
        _, post = self.request('/post/' + quote(post_id, safe=''))
        return post.get('id') == post_id and same_payload(post, payload)

    def detail_url(self, post_id):
        # Relay exposes /view/{id} beside /api/rss-relay (public) or /api (local).
        parsed = urlsplit(self.base)
        path = parsed.path
        suffix = '/api/rss-relay' if path.endswith('/api/rss-relay') else '/api'
        if not path.endswith(suffix):
            return None
        return urlunsplit((parsed.scheme, parsed.netloc, path[:-len(suffix)] + '/view/' + quote(post_id, safe=''), '', ''))


def open_receipts(state_dir):
    state_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state_dir / 'receipts.sqlite3', timeout=10)
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS receipts ('
                     'identity TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL, '
                     'post_id TEXT, detail_url TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


def save(conn, identity, state, post_id=None, detail_url=None):
    with conn:
        conn.execute('UPDATE receipts SET state=?, post_id=?, detail_url=?, updated_at=CURRENT_TIMESTAMP WHERE identity=?',
                     (state, post_id, detail_url, identity))


def recover(transport, conn, identity, payload, post_id=None, detail_url=None, status='duplicate'):
    """Reads only. Missing evidence never authorizes a second POST."""
    if not post_id:
        matches = transport.matches(payload)
        if len(matches) != 1:
            return result('unknown', code='unconfirmed', message='No unique remote match; no automatic repost')
        post_id = matches[0].get('id')
    if not transport.verify(post_id, payload):
        return result('unknown', post_id=post_id, detail_url=detail_url, code='readback_mismatch', message='Remote content could not be verified')
    detail_url = detail_url or transport.detail_url(post_id)
    save(conn, identity, 'confirmed', post_id, detail_url)
    return result(status, post_id=post_id, detail_url=detail_url, verification='current')


def publish(payload, key, base, state_dir, *, timeout=20, ca_file=None, insecure=False, dry_run=False):
    base = normalize_base(base)
    for name in FIELDS:
        if not isinstance(payload.get(name), str) or (name != 'url' and not payload[name].strip()):
            raise ValueError('Missing or invalid field: ' + name)
    if not key.strip():
        raise ValueError('dedupe-key must not be blank')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', payload['channel']):
        raise ValueError('Invalid channel identifier')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be a finite positive number')
    if dry_run:
        return dict(result('preview'), payload=payload, dedupe_key=key)

    transport = Transport(base, timeout, ca_file, insecure)
    identity = json.dumps([base, payload['channel'], payload['source'], key], ensure_ascii=False)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    with closing(open_receipts(Path(state_dir))) as conn:
        with conn:
            cursor = conn.execute('INSERT OR IGNORE INTO receipts(identity,digest,state) VALUES(?,?,?)', (identity, digest, 'pending'))
            claimed = cursor.rowcount == 1
            row = conn.execute('SELECT digest,state,post_id,detail_url FROM receipts WHERE identity=?', (identity,)).fetchone()
        if row[0] != digest:
            return result('conflict', code='key_conflict', message='Same identity has different content; use an explicit new version key')
        if row[1] == 'confirmed':
            return result('duplicate', post_id=row[2], detail_url=row[3], verification='historical')
        if not claimed:
            try:
                return recover(transport, conn, identity, payload, row[2], row[3])
            except (OSError, ValueError, HTTPException, sqlite3.Error):
                return result('unknown', post_id=row[2], detail_url=row[3], code='pending', message='Previous request remains unconfirmed; no automatic repost')

        # Preflight errors occur before POST and can safely release our claim.
        try:
            matches = transport.matches(payload)
        except (OSError, ValueError, HTTPException):
            with conn:
                conn.execute('DELETE FROM receipts WHERE identity=?', (identity,))
            return result('failed', code='preflight_failed', message='Could not read remote posts; nothing published')
        if matches:
            try:
                return recover(transport, conn, identity, payload)
            except (OSError, ValueError, HTTPException, sqlite3.Error):
                return result('unknown', code='adoption_failed', message='Existing remote article could not be verified')

        post_id = detail_url = None
        request_finished = False
        try:
            _status, response = transport.request('/post', payload)
            request_finished = True
            post_id, detail_url = response.get('id'), response.get('detail_url')
            if not isinstance(post_id, str) or not post_id.strip():
                post_id = None
            if not isinstance(detail_url, str) or urlsplit(detail_url).scheme not in ('http', 'https'):
                detail_url = None
            # Save the id even if the rest of the server reply is malformed.
            save(conn, identity, 'pending', post_id, detail_url)
            return recover(transport, conn, identity, payload, post_id, detail_url, 'published')
        except HTTPError as exc:
            if not request_finished and exc.code in REJECTED_CODES:
                with conn:
                    conn.execute('DELETE FROM receipts WHERE identity=?', (identity,))
                return result('failed', code='http_rejected', message=f'Relay rejected request (HTTP {exc.code})')
        except (OSError, ValueError, HTTPException, sqlite3.Error):
            pass
        # This also covers accepted writes followed by a lost/malformed response.
        try:
            return recover(transport, conn, identity, payload, post_id, detail_url, 'published')
        except (OSError, ValueError, HTTPException, sqlite3.Error):
            return result('unknown', post_id=post_id, detail_url=detail_url, code='unconfirmed', message='Request may have been accepted; no automatic repost')


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None):
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True, parser_class=Parser)
    command = commands.add_parser('publish')
    for name in ('file', 'title', 'channel', 'source', 'dedupe-key'):
        command.add_argument('--' + name, required=True)
    command.add_argument('--url', default='')
    command.add_argument('--base-url', default=os.environ.get('RSS_RELAY_BASE_URL', DEFAULT_BASE))
    command.add_argument('--state-dir', default=os.environ.get('RSS_RELAY_STATE_DIR'))
    command.add_argument('--ca-file', default=os.environ.get('RSS_RELAY_CA_FILE'))
    command.add_argument('--timeout', type=float, default=os.environ.get('RSS_RELAY_TIMEOUT', '20'))
    command.add_argument('--insecure', action='store_true')
    command.add_argument('--dry-run', action='store_true')
    try:
        args = parser.parse_args(argv)
        if args.file == '-':
            content = sys.stdin.read()
        else:
            with Path(args.file).open(encoding='utf-8-sig', newline='') as source:
                content = source.read()
        payload = {name: getattr(args, name) for name in FIELDS if name != 'content'}
        payload['content'] = content
        response = publish(payload, args.dedupe_key, args.base_url, args.state_dir or default_state_dir(),
                           timeout=args.timeout, ca_file=args.ca_file, insecure=args.insecure, dry_run=args.dry_run)
    except (OSError, ValueError, HTTPException, sqlite3.Error) as exc:
        response = result('failed', code='invalid_input_or_state', message=type(exc).__name__ + ': check input, configuration and state directory')
    print(json.dumps(response, ensure_ascii=False))
    return EXIT_CODES[response['status']]


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', newline='')
    raise SystemExit(main())
