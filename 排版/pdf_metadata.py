"""两期及封面共用的 PDF 元数据、页码标签与书签校正。"""
from __future__ import annotations

import html
import re

ISSUE_NAMES = {"第一期": "云图试骏", "第二期": "骋风逐曜"}
AUTHOR = "《鄞年・思叙》编辑部"
SUBJECT = "鄞州中学第四十四届暨鄞州蓝青高级中学第二十九届校园运动会特别刊物"


def document_metadata(issue: str, part: str, producer: str = "") -> dict[str, str]:
    """标题为「校运会特刊 + 期次 + 刊名 + 输出类型」；实际的 PDF 生成器原样保留。"""
    return {
        "title": " ".join(("校运会特刊", issue, ISSUE_NAMES[issue], part)),
        "author": AUTHOR,
        "subject": SUBJECT,
        "creator": "校运会特刊排版程序（HTML → Chromium）",
        "producer": producer,
    }


def pdf_text(s: str) -> str:
    """PDF 文本串：UTF-16BE 加 BOM 的十六进制串，中文在各阅读器里都不乱码。"""
    return "<FEFF" + s.encode("utf-16-be").hex().upper() + ">"


def set_page_labels(doc, uncounted: dict[int, str]) -> None:
    """页码标签与印出来的页码一致。uncounted 为不计页数的页 {第几页（从 1 数）: 标签}，直接用中文标签；
    其余页用阿拉伯数字，从这些页之后连续计数。
    （PyMuPDF 的 set_page_labels 把中文前缀存成不带 BOM 的 UTF-8，有的阅读器显示乱码，所以直接写页码树。）"""
    nums, in_run = [], False
    for n in range(1, doc.page_count + 1):
        if n in uncounted:
            nums.append(f"{n - 1} <</P {pdf_text(uncounted[n])}>>")
            in_run = False
        elif not in_run:
            printed = n - sum(1 for u in uncounted if u < n)
            nums.append(f"{n - 1} <</S /D /St {printed}>>")
            in_run = True
    doc.xref_set_key(doc.pdf_catalog(), "PageLabels", f"<</Nums [{' '.join(nums)}]>>")


HEADING = re.compile(r"<h([1-6])\b[^>]*>(.*?)</h\1>", re.S)


def html_headings(html_text: str) -> list[str]:
    """HTML 里按出现顺序排列的标题文字。"""
    return [html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip() for m in HEADING.finditer(html_text)]


def outline_from_html(toc: list[list], html_text: str) -> list[list]:
    """Chromium 按 HTML 标题生成书签，但个别标题的文字会被重复拼接（如「（三）」变成「（三（三））」）。
    书签与 HTML 标题一一对应，所以层级和页码沿用书签，文字一律取 HTML 标题；条数对不上时报错。"""
    heads = html_headings(html_text)
    if len(heads) != len(toc):
        raise RuntimeError(f"书签 {len(toc)} 条，HTML 标题 {len(heads)} 个，无法一一对应")
    return [[entry[0], text, *entry[2:]] for entry, text in zip(toc, heads)]
