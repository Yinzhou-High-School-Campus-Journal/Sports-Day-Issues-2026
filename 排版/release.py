#!/usr/bin/env python3
"""两期完整制作入口：字体检查 → 封面与扉页 → 内页排版与拼页。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from preflight import check_fonts

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue", choices=["第一期", "第二期", "全部"], nargs="?", default="全部")
    args = parser.parse_args()
    check_fonts()
    # 显式传入当前虚拟环境的 Python，避免子进程切换依赖版本。
    subprocess.run([sys.executable, str(HERE / "封面/build.py")], check=True)
    issues = ["第一期", "第二期"] if args.issue == "全部" else [args.issue]
    for issue in issues:
        subprocess.run([sys.executable, str(HERE / issue / "fonts.py")], check=True)
        subprocess.run([sys.executable, str(HERE / issue / "build.py"), issue], check=True)


if __name__ == "__main__":
    main()
