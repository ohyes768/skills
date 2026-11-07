"""pytest 路径配置：把 scripts/ 加入 sys.path，测试可直接 import daily_pick。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
