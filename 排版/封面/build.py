#!/usr/bin/env python3
"""生成两期封面与扉页（输出在本目录）；使用与内页相同的锁定浏览器和仓库字体。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from preflight import check_requirements, prepare_fonts, require_single_page, sources_unchanged
check_requirements()            # 先核对依赖：没装或版本不对时给出安装提示，而不是在下面导入时报错

import pymupdf

from pdf_metadata import document_metadata

PAGES = [(issue, mode, HERE / script) for issue, script in
         [("第一期", "make_pages.py"), ("第二期", "make_issue2.py")]
         for mode in ["cover", "title"]]


def main() -> None:
    prepare_fonts()
    with sources_unchanged(), tempfile.TemporaryDirectory(prefix="sports-day-covers-") as tmp:
        tmp = Path(tmp)
        outputs = []
        for issue, mode, script in PAGES:
            name = issue + ("封面" if mode == "cover" else "扉页")
            html, pdf, png = tmp / f"{name}.html", tmp / f"{name}.pdf", tmp / f"{name}.png"
            subprocess.run([sys.executable, str(script), f"mode={mode}", f"out={html}"], check=True)
            subprocess.run(["node", str(HERE / "render.cjs"), str(html), str(pdf), str(png)], check=True)
            with pymupdf.open(pdf) as doc:
                doc.set_metadata(document_metadata(issue, "封面" if mode == "cover" else "扉页",
                                                   doc.metadata.get("producer", "")))
                doc.saveIncr()
            require_single_page([pdf])
            outputs.extend([pdf, png])
        # 全部成功后再替换既有成品，失败不留下半套封面
        for source in outputs:
            (HERE / source.name).write_bytes(source.read_bytes())
    print(f"完成：两期封面与扉页（4 PDF、4 PNG），输出至 {HERE}")


if __name__ == "__main__":
    main()
