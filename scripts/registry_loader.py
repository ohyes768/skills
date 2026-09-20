"""三个 sync 脚本的共享注册表加载器。

registry.json 是 skill 清单与 agent 分配的唯一真源（可版本控制）；
GitHub 版本快照（latest_version/head_commit/checked_at）属于运行状态，
不写回注册表，保存在机器本地的 .cache/github-versions.json（不入 git）。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "registry.json"
VERSIONS_PATH = ROOT / ".cache" / "github-versions.json"

EMPTY_VERSIONS = {"version": 1, "updated": "", "skills": {}}


def load_registry() -> dict:
    """读取注册表真源；缺失时给出明确指引而不是继续用旧数据源。"""
    if not REGISTRY_PATH.is_file():
        raise FileNotFoundError(
            f"{REGISTRY_PATH} 不存在。registry.json 是注册表真源，"
            "请先用 backend/skill-manager/scripts/migrate_registry.py 从 "
            "skill-agent-matrix.html 迁移生成。"
        )
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def load_versions() -> dict:
    """读取机器本地的 GitHub 版本快照；无文件时返回空结构。"""
    if not VERSIONS_PATH.is_file():
        return json.loads(json.dumps(EMPTY_VERSIONS))
    return json.loads(VERSIONS_PATH.read_text(encoding="utf-8"))


def save_versions(data: dict) -> None:
    """原子写入 GitHub 版本快照。"""
    VERSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = VERSIONS_PATH.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(VERSIONS_PATH)
