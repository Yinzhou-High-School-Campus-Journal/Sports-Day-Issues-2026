"""用仓库中的静态 TrueType 输入生成封面字重子集，无需本机字体或 uv。"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from preflight import check_fonts


def main() -> None:
    check_fonts()
    source, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    bodies = re.findall(r"<body>(.*?)</body>", source.read_text(encoding="utf-8"), re.S)
    if not bodies:
        raise ValueError("未找到封面 HTML 的正文")
    text = html.unescape(re.sub(r"<[^>]+>", "", "".join(bodies)))
    chars = set(text) | set(chr(c) for c in range(0x20, 0x7F)) | set("，。：；、「」《》——…·〇")
    chars = "".join(sorted(c for c in chars if not c.isspace() or c == " "))
    for source in sorted((HERE.parent / "fonts/封面").glob("*.ttf")):
        font = TTFont(source, recalcTimestamp=False)
        options = subset.Options()
        options.layout_features = ["*"]
        options.name_IDs = ["*"]
        options.notdef_outline = True
        options.glyph_names = False
        options.hinting = False
        cutter = subset.Subsetter(options)
        cutter.populate(text=chars)
        cutter.subset(font)
        font.save(outdir / source.name)
        font.close()
        print("字体子集：", source.name)


if __name__ == "__main__":
    main()
