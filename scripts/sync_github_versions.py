#!/usr/bin/env python3
"""刷新 GitHub skill 的最新版本快照。

注册表（registry.json）只保存 skill 清单与 agent 分配；版本快照
（latest_version/head_commit/checked_at）是运行状态，保存在机器本地的
.cache/github-versions.json（不入 git）。脚本对每个 github skill 执行
git ls-remote（不走 GitHub REST API、无需 token）。

用法：
    python scripts/sync_github_versions.py
    python scripts/sync_github_versions.py --dry-run
"""

import argparse
import re
import subprocess
import sys
from datetime import date

from registry_loader import load_registry, load_versions, save_versions

TAG_RE = re.compile(r"^v?(\d+(?:\.\d+)*)(?:[-_](.+))?$")


def parse_tag(tag: str):
    m = TAG_RE.match(tag)
    if not m:
        return None
    nums = tuple(int(x) for x in m.group(1).split("."))
    suffix = m.group(2) or ""
    return (nums, 0 if suffix else 1, suffix)


def git_ls_remote(repo: str, *flags: str, refs: tuple[str, ...] = ()) -> list[str]:
    cmd = ["git", "ls-remote", *flags, repo, *refs]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, encoding="utf-8")
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "git ls-remote failed")
    return [line for line in out.stdout.splitlines() if line.strip()]


def latest_version(repo: str) -> tuple[str, str]:
    head_lines = git_ls_remote(repo, refs=("HEAD",))
    head = head_lines[0].split()[0][:7] if head_lines else "unknown"
    tags = []
    for line in git_ls_remote(repo, "--tags", "--refs"):
        tags.append(line.split()[1].rsplit("/", 1)[-1])
    parsed = [(parse_tag(t), t) for t in tags]
    parsed = [(k, t) for k, t in parsed if k is not None]
    if parsed:
        parsed.sort(key=lambda x: x[0])
        return parsed[-1][1], head
    return f"HEAD@{head}", head


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="刷新 github skill 版本快照（.cache/github-versions.json）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    registry = load_registry()
    versions = load_versions()
    today = date.today().isoformat()
    changed = 0
    github_skills = [s for s in registry.get("skills", []) if s.get("source") == "github"]
    if not github_skills:
        print("registry.json 中没有 source=github 的 skill。")
        return 0

    for skill in github_skills:
        skill_id, repo = skill["id"], skill["repository"]
        try:
            version, head = latest_version(repo)
        except Exception as e:  # noqa: BLE001
            print(f"[x] {skill_id}: {e}")
            versions.setdefault("skills", {}).setdefault(skill_id, {})["checked_at"] = today
            continue
        old = versions.get("skills", {}).get(skill_id, {}).get("latest_version")
        versions.setdefault("skills", {})[skill_id] = {
            "latest_version": version,
            "head_commit": head,
            "checked_at": today,
        }
        if old != version:
            changed += 1
            print(f"[^] {skill_id}: {old or '(无)'} -> {version}")
        else:
            print(f"[=] {skill_id}: {version}")

    versions["updated"] = today
    if args.dry_run:
        print("\n--dry-run：未写入快照")
    else:
        save_versions(versions)
        print(f"\n已写入 .cache/github-versions.json：{changed} 个有更新")
    return 0


if __name__ == "__main__":
    sys.exit(main())
