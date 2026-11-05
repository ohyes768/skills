"""运行目录与产物文件的基础工具：UTF-8 JSON 读写、原子落盘、单条状态输出。"""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"unserializable type: {type(value)!r}")


def write_json(path: Path, value: dict) -> None:
    """原子写入 UTF-8 JSON；失败时不破坏已有文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    text = json.dumps(value, ensure_ascii=False, indent=2, default=_json_default)
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def emit_status(status: str, artifacts: dict, issues: list) -> None:
    """向 stdout 输出单条 JSON 状态；正文与详细日志一律不进 stdout。"""
    print(
        json.dumps({"status": status, "artifacts": artifacts, "issues": issues}, ensure_ascii=False)
    )
    sys.stdout.flush()
