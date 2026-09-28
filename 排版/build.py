#!/usr/bin/env python3
"""《云图试骏》排版：Markdown 稿件 → HTML → PDF。

用法：python3 排版/build.py [第一期]

流程：
1. 读取期刊目录下的稿件（卷首语、开幕式致辞、各栏目文章），生成 HTML；
2. 调用 Chromium（render.cjs）打印成 PDF；
3. 从 PDF 书签读出每篇的起始页，回填目录页码，再排一遍；
4. 写入 PDF 元数据，并另存一份拼上封面、扉页的预览版。
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
IMG_DIR = HERE / "images"

PT_PER_MM = 72 / 25.4
LH = 17.35                      # 1 行
PAGE_H = 297 * PT_PER_MM
CONTENT_TOP = 24.5 * PT_PER_MM
CONTENT_BOTTOM = PAGE_H - 27.5 * PT_PER_MM
CONTENT_W = (210 - 2 * 27.2) * PT_PER_MM
GAP = 21.0
COL_W = (CONTENT_W - GAP) / 2

SECTIONS = {                    # 栏目名 → 命名页
    "校运风采": "xiaoyun",
    "少年心语": "shaonian",
    "校园绘卷": "xiaoyuan",
    "社会观察": "shehui",
    "古韵风雅": "guyun",
}

ISSUES = {
    "第一期": {
        "journal": "云图试骏",
        "front": ["卷首语.md", "开幕式致辞.md"],
        "sections": ["校运风采", "少年心语", "校园绘卷", "社会观察", "古韵风雅"],
        "cover": ["资产/第一期封面.pdf", "资产/第一期扉页.pdf"],
    },
}

# 个别稿件的版面参数（键为稿件文件名）
ARTICLE_OPTIONS: dict[str, dict] = {
    # 五张照片各收到 6 行高，让全文排进一页
    "6_忙碌的高三生的苦中寻乐……_2418_朱麒荣.md": {"max_img_lines": 6},
    # 月亮照片大面积纯黑，先裁到月亮周围
    "2_游天妃湖赏月有感_2614_康茵子.md": {
        "crops": {"游天妃湖赏月有感_2614_康茵子_02.jpeg": (0.389, 0.106, 0.877, 0.509)},
    },
}


# ---------------------------------------------------------------- 解析稿件

@dataclass
class Block:
    kind: str                   # p / h / quote / verse / img
    text: str = ""
    level: int = 0
    lines: list[str] = field(default_factory=list)
    stanzas: list[list[str]] = field(default_factory=list)
    src: str = ""
    alt: str = ""


@dataclass
class Piece:
    path: Path
    title: str
    cls: str = ""               # 班级
    name: str = ""              # 作者
    subtitle: str = ""
    blocks: list[Block] = field(default_factory=list)
    section: str = ""           # 栏目；卷首语等为空
    pid: str = ""

    @property
    def is_poem(self) -> bool:
        return bool(self.blocks) and all(b.kind == "verse" for b in self.blocks)


def parse_piece(path: Path) -> Piece:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = text.split("\n")
    i = 0
    while not lines[i].strip():
        i += 1
    m = re.match(r"^#\s+(.+?)\s*$", lines[i])
    if not m:
        raise ValueError(f"{path}: 第一行应是 # 标题")
    piece = Piece(path=path, title=m.group(1))
    rest = lines[i + 1:]
    if "---" in rest:
        k = rest.index("---")
        head, body = rest[:k], rest[k + 1:]
    else:
        head, body = [], rest
    for line in head:
        s = line.strip()
        if not s:
            continue
        if s.startswith("——"):
            piece.subtitle = s
        elif not piece.name:
            mm = re.match(r"^(\S+)\s+(.+)$", s)
            if mm and re.fullmatch(r"\d+", mm.group(1)):
                piece.cls, piece.name = mm.group(1), mm.group(2).strip()
            else:
                piece.name = s
    piece.blocks = parse_body(body)
    return piece


def parse_body(lines: list[str]) -> list[Block]:
    chunks: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        if line.strip():
            cur.append(line)
        elif cur:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)

    blocks: list[Block] = []
    for ch in chunks:
        first = ch[0].strip()
        if m := re.match(r"^(#{2,6})\s+(.+)$", first):
            blocks.append(Block("h", text=m.group(2).strip(), level=len(m.group(1))))
        elif m := re.match(r"^!\[(.*?)\]\((.+?)\)$", first):
            blocks.append(Block("img", src=m.group(2), alt=m.group(1)))
        elif all(l.lstrip().startswith(">") for l in ch):
            qs = [re.sub(r"^\s*>\s?", "", l).rstrip() for l in ch]
            blocks.append(Block("quote", lines=qs))
        elif len(ch) > 1 and all(l.endswith("  ") for l in ch[:-1]):
            # 行末两个空格 = 硬换行：诗行
            vs = [l.strip() for l in ch]
            if blocks and blocks[-1].kind == "verse":
                blocks[-1].stanzas.append(vs)
            else:
                blocks.append(Block("verse", stanzas=[vs]))
        else:
            blocks.append(Block("p", text="".join(l.strip() for l in ch)))
    # 标题层级：文中出现的第一级 → 中标题（h2），第二级 → 小标题（h3）
    levels = sorted({b.level for b in blocks if b.kind == "h"})
    for b in blocks:
        if b.kind == "h":
            b.level = 2 + levels.index(b.level)
    return blocks


# ---------------------------------------------------------------- 文本处理

OPEN_PUNCT = "「『（《〈【〔"
CLOSE_PUNCT = "」』）》〉】〕"


def inline(s: str) -> str:
    return html.escape(s, quote=False)


def centered(s: str) -> str:
    """居中的单行标题：末尾收口括号取半宽，免得视觉偏左。"""
    out = inline(s)
    if s and s[-1] in CLOSE_PUNCT:
        out = out[:-1] + f'<span class="hw">{out[-1]}</span>'
    return out


# ---------------------------------------------------------------- 图片

def asset_path(piece: Piece, src: str) -> Path:
    return (piece.path.parent / src).resolve()


def process_image(src: Path, crop: tuple[float, float, float, float] | None = None) -> tuple[Path, int, int]:
    """转成适合黑白印刷的灰度图：自动色阶、稍提中间调（抵消网点扩大）、轻度锐化。"""
    IMG_DIR.mkdir(exist_ok=True)
    out = IMG_DIR / (src.stem + ".jpg")
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime or crop:
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        if crop:
            w, h = im.size
            im = im.crop((round(crop[0] * w), round(crop[1] * h), round(crop[2] * w), round(crop[3] * h)))
        g = im.convert("L")
        g = ImageOps.autocontrast(g, cutoff=(0.5, 0.3))
        lut = [round(255 * (v / 255) ** 0.9) for v in range(256)]
        g = g.point(lut)
        long_side = max(g.size)
        if long_side > 2000:
            g = g.resize((round(g.width * 2000 / long_side), round(g.height * 2000 / long_side)), Image.LANCZOS)
        g = g.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
        g.save(out, "JPEG", quality=90, dpi=(300, 300), optimize=True)
    with Image.open(out) as im:
        return out, im.width, im.height


# ---------------------------------------------------------------- 生成 HTML

def rel(p: Path) -> str:
    return p.relative_to(HERE).as_posix()


def render_blocks(piece: Piece) -> str:
    out: list[str] = []
    opts = ARTICLE_OPTIONS.get(piece.path.name, {})
    blocks = piece.blocks
    i = 0
    first_para = True
    while i < len(blocks):
        b = blocks[i]
        if b.kind == "p":
            cls = ""
            # 称呼语顶格（如致辞开头的「尊敬的……：」）
            if first_para and b.text.endswith("：") and len(b.text) <= 24:
                cls = ' class="noindent"'
            out.append(f"<p{cls}>{inline(b.text)}</p>")
            first_para = False
        elif b.kind == "h":
            tag = "h2" if b.level == 2 else "h3"
            out.append(f"<{tag}>{centered(b.text) if tag == 'h2' else inline(b.text)}</{tag}>")
        elif b.kind == "quote":
            inner = []
            for l in b.lines:
                if l.startswith("——"):
                    inner.append(f'<p class="src">{inline(l)}</p>')
                else:
                    inner.append(f'<span class="l">{inline(l.rstrip())}</span>')
            out.append("<blockquote>" + "".join(inner) + "</blockquote>")
        elif b.kind == "verse":
            st = "".join(
                '<p class="stanza">' + "".join(f'<span class="l">{inline(l)}</span>' for l in s) + "</p>"
                for s in b.stanzas)
            out.append(f'<div class="verse">{st}</div>')
        elif b.kind == "img":
            # 栏内插图：宽 = 栏宽，高取整行
            path, w, h = process_image(asset_path(piece, b.src))
            natural = COL_W * h / w
            n = max(4, round(natural / LH))
            n = min(n, opts.get("max_img_lines", 99))
            out.append(f'<figure class="fig"><img src="{rel(path)}" alt="{html.escape(b.alt)}" '
                       f'style="height:{n * LH:.3f}pt"></figure>')
        i += 1
    return "\n".join(out)


def split_trailing_images(piece: Piece) -> tuple[list[Block], list[Block]]:
    """文末连续的图片单独拿出来排成通栏图组。"""
    blocks = list(piece.blocks)
    tail: list[Block] = []
    while blocks and blocks[-1].kind == "img":
        tail.insert(0, blocks.pop())
    if len(tail) < 2:
        return piece.blocks, []
    return blocks, tail


def wide_figure(piece: Piece, imgs: list[Block]) -> str:
    """若干张图并排成一行，铺满版心宽度，高度取整行。"""
    opts = ARTICLE_OPTIONS.get(piece.path.name, {})
    items = []
    for b in imgs:
        crop = opts.get("crops", {}).get(Path(b.src).name)
        path, w, h = process_image(asset_path(piece, b.src), crop)
        items.append((path, w / h, b.alt))
    usable = CONTENT_W - GAP * (len(items) - 1)
    total_aspect = sum(a for _, a, _ in items)
    n = max(4, round(usable / total_aspect / LH))
    n = min(n, opts.get("max_wide_lines", 99))
    hgt = n * LH
    natural = [a * hgt for _, a, _ in items]
    scale = usable / sum(natural)
    tags = [f'<img src="{rel(p)}" alt="{html.escape(alt)}" style="width:{nw * scale:.3f}pt;height:{hgt:.3f}pt;flex:none">'
            for (p, _, alt), nw in zip(items, natural)]
    return f'<figure class="fig-wide" style="margin-top:{LH:.2f}pt">{"".join(tags)}</figure>'


def render_piece(piece: Piece) -> str:
    sec_cls = f"sec-{SECTIONS[piece.section]}" if piece.section else "front"
    classes = ["piece", sec_cls]
    if piece.is_poem:
        classes.append("poem")
    head = [f'<h1 class="title{"" if piece.name else " bare"}">{centered(piece.title)}</h1>']
    if piece.subtitle:
        head.append(f'<p class="subtitle">{centered(piece.subtitle)}</p>')
    if piece.name:
        who = f"{piece.cls}　{piece.name}" if piece.cls else piece.name
        head.append(f'<p class="author">{inline(who)}</p>')
    body_blocks, tail = split_trailing_images(piece)
    saved = piece.blocks
    piece.blocks = body_blocks
    body = render_blocks(piece)
    piece.blocks = saved
    extra = wide_figure(piece, tail) if tail else ""
    return (f'<article class="{" ".join(classes)}" id="{piece.pid}">\n'
            f'<header class="head">{"".join(head)}</header>\n'
            f'<div class="body">\n{body}\n</div>\n{extra}</article>')


def render_toc(front: list[Piece], groups: list[tuple[str, list[Piece]]], pages: dict[str, int]) -> str:
    def entry(p: Piece) -> str:
        num = pages.get(p.pid, 0)
        return (f'<li><span class="t">{inline(p.title)}</span>'
                f'<span class="a">{inline(p.name)}</span>'
                f'<span class="p">{num if num else "00"}</span></li>')
    parts = ['<ol class="front-list">' + "".join(entry(p) for p in front) + "</ol>"]
    for sec, items in groups:
        parts.append(f"<h2>{inline(sec)}</h2>")
        parts.append("<ol>" + "".join(entry(p) for p in items) + "</ol>")
    return ('<section class="piece front toc" id="toc">\n'
            '<header class="head"><h1 class="title bare">目录</h1></header>\n'
            f'<div class="list">\n{"".join(parts)}\n</div>\n</section>')


def load_issue(issue: str) -> tuple[list[Piece], list[tuple[str, list[Piece]]]]:
    cfg = ISSUES[issue]
    base = ROOT / issue
    front = [parse_piece(base / f) for f in cfg["front"]]
    groups = []
    for sec in cfg["sections"]:
        files = sorted((base / sec).glob("*.md"), key=lambda p: int(p.name.split("_")[0]))
        items = [parse_piece(f) for f in files]
        for it in items:
            it.section = sec
        groups.append((sec, items))
    n = 0
    for p in front + [x for _, items in groups for x in items]:
        n += 1
        p.pid = f"p{n:02d}"
    return front, groups


def build_html(issue: str, pages: dict[str, int]) -> str:
    cfg = ISSUES[issue]
    front, groups = load_issue(issue)
    body = [render_piece(p) for p in front]
    body.append(render_toc(front, groups, pages))
    for _, items in groups:
        body.extend(render_piece(p) for p in items)
    return ("<!doctype html>\n<html lang=\"zh-Hans\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>{cfg['journal']} {issue}</title>\n"
            '<link rel="stylesheet" href="style.css">\n</head>\n<body>\n'
            + "\n\n".join(body) + "\n</body>\n</html>\n")


# ---------------------------------------------------------------- 输出与分析

def render_pdf(html_path: Path, pdf_path: Path) -> None:
    subprocess.run(["node", str(HERE / "render.cjs"), str(html_path), str(pdf_path)], check=True)


def piece_pages(pdf_path: Path, issue: str) -> tuple[dict[str, int], dict[str, tuple[int, int]]]:
    """根据 PDF 书签（每篇的 h1）确定每篇的起止页。"""
    front, groups = load_issue(issue)
    order = front + [{"pid": "toc", "title": "目录"}] + [x for _, items in groups for x in items]
    doc = pymupdf.open(pdf_path)
    tops = [(t, pg) for lvl, t, pg in doc.get_toc(simple=True) if lvl == 1]
    starts: dict[str, int] = {}
    j = 0
    for p in order:
        title = p["title"] if isinstance(p, dict) else p.title
        pid = p["pid"] if isinstance(p, dict) else p.pid
        while j < len(tops) and tops[j][0].strip() != title.strip():
            j += 1
        if j == len(tops):
            raise RuntimeError(f"书签里找不到《{title}》")
        starts[pid] = tops[j][1]
        j += 1
    pids = list(starts)
    spans = {}
    for k, pid in enumerate(pids):
        end = starts[pids[k + 1]] - 1 if k + 1 < len(pids) else doc.page_count
        spans[pid] = (starts[pid], end)
    return starts, spans


def last_page_fill(pdf_path: Path, spans: dict[str, tuple[int, int]]) -> dict[str, float]:
    """每篇末页正文底边到版心底边的剩余高度（pt）。"""
    doc = pymupdf.open(pdf_path)
    free = {}
    for pid, (_, end) in spans.items():
        page = doc[end - 1]
        bottom = CONTENT_TOP
        for b in page.get_text("dict")["blocks"]:
            x0, y0, x1, y1 = b["bbox"]
            if y0 >= CONTENT_TOP - 2 and y1 <= CONTENT_BOTTOM + 4:
                bottom = max(bottom, y1)
        free[pid] = CONTENT_BOTTOM - bottom
    return free


def finalize(issue: str, pdf_path: Path) -> Path:
    cfg = ISSUES[issue]
    doc = pymupdf.open(pdf_path)
    doc.set_metadata({
        "title": f"{cfg['journal']} {issue} 内页",
        "author": "鄞州中学媒体部",
        "subject": "鄞州中学第四十四届暨鄞州蓝青高级中学第二十九届运动会校刊",
        "creator": "排版/build.py（HTML → Chromium）",
        "producer": doc.metadata.get("producer", ""),
    })
    doc.save(pdf_path.with_suffix(".tmp.pdf"), garbage=3, deflate=True)
    doc.close()
    pdf_path.with_suffix(".tmp.pdf").replace(pdf_path)

    # 拼上封面和扉页的预览版
    preview = HERE / f"{issue}（含封面预览）.pdf"
    out = pymupdf.open()
    offset = 0
    for c in cfg.get("cover", []):
        cp = ROOT / c
        if cp.exists():
            with pymupdf.open(cp) as cd:
                out.insert_pdf(cd)
                offset += cd.page_count
    with pymupdf.open(pdf_path) as inner:
        toc = inner.get_toc(simple=False)
        out.insert_pdf(inner)
    out.set_toc([[t[0], t[1], t[2] + offset] for t in toc])
    out.set_metadata({"title": f"{cfg['journal']} {issue}（含封面预览）", "author": "鄞州中学媒体部"})
    out.save(preview, garbage=3, deflate=True)
    return preview


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("issue", nargs="?", default="第一期")
    args = ap.parse_args()
    issue = args.issue
    html_path = HERE / f"{issue}.html"
    pdf_path = HERE / f"{issue}内页.pdf"

    # 第一遍：目录页码先占位
    html_path.write_text(build_html(issue, {}), encoding="utf-8")
    render_pdf(html_path, pdf_path)
    starts, spans = piece_pages(pdf_path, issue)

    # 第二遍：回填目录页码
    html_path.write_text(build_html(issue, starts), encoding="utf-8")
    render_pdf(html_path, pdf_path)
    starts2, spans2 = piece_pages(pdf_path, issue)
    if starts2 != starts:
        print("目录回填后页码有变动，再排一遍")
        html_path.write_text(build_html(issue, starts2), encoding="utf-8")
        render_pdf(html_path, pdf_path)
        starts2, spans2 = piece_pages(pdf_path, issue)

    free = last_page_fill(pdf_path, spans2)
    front, groups = load_issue(issue)
    names = {p.pid: p.title for p in front + [x for _, it in groups for x in it]}
    names["toc"] = "目录"
    report = []
    for pid, (a, b) in spans2.items():
        report.append({"pid": pid, "title": names[pid], "pages": [a, b], "free_pt": round(free[pid], 1),
                       "free_lines": round(free[pid] / LH, 1)})
    (HERE / f"{issue}版面.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    total = pymupdf.open(pdf_path).page_count
    preview = finalize(issue, pdf_path)
    print(f"完成：{pdf_path.name}（{total} 页），预览：{preview.name}")
    for r in report:
        flag = "  ← 留白多" if r["free_lines"] > 12 else ""
        print(f"  {r['pages'][0]:>3}–{r['pages'][1]:<3} 末页余 {r['free_lines']:>5} 行  {r['title']}{flag}")


if __name__ == "__main__":
    sys.exit(main())
