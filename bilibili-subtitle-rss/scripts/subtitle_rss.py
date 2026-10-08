#!/usr/bin/env python3
"""Extract pinned bili CLI subtitles; save Markdown and optionally publish to RSS Relay."""

import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

CLI_PACKAGE = 'git+https://github.com/ZeroMarker/bilibili-cli.git@6962d5b'
DEFAULT_ENDPOINT = 'https://web.duomi77.cn:9443/rss/api/rss-relay/post'
BV_PATTERN = r'BV[0-9A-Za-z]{10}'
VIDEO_HOSTS = {'bilibili.com', 'www.bilibili.com', 'm.bilibili.com'}


def resolve_short_link(url):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=30) as response:
        return response.url


def resolve_video(value):
    value = value.strip()
    if re.fullmatch(BV_PATTERN, value):
        return value, f'https://www.bilibili.com/video/{value}'
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or parsed.username or parsed.password:
        raise ValueError('请输入 BV 号或 B 站视频链接')
    if parsed.hostname == 'b23.tv':
        value = resolve_short_link(value)
        parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or parsed.hostname not in VIDEO_HOSTS:
        raise ValueError('链接必须指向 bilibili.com 的视频页面')
    match = re.fullmatch(r'/video/(' + BV_PATTERN + r')/?', parsed.path)
    if not match:
        raise ValueError('链接中未找到有效 BV 号')
    pages = parse_qs(parsed.query, keep_blank_values=True).get('p', ['1'])
    if pages != ['1']:
        raise ValueError('指定版本的 bili CLI 只提取第一 P，不能处理此分 P 链接')
    bvid = match.group(1)
    return bvid, f'https://www.bilibili.com/video/{bvid}'


def escape_text(value):
    # RSS Relay allows Markdown/HTML: subtitles must remain literal text.
    text = html.escape(str(value), quote=False)
    return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', text)


def merge_segments_to_paragraphs(segments, gap_threshold=1.5, max_chars=120):
    """Match douyin's pause/length grouping; count text characters, excluding join spaces."""
    paragraphs = []
    previous_end = None
    current_chars = 0
    for start, end, text in segments:
        if not paragraphs or start - previous_end > gap_threshold or current_chars >= max_chars:
            paragraphs.append([])
            current_chars = 0
        paragraphs[-1].append(text)
        current_chars += len(text)
        previous_end = end
    return [' '.join(paragraph) for paragraph in paragraphs]


def build_post(envelope, bvid):
    if not isinstance(envelope, dict) or envelope.get('ok') is not True or envelope.get('schema_version') != '1':
        raise ValueError('bili CLI 未返回成功的 schema_version=1 JSON')
    data = envelope.get('data')
    if not isinstance(data, dict):
        raise ValueError('bili CLI data 字段无效')
    video, subtitle = data.get('video'), data.get('subtitle')
    if not isinstance(video, dict) or video.get('bvid') != bvid:
        raise ValueError('返回视频 BV 号与请求不符')
    if not isinstance(subtitle, dict) or not subtitle.get('available') or not subtitle.get('items'):
        raise ValueError('未取得带时间戳的字幕：可能未登录、权限不足、视频无字幕或接口失败；未推送')
    if not isinstance(subtitle['items'], list):
        raise ValueError('字幕 items 格式无效')
    title = str(video.get('title') or bvid).strip()
    url = f'https://www.bilibili.com/video/{bvid}'
    owner = video.get('owner') or {}
    author = str(owner.get('name') or '未知') if isinstance(owner, dict) else '未知'
    lines = [f'# {escape_text(title)}', '', f'原视频：{url}', '',
             f'UP 主：{escape_text(author)}', '',
             f'视频时长：{escape_text(video.get("duration", "未知"))}', '',
             '以下为平台字幕原文，按停顿和字数合并分段，未作摘要或纠错。', '', '## 完整文字稿', '']
    segments = []
    previous_start = -1.0
    for item in subtitle['items']:
        if not isinstance(item, dict) or not isinstance(item.get('content'), str):
            raise ValueError('字幕条目或文本格式无效')
        try:
            start, end = float(item['from']), float(item['to'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('字幕时间戳缺失或无效') from exc
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start or start < previous_start:
            raise ValueError('字幕时间戳无效或顺序错误')
        previous_start = start
        text = item['content'].strip()
        if not text:
            continue
        segments.append((start, end, text))
    if not segments:
        raise ValueError('字幕内容为空；未推送')
    for paragraph in merge_segments_to_paragraphs(segments):
        lines.extend([escape_text(paragraph), ''])
    return {'title': f'B站文字稿｜{title}', 'content': '\n'.join(lines), 'url': url, 'source': 'bilibili'}


def extract(bvid, timeout):
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    command = ['uvx', '--from', CLI_PACKAGE, 'bili', 'video', bvid, '--subtitle-timeline', '--json']
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', env=env, timeout=timeout)
    if result.returncode:
        raise ValueError(f'bili CLI 退出码 {result.returncode}；请用相同命令检查登录、网络或视频权限')
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError('bili CLI 输出不是有效 JSON；未推送') from exc


def request_json(url, *, method='GET', payload=None, ca_file=None):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    req = Request(url, data=body, method=method, headers={
        'Accept': 'application/json', 'Content-Type': 'application/json; charset=utf-8',
        'User-Agent': 'bilibili-subtitle-rss/1.0',
    })
    context = ssl.create_default_context(cafile=ca_file)
    with urlopen(req, timeout=30, context=context) as response:
        if method == 'POST' and response.status != 201:
            raise ValueError(f'RSS 接口返回 {response.status}，未确认创建成功；请查远端后再试')
        return json.load(response)


def receipt_path(post, endpoint, output):
    key = hashlib.sha256((endpoint + '\n' + post['url']).encode('utf-8')).hexdigest()[:24]
    return output / f'{key}.receipt.json'


def publish(post, endpoint, output, ca_file=None):
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.query or parsed.fragment or not endpoint.endswith('/post'):
        raise ValueError('--endpoint 应为完整 /post 接口地址，不带 query 或 fragment')
    output.mkdir(parents=True, exist_ok=True)
    receipt = receipt_path(post, endpoint, output)
    if receipt.exists():
        saved = json.loads(receipt.read_text(encoding='utf-8'))
        return {'status': 'duplicate', 'id': saved['id'], 'matched': 'local-receipt'}
    # Fail closed: do not publish if the duplicate check fails.
    remote = request_json(endpoint[:-4] + 'posts?limit=200', ca_file=ca_file)
    if not isinstance(remote, dict) or not isinstance(remote.get('posts'), list):
        raise ValueError('RSS 列表响应格式无效，无法查重；未推送')
    bvid = post['url'].rsplit('/', 1)[-1]
    for existing in remote['posts']:
        if not isinstance(existing, dict):
            raise ValueError('RSS 列表条目格式无效；未推送')
        # Resolve only ordinary video URLs during deduplication, never remote short links.
        old_url = existing.get('url') or ''
        old = urlsplit(old_url)
        if old.hostname not in VIDEO_HOSTS:
            continue
        try:
            old_bvid, _ = resolve_video(old_url)
        except ValueError:
            continue
        if old_bvid == bvid:
            result = {'status': 'duplicate', 'id': existing['id'], 'matched': 'remote-list'}
            receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            return result
    # Exactly one POST. A timeout may mean the server accepted it: never retry automatically.
    created = request_json(endpoint, method='POST', payload=post, ca_file=ca_file)
    if not isinstance(created, dict) or not isinstance(created.get('id'), str) or not created['id']:
        raise ValueError('POST 响应缺少有效 id；请检查远端是否已创建，勿直接重试')
    result = {'status': 'published', 'id': created['id'], 'url': post['url'], 'endpoint': endpoint}
    receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', help='BV 号、B 站完整视频链接或 b23.tv 短链接')
    parser.add_argument('--push', action='store_true', help='执行一次 RSS 推送；默认只生成本地文件')
    parser.add_argument('--endpoint', default=DEFAULT_ENDPOINT)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'output')
    parser.add_argument('--input-json', type=Path, help='复用本次视频已保存的 CLI JSON，避免重复提取')
    parser.add_argument('--timeout', type=int, default=180, help='CLI 超时秒数')
    parser.add_argument('--ca-file', help='自定义受信任 CA 证书文件；默认验证 TLS')
    args = parser.parse_args(argv)
    try:
        bvid, _ = resolve_video(args.video)
        if args.push and receipt_path({'url': f'https://www.bilibili.com/video/{bvid}'}, args.endpoint, args.output_dir).exists():
            result = publish({'url': f'https://www.bilibili.com/video/{bvid}'}, args.endpoint, args.output_dir, args.ca_file)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        envelope = json.loads(args.input_json.read_text(encoding='utf-8-sig')) if args.input_json else extract(bvid, args.timeout)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        raw_file = args.output_dir / f'{bvid}.cli.json'
        raw_file.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding='utf-8')
        post = build_post(envelope, bvid)
        markdown_file = args.output_dir / f'{bvid}.md'
        markdown_file.write_text(post['content'], encoding='utf-8')
        (args.output_dir / f'{bvid}.post.json').write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding='utf-8')
        result = publish(post, args.endpoint, args.output_dir, args.ca_file) if args.push else {'status': 'saved'}
        result['markdown'] = str(markdown_file.resolve())
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(f'失败：{exc}', file=sys.stderr)
        if args.push:
            print('若发生在 POST 阶段，请先查询远端记录，确认没有创建后再重试。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
