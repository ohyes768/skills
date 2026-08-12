#!/usr/bin/env python3
"""同步 skill-agent-matrix.html 中 github skill 的最新版本。

用法：
    python scripts/sync_github_versions.py
    python scripts/sync_github_versions.py --dry-run
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

HTML = Path(__file__).resolve().parent.parent / "skill-agent-matrix.html"
BLOCK_RE = re.compile(
    r'(<script\s+type="application/json"\s+id="registry-data"\s*>\s*)(.*?)(\s*</script>)',
    re.DOTALL,
)
TAG_RE = re.compile(r"^v?(\d+(?:\.\d+)*)(?:[-_](.+))?$")


def load_from_html() -> dict:
    text = HTML.read_text(encoding="utf-8")
    m = BLOCK_RE.search(text)
    if not m:
        raise ValueError(f"{HTML} 中未找到 registry-data 块")
    return json.loads(m.group(2))


def write_to_html(data: dict) -> None:
    text = HTML.read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    HTML.write_text(BLOCK_RE.sub(rf"\1\n{payload}\n\3", text, count=1), encoding="utf-8")


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

    ap = argparse.ArgumentParser(description="同步 github skill 最新版本到 HTML")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    registry = load_from_html()
    today = date.today().isoformat()
    changed = 0
    github_skills = [s for s in registry["skills"] if s.get("source") == "github"]
    if not github_skills:
        print("HTML 中没有 source=github 的 skill。")
        return 0

    for skill in github_skills:
        name, repo = skill["name"], skill["repo"]
        try:
            version, head = latest_version(repo)
        except Exception as e:  # noqa: BLE001
            print(f"[x] {name}: {e}")
            skill["checked_at"] = today
            continue
        old = skill.get("latest_version")
        skill["latest_version"] = version
        skill["head_commit"] = head
        skill["checked_at"] = today
        if old != version:
            changed += 1
            print(f"[^] {name}: {old or '(无)'} -> {version}")
        else:
            print(f"[=] {name}: {version}")

    if args.dry_run:
        print("\n--dry-run：未写回")
    else:
        write_to_html(registry)
        print(f"\n已写回 {HTML.name}：{changed} 个有更新")
    return 0


if __name__ == "__main__":
    sys.exit(main())
