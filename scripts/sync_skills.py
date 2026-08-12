#!/usr/bin/env python3
"""将自研 skill 以 junction 同步到各 agent 的 skills 目录。

读取 sync-config.json（agent 路径与 enabled 开关）和 skill-agent-matrix.html
（skill 清单与各 agent 勾选关系），为 source=local 的 skill 创建目录联接。

用法：
    python scripts/sync_skills.py
    python scripts/sync_skills.py --dry-run
    python scripts/sync_skills.py --skill git-commit-push
    python scripts/sync_skills.py --agent claudecode
    python scripts/sync_skills.py --status
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "sync-config.json"
BLOCK_RE = re.compile(
    r'(<script\s+type="application/json"\s+id="registry-data"\s*>\s*)(.*?)(\s*</script>)',
    re.DOTALL,
)


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def load_registry(config: dict) -> dict:
    html = ROOT / config.get("registry", "skill-agent-matrix.html")
    text = html.read_text(encoding="utf-8")
    match = BLOCK_RE.search(text)
    if not match:
        raise ValueError(f"{html} 中未找到 registry-data 块")
    return json.loads(match.group(2))


def expand_path(raw: str) -> Path:
    return Path(raw.replace("\\", "/").replace("~", str(Path.home()))).resolve()


def is_junction(path: Path) -> bool:
    if not path.exists():
        return False
    if hasattr(path, "is_junction") and path.is_junction():
        return True
    try:
        return bool(path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, AttributeError):
        return path.is_symlink()


def junction_target(path: Path) -> Path | None:
    if not is_junction(path):
        return None
    try:
        return path.resolve()
    except OSError:
        return None


def remove_link(path: Path, *, dry_run: bool) -> None:
    if not path.exists() and not path.is_symlink():
        return
    label = "移除旧链接" if is_junction(path) or path.is_symlink() else "备份旧目录"
    print(f"    {label}: {path}")
    if dry_run:
        return
    if is_junction(path) or path.is_symlink():
        path.rmdir()
    else:
        backup = path.with_name(f"{path.name}.bak")
        if backup.exists():
            shutil.rmtree(backup)
        path.rename(backup)
        print(f"    已备份到: {backup}")


def create_junction(link: Path, target: Path, *, dry_run: bool) -> None:
    target = target.resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"源目录不存在: {target}")

    if link.exists() or link.is_symlink():
        if is_junction(link):
            current = junction_target(link)
            if current == target:
                print(f"    [=] 已是正确 junction，跳过")
                return
        remove_link(link, dry_run=dry_run)

    print(f"    [+] junction -> {target}")
    if dry_run:
        return

    link.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "mklink 失败")


def local_skill_dirs(registry: dict) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for skill in registry.get("skills", []):
        if skill.get("source") != "local":
            continue
        name = skill["name"]
        rel = skill.get("dir", name)
        mapping[name] = (ROOT / rel).resolve()
    return mapping


def agent_skills_root(skills_dir: Path, agent_cfg: dict) -> Path:
    subdir = agent_cfg.get("skills_subdir", "")
    return skills_dir / subdir if subdir else skills_dir


def agent_link_path(skills_dir: Path, skill_name: str, agent_cfg: dict) -> Path:
    return agent_skills_root(skills_dir, agent_cfg) / skill_name


def planned_syncs(
    config: dict,
    registry: dict,
    *,
    agent_filter: str | None,
    skill_filter: str | None,
) -> list[tuple[str, str, Path, Path]]:
    local = local_skill_dirs(registry)
    rows: list[tuple[str, str, Path, Path]] = []

    for agent_key, agent_cfg in config.get("agents", {}).items():
        if agent_filter and agent_key != agent_filter:
            continue
        if not agent_cfg.get("enabled", False):
            continue

        skills_dir = expand_path(agent_cfg["skills_dir"])
        agent_registry = registry.get("agents", {}).get(agent_key, {})
        for skill_name in agent_registry.get("skills", []):
            if skill_filter and skill_name != skill_filter:
                continue
            if skill_name not in local:
                continue
            rows.append(
                (agent_key, skill_name, agent_link_path(skills_dir, skill_name, agent_cfg), local[skill_name])
            )

    return rows


def show_status(config: dict, registry: dict) -> int:
    local = local_skill_dirs(registry)
    print(f"仓库: {ROOT}")
    print(f"自研 skill: {len(local)} 个\n")

    for agent_key, agent_cfg in config.get("agents", {}).items():
        enabled = agent_cfg.get("enabled", False)
        skills_dir = expand_path(agent_cfg["skills_dir"])
        subdir = agent_cfg.get("skills_subdir", "")
        link_root = agent_link_path(skills_dir, "_probe_", agent_cfg).parent
        exists = link_root.exists()
        flag = "ON " if enabled else "OFF"
        print(f"[{flag}] {agent_key} — {agent_cfg.get('description', '')}")
        print(f"      加载路径: {link_root} {'(存在)' if exists else '(不存在)'}")
        if agent_cfg.get("source_repo"):
            print(f"      源仓库: {expand_path(agent_cfg['source_repo'])}")
        if not enabled:
            print()
            continue

        assigned = registry.get("agents", {}).get(agent_key, {}).get("skills", [])
        local_assigned = [s for s in assigned if s in local]
        print(f"      勾选 {len(local_assigned)} 个自研 skill:")
        for name in local_assigned:
            link = agent_link_path(skills_dir, name, agent_cfg)
            src = local[name]
            if is_junction(link):
                target = junction_target(link)
                ok = target == src
                mark = "=" if ok else "!"
                print(f"        [{mark}] {name} -> {target or '?'}")
            elif link.exists():
                print(f"        [copy] {name}（普通目录，非 junction）")
            else:
                print(f"        [-] {name}（未同步）")
        print()
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="同步自研 skill 到各 agent（junction）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不实际创建")
    parser.add_argument("--skill", help="只同步指定 skill")
    parser.add_argument("--agent", help="只同步到指定 agent")
    parser.add_argument("--status", action="store_true", help="查看当前同步状态")
    args = parser.parse_args()

    config = load_config()
    registry = load_registry(config)

    if args.status:
        return show_status(config, registry)

    rows = planned_syncs(config, registry, agent_filter=args.agent, skill_filter=args.skill)
    if not rows:
        print("没有需要同步的 skill。")
        print("检查 sync-config.json 的 enabled 开关，以及 skill-agent-matrix.html 中的 agent 勾选。")
        return 0

    print(f"计划同步 {len(rows)} 个联接" + ("（dry-run）" if args.dry_run else ""))
    ok = 0
    for agent_key, skill_name, link, target in rows:
        print(f"\n{agent_key} / {skill_name}")
        print(f"    链接: {link}")
        try:
            create_junction(link, target, dry_run=args.dry_run)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"    [x] 失败: {exc}")

    print(f"\n完成: {ok}/{len(rows)}")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
