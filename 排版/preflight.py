"""构建前检查字体指纹与必需的单页 PDF。"""
from __future__ import annotations

import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"


def check_fonts() -> None:
    for line in (HERE / "requirements.txt").read_text(encoding="utf-8").splitlines():
        name, expected_version = line.split("==", 1)
        try:
            actual = version(name)
        except PackageNotFoundError:
            actual = "未安装"
        if actual != expected_version:
            raise RuntimeError(f"依赖版本不符：{name} 应为 {expected_version}，实际为 {actual}；"
                               "请在排版目录运行 python -m pip install -r requirements.txt")
    expected = json.loads((FONTS / "manifest.json").read_text(encoding="utf-8"))
    errors = []
    for name, digest in expected.items():
        path = FONTS / name
        if not path.is_file():
            errors.append(f"缺少字体：{path}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(f"字体版本不符：{path}")
    if errors:
        raise RuntimeError("\n".join(errors) + "\n请从仓库恢复锁定的字体文件。")


def require_single_page(paths: list[Path]) -> None:
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"缺少拼页文件：{path}；请先运行 python3 排版/封面/build.py")
    for path in paths:
        with pymupdf.open(path) as doc:
            if doc.page_count != 1 or doc.is_encrypted:
                raise ValueError(f"拼页文件须为未加密的单页 PDF：{path}")
            rect = doc[0].rect
            if abs(rect.width - 210 * 72 / 25.4) > 1 or abs(rect.height - 297 * 72 / 25.4) > 1:
                raise ValueError(f"拼页文件须为 A4 竖页：{path}")
