"""pytest 路径装配：把 scripts/ 加入 sys.path，使 `from gold import ...` 生效。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
