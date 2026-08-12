#!/usr/bin/env python3
"""将 GitHub 外部 skill clone/pull 到各 agent 的 skills 目录。

仓库级缓存在 .cache/github-skills/<skill名>/，各 agent 以 junction 指向缓存
（若注册表有 path 字段则指向缓存内子目录）。版本以注册表 latest_version /
head_commit 为准，建议先运行 sync_github_versions.py 刷新。

用法：
    python scripts/sync_github_skills.py
    python scripts/sync_github_skills.py --dry-run
    python scripts/sync_github_skills.py --status
    python scripts/sync_github_skills.py --skill UZI-Skill --agent openclaw
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
CACHE_ROOT = ROOT / ".cache" / "github-skills"
BLOCK_RE = re.compile(
    r'(<script\s+type="application/json"\s+id="registry-data"\s*>\s*)(.*?)(\s*</script>)',
    re.DOTALL,
)
COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)


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
        raise FileNotFoundError(f"目标目录不存在: {target}")

    if link.exists() or link.is_symlink():
        if is_junction(link):
            current = junction_target(link)
            if current == target:
                print("    [=] 已是正确 junction，跳过")
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


def run_git(*args: str, cwd: Path | None = None) -> str:
    cmd = ["git", *args]
    out = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if out.returncode != 0:
        detail = (out.stderr or out.stdout).strip()
        raise RuntimeError(detail or "git 命令失败")
    return out.stdout.strip()


def github_skills(registry: dict) -> dict[str, dict]:
    return {s["name"]: s for s in registry.get("skills", []) if s.get("source") == "github"}


def target_ref(skill: dict) -> str:
    version = (skill.get("latest_version") or "").strip()
    if version.startswith("HEAD@"):
        return (skill.get("head_commit") or version[5:]).strip()
    return version


def cache_repo_dir(skill_name: str) -> Path:
    return CACHE_ROOT / skill_name


def cache_content_dir(skill: dict) -> Path:
    repo_dir = cache_repo_dir(skill["name"])
    sub = (skill.get("path") or "").strip().replace("\\", "/").strip("/")
    return repo_dir / sub if sub else repo_dir


def agent_skills_root(skills_dir: Path, agent_cfg: dict) -> Path:
    subdir = agent_cfg.get("skills_subdir", "")
    return skills_dir / subdir if subdir else skills_dir


def agent_link_path(skills_dir: Path, skill_name: str, agent_cfg: dict) -> Path:
    return agent_skills_root(skills_dir, agent_cfg) / skill_name


def looks_like_commit(ref: str) -> bool:
    return bool(COMMIT_RE.match(ref))


def current_checkout(repo_dir: Path) -> str:
    if not (repo_dir / ".git").exists():
        return "(非 git)"
    try:
        return run_git("-C", str(repo_dir), "describe", "--tags", "--always", "--dirty")
    except RuntimeError:
        return run_git("-C", str(repo_dir), "rev-parse", "--short", "HEAD")


def clone_repo(repo: str, dest: Path, ref: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"    [plan] clone {repo} -> {dest}")
        print(f"    [plan] checkout {ref}")
        return

    print(f"    [*] 正在 clone（仓库较大时可能较慢）...", flush=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)

    if ref and not looks_like_commit(ref):
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", ref, repo, str(dest)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return
        if dest.exists():
            shutil.rmtree(dest)

    run_git("clone", repo, str(dest))
    run_git("-C", str(dest), "checkout", ref)
    if looks_like_commit(ref):
        run_git("-C", str(dest), "reset", "--hard", ref)


def update_repo(repo_dir: Path, repo: str, ref: str, *, dry_run: bool) -> None:
    if dry_run:
        print(f"    [plan] fetch + checkout {ref}")
        return

    if not (repo_dir / ".git").exists():
        shutil.rmtree(repo_dir)
        clone_repo(repo, repo_dir, ref, dry_run=False)
        return

    run_git("-C", str(repo_dir), "fetch", "--tags", "origin")
    try:
        run_git("-C", str(repo_dir), "checkout", ref)
        run_git("-C", str(repo_dir), "reset", "--hard", ref)
    except RuntimeError:
        if looks_like_commit(ref):
            run_git("-C", str(repo_dir), "fetch", "origin", ref, "--depth", "1")
            run_git("-C", str(repo_dir), "checkout", ref)
            run_git("-C", str(repo_dir), "reset", "--hard", ref)
            return
        raise


def ensure_skill_cache(skill: dict, *, dry_run: bool) -> Path:
    name = skill["name"]
    repo = skill["repo"]
    ref = target_ref(skill)
    if not ref:
        raise ValueError(f"{name}: 缺少 latest_version / head_commit，请先运行 sync_github_versions.py")

    repo_dir = cache_repo_dir(name)
    content_dir = cache_content_dir(skill)
    print(f"\n[cache] {name}")
    print(f"    仓库: {repo}")
    print(f"    目标版本: {ref}")
    print(f"    缓存: {repo_dir}")

    if not repo_dir.exists():
        clone_repo(repo, repo_dir, ref, dry_run=dry_run)
    else:
        before = current_checkout(repo_dir) if not dry_run else "?"
        update_repo(repo_dir, repo, ref, dry_run=dry_run)
        if not dry_run:
            after = current_checkout(repo_dir)
            mark = "=" if before == after else "^"
            print(f"    [{mark}] {before} -> {after}")

    if not dry_run and not content_dir.is_dir():
        raise FileNotFoundError(f"缓存内路径不存在: {content_dir}（检查注册表 path 字段）")
    if not dry_run and not (content_dir / "SKILL.md").exists():
        print(f"    [!] 警告: {content_dir} 下未找到 SKILL.md")

    return content_dir


def planned_links(
    config: dict,
    registry: dict,
    *,
    agent_filter: str | None,
    skill_filter: str | None,
) -> list[tuple[str, str, Path, dict]]:
    remote = github_skills(registry)
    rows: list[tuple[str, str, Path, dict]] = []

    for agent_key, agent_cfg in config.get("agents", {}).items():
        if agent_filter and agent_key != agent_filter:
            continue
        if not agent_cfg.get("enabled", False):
            continue

        skills_dir = expand_path(agent_cfg["skills_dir"])
        assigned = registry.get("agents", {}).get(agent_key, {}).get("skills", [])
        for skill_name in assigned:
            if skill_filter and skill_name != skill_filter:
                continue
            skill = remote.get(skill_name)
            if not skill:
                continue
            rows.append((agent_key, skill_name, agent_link_path(skills_dir, skill_name, agent_cfg), skill))

    return rows


def show_status(config: dict, registry: dict) -> int:
    remote = github_skills(registry)
    print(f"仓库: {ROOT}")
    print(f"GitHub skill: {len(remote)} 个")
    print(f"缓存目录: {CACHE_ROOT}\n")

    for name, skill in remote.items():
        repo_dir = cache_repo_dir(name)
        content = cache_content_dir(skill)
        ref = target_ref(skill) or "(未知)"
        print(f"  {name} — {skill.get('latest_version', '?')} ({ref})")
        if repo_dir.exists() and (repo_dir / ".git").exists():
            print(f"      缓存: {content} [{current_checkout(repo_dir)}]")
        else:
            print("      缓存: (未下载)")
        print()

    for agent_key, agent_cfg in config.get("agents", {}).items():
        enabled = agent_cfg.get("enabled", False)
        skills_dir = expand_path(agent_cfg["skills_dir"])
        link_root = agent_link_path(skills_dir, "_probe_", agent_cfg).parent
        flag = "ON " if enabled else "OFF"
        print(f"[{flag}] {agent_key} — {agent_cfg.get('description', '')}")
        print(f"      加载路径: {link_root} {'(存在)' if link_root.exists() else '(不存在)'}")
        if not enabled:
            print()
            continue

        assigned = registry.get("agents", {}).get(agent_key, {}).get("skills", [])
        github_assigned = [s for s in assigned if s in remote]
        print(f"      勾选 {len(github_assigned)} 个 GitHub skill:")
        for name in github_assigned:
            link = agent_link_path(skills_dir, name, agent_cfg)
            expected = cache_content_dir(remote[name])
            if is_junction(link):
                target = junction_target(link)
                ok = target == expected.resolve()
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

    parser = argparse.ArgumentParser(description="同步 GitHub skill 到各 agent（clone + junction）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不实际下载或创建链接")
    parser.add_argument("--skill", help="只同步指定 skill")
    parser.add_argument("--agent", help="只同步到指定 agent")
    parser.add_argument("--status", action="store_true", help="查看缓存与各 agent 链接状态")
    args = parser.parse_args()

    config = load_config()
    registry = load_registry(config)

    if args.status:
        return show_status(config, registry)

    rows = planned_links(config, registry, agent_filter=args.agent, skill_filter=args.skill)
    if not rows:
        print("没有需要同步的 GitHub skill。")
        print("检查 sync-config.json 的 enabled 开关，以及 skill-agent-matrix.html 中的 agent 勾选。")
        return 0

    unique_skills: dict[str, dict] = {}
    for _, skill_name, _, skill in rows:
        unique_skills[skill_name] = skill

    print(f"计划同步 {len(rows)} 个联接（{len(unique_skills)} 个 GitHub skill）" + ("（dry-run）" if args.dry_run else ""))

    cache_targets: dict[str, Path] = {}
    for skill_name, skill in unique_skills.items():
        try:
            cache_targets[skill_name] = ensure_skill_cache(skill, dry_run=args.dry_run)
        except Exception as exc:  # noqa: BLE001
            print(f"    [x] 缓存失败: {exc}")
            return 1

    ok = 0
    for agent_key, skill_name, link, skill in rows:
        target = cache_targets[skill_name]
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
