#!/usr/bin/env python3
"""把真源 rss_relay_client.py 同步到所有业务副本。

真源是本包 scripts/rss_relay_client.py；副本清单由 consumer_paths() 给出，
必须与 tests/test_clients.py 的 CONSUMERS 一致（该文件里有守卫测试）。
仓库外兄弟项目（daily-review、stock-info-dingding）的副本也一并同步。
独立安装的公共包没有副本，本脚本只在 skills 源码仓库内运行。

用法：
  python sync_shims.py           # 同步：与真源不一致的副本直接覆盖
  python sync_shims.py --check   # 只检查：发现漂移退出码 1（pre-commit 使用）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

CANONICAL = Path(__file__).resolve().with_name('rss_relay_client.py')
PACKAGE = CANONICAL.parent.parent  # knowledge/rss-relay-publish
ROOT = PACKAGE.parents[1]  # skills 仓库根
PROJECT_ROOT = ROOT.parent  # 兄弟项目所在目录

REPO_CONSUMERS = (
    'personal-tools/bilibili-subtitle-rss',
    'hk-ipo-research',
    'finance-macro/a-share-macro-impact-skill',
    'finance-macro/bond-market-macro-impact-skill',
    'personal-tools/waytoagi-update-log',
)
SIBLING_CONSUMERS = ('daily-review', 'stock-info-dingding')


def consumer_paths() -> list[Path]:
    paths = [ROOT / name / 'scripts/rss_relay_client.py' for name in REPO_CONSUMERS]
    paths += [PROJECT_ROOT / name / 'rss_relay_client.py' for name in SIBLING_CONSUMERS]
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description='同步 rss_relay_client.py 真源到全部业务副本')
    parser.add_argument('--check', action='store_true', help='只检查漂移，不修改文件；发现漂移退出码 1')
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if stream.encoding and stream.encoding.lower() not in ('utf-8', 'utf8'):
            stream.reconfigure(encoding='utf-8', errors='replace')

    if not (ROOT / '.git').exists():
        print('本脚本只在 skills 源码仓库内运行；独立安装的公共包没有副本需要同步。', file=sys.stderr)
        return 2
    if not CANONICAL.is_file():
        print(f'真源缺失：{CANONICAL}', file=sys.stderr)
        return 2

    canonical = CANONICAL.read_bytes()
    changed = 0
    for path in consumer_paths():
        label = path.relative_to(PROJECT_ROOT)
        if not path.parent.is_dir():
            print(f'跳过（目录不存在）：{label}')
            continue
        if path.is_file() and path.read_bytes() == canonical:
            print(f'一致：{label}')
            continue
        changed += 1
        if args.check:
            print(f'漂移：{label}')
        else:
            path.write_bytes(canonical)
            print(f'已同步：{label}')

    if args.check:
        if changed:
            print(f'\n{changed} 份副本与真源不一致。修复：python knowledge/rss-relay-publish/scripts/sync_shims.py')
            return 1
        print('\n全部副本与真源一致。')
        return 0
    print(f'\n同步完成：{changed} 份已更新。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
