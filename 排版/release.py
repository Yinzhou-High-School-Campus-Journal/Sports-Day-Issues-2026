#!/usr/bin/env python3
"""完整制作入口：准备字体 → 封面与扉页 → 内页排版与拼页。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from preflight import prepare_fonts, sources_unchanged

HERE = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("issue", choices=["第一期", "第二期", "全部"], nargs="?", default="全部")
    args = parser.parse_args()
    prepare_fonts()
    issues = ["第一期", "第二期"] if args.issue == "全部" else [args.issue]
    with sources_unchanged():
        # 显式传入当前虚拟环境的 Python，避免子进程切换依赖版本
        subprocess.run([sys.executable, str(HERE / "封面/build.py")], check=True)
        for issue in issues:
            subprocess.run([sys.executable, str(HERE / issue / "build.py"), issue], check=True)


if __name__ == "__main__":
    main()
