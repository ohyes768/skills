"""Preview or retire the old profile-local runbook and forward its validator.

Run only during an authorized installation/synchronization, never per analysis.
Existing files are backed up, never deleted. Default is read-only preview.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

MARKER = "basic-quality-rating canonical validator migration v1"
RETIRED_SKILL = """---
name: quality-rating-pipeline-runbook
description: 旧版质量评级执行手册的兼容入口；当前评级请直接读取 basic-quality-rating。
---

# 旧执行手册已合并

方法论、财务评分、PDF 取证与输出校验均由 `basic-quality-rating` 维护。
不再使用本手册的旧整数占位、逐项财务反算、历史案例或独立算分规则。
旧 `scripts/validate_rating_json.py <rating.json>` 命令仅转发主 skill 校验器。
使用主 skill 的 `financial`、`calculate`、`finalize` 与 PDF 取证命令。
数值/结构失败需要修复；文字提示交由人工复核，不能据此修改算分规则。
安装前版本已备份为同路径 `.pre-unification.bak`，不作为运行时规则加载。
"""


def _atomic_write(path, content):
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def retire_runbook(runbook_dir, skill_dir, *, apply=False):
    runbook = Path(runbook_dir).resolve()
    skill = Path(skill_dir).resolve()
    target = skill / "scripts/validate_rating_json.py"
    if runbook == skill or runbook in skill.parents or skill in runbook.parents:
        raise ValueError("旧 runbook 与主 skill 必须是独立目录")
    if not target.is_file() or not (skill / "scripts/rating_math.py").is_file():
        raise ValueError("主 skill 缺少规范校验器或 rating_math.py；请先安装新版")
    entry = runbook / "SKILL.md"
    text = entry.read_text(encoding="utf-8")
    if not re.search(r"^name:\s*quality-rating-pipeline-runbook\s*$", text, re.MULTILINE):
        raise ValueError("目标不是 quality-rating-pipeline-runbook，不执行迁移")
    old_validator = runbook / "scripts/validate_rating_json.py"
    if not old_validator.is_file():
        raise ValueError("旧校验器不存在，请核对 runbook 路径")
    shim = (
        f'"""{MARKER}."""\n'
        "import os\nimport subprocess\nimport sys\nfrom pathlib import Path\n\n"
        f"skill = Path(os.environ.get('BASIC_QUALITY_RATING_DIR', {str(skill)!r}))\n"
        "target = skill / 'scripts' / 'validate_rating_json.py'\n"
        "if not target.is_file():\n"
        "    print('Canonical validator missing; reinstall basic-quality-rating or set BASIC_QUALITY_RATING_DIR', file=sys.stderr)\n"
        "    raise SystemExit(2)\n"
        "raise SystemExit(subprocess.run([sys.executable, str(target), *sys.argv[1:]], check=False).returncode)\n"
    )
    desired = {entry: RETIRED_SKILL.encode("utf-8"), old_validator: shim.encode("utf-8")}
    changed = {path: body for path, body in desired.items() if path.read_bytes() != body}
    if not changed:
        return {"status": "unchanged", "paths": []}
    owned_forwarder = text == RETIRED_SKILL and old_validator.read_text(
        encoding="utf-8"
    ).startswith(f'"""{MARKER}."""')
    # Check every backup before touching any live file.
    for path in changed:
        backup = path.with_name(path.name + ".pre-unification.bak")
        if (
            backup.exists()
            and backup.read_bytes() != path.read_bytes()
            and not (path == old_validator and owned_forwarder)
        ):
            raise ValueError(f"已有不同版本备份，保留原文件并停止: {backup}")
    if apply:
        for path in changed:
            backup = path.with_name(path.name + ".pre-unification.bak")
            if not backup.exists():
                backup.write_bytes(path.read_bytes())
        # Forward the command before retiring the instructions.
        for path in (old_validator, entry):
            if path in changed:
                _atomic_write(path, changed[path])
    return {"status": "updated" if apply else "preview", "paths": [str(p) for p in changed]}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runbook-dir", required=True)
    parser.add_argument("--skill-dir", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = retire_runbook(args.runbook_dir, args.skill_dir, apply=args.apply)
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
