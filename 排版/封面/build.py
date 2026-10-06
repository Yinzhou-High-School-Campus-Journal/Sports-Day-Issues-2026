#!/usr/bin/env python3
"""从仓库字体生成两期封面与扉页；使用与内页相同的锁定浏览器。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from preflight import check_fonts, require_single_page
from pdf_metadata import document_metadata
import pymupdf


def main() -> None:
    check_fonts()
    out = Path(os.environ.get("OUT", HERE)).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sports-day-covers-") as tmp:
        tmp = Path(tmp)
        fontdir = tmp / "fonts"
        pages = [(issue, mode, HERE / script) for issue, script in
                 [("第一期", "make_pages.py"), ("第二期", "make_issue2.py")]
                 for mode in ["cover", "title"]]

        def make_pages() -> list[Path]:
            result = []
            for issue, mode, script in pages:
                html = tmp / f"{issue}-{mode}.html"
                subprocess.run([sys.executable, str(script), f"mode={mode}",
                                f"fontdir={fontdir}", f"out={html}"], check=True)
                result.append(html)
            return result

        html_pages = make_pages()
        text = tmp / "alltext.html"
        text.write_text("".join(p.read_text(encoding="utf-8") for p in html_pages), encoding="utf-8")
        subprocess.run([sys.executable, str(HERE / "fontprep.py"), str(text), str(fontdir)], check=True)
        html_pages = make_pages()
        # 全部成功后再替换既有成品，失败不留下半套封面。
        outputs = []
        for (issue, mode, _), html in zip(pages, html_pages):
            name = issue + ("封面" if mode == "cover" else "扉页")
            pdf, png = tmp / f"{name}.pdf", tmp / f"{name}.png"
            subprocess.run(["node", str(HERE / "render.cjs"), str(html), str(pdf), str(png)], check=True)
            with pymupdf.open(pdf) as doc:
                doc.set_metadata(document_metadata(issue, "封面" if mode == "cover" else "扉页", doc.metadata.get("producer", "")))
                doc.saveIncr()
            require_single_page([pdf])
            outputs.extend([pdf, png])
        for source in outputs:
            (out / source.name).write_bytes(source.read_bytes())
    print(f"完成：两期封面与扉页（4 PDF、4 PNG），输出至 {out}")


if __name__ == "__main__":
    main()
