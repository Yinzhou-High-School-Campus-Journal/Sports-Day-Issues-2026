#!/usr/bin/env python3
"""《云图试骏》排版：Markdown 稿件 → HTML → PDF。

用法：python3 排版/build.py [第一期]

流程：
1. 读取期刊目录下的稿件（卷首语、开幕式致辞、各板块导读与文章），生成 HTML；
2. 调用 Chromium（render.cjs）打印成 PDF；
3. 从 PDF 书签读出每篇的起止页，回填目录页码；量出每篇末页剩下几行，
   按 FILLS 的配置在留白处放插图（线描按实际尺寸生成，照片按尺寸裁切），再排，直到版面稳定；
4. 写入 PDF 元数据，并另存一份拼上封面、扉页的预览版。
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter, ImageOps

import art

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
IMG_DIR = HERE / "images"

PT_PER_MM = 72 / 25.4
LH = 17.35                      # 1 行
LINES = 40                      # 每页 40 行
PAGE_H = 297 * PT_PER_MM
CONTENT_TOP = 24.5 * PT_PER_MM
CONTENT_BOTTOM = PAGE_H - 27.5 * PT_PER_MM
CONTENT_W = (210 - 2 * 27.2) * PT_PER_MM
GAP = 21.0
COL_W = (CONTENT_W - GAP) / 2

SECTIONS = {                    # 板块名 → 命名页（页眉）
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

# 个别稿件的版面参数（键为期刊目录下的相对路径）
ARTICLE_OPTIONS: dict[str, dict] = {
    # 五张照片各收到 6 行高，让全文排进一页
    "校园绘卷/6_忙碌的高三生的苦中寻乐……_2418_朱麒荣.md": {"max_img_lines": 6},
    # 月亮照片大面积纯黑，先裁到月亮周围
    "古韵风雅/2_游天妃湖赏月有感_2614_康茵子.md": {
        "crops": {"游天妃湖赏月有感_2614_康茵子_02.jpeg": (0.389, 0.106, 0.877, 0.509)},
    },
}

# 留白配图（键为期刊目录下的相对路径）。每项：
#   where: "end" 文末通栏，高度按末页剩余行数自动取整；"head" 作者行下方通栏，lines 指定行数
#   art:   art.py 里的图样名，args 为参数；或 photo: 照片路径（相对仓库根目录），crop 裁切，pos 对齐
#   grow:  True 表示放大文末原有的图组来填满，不另加图
#   min:   剩余行数少于此值时不放（默认 9）
FILLS: dict[str, list[dict]] = {
    # 卷首语写亚运羽毛球女团夺冠、校园银杏
    "卷首语.md": [{"art": "shuttle", "min": 5, "alt": "羽毛球拍与飞行的羽毛球，风中的银杏叶"}],
    "开幕式致辞.md": [{"photo": "资产/配图/2023运动会开幕式_航拍全景_鄞中电视台.jpg", "crop": (0, 0, 0.86, 1),
                       "pos": "50% 0%", "min": 5, "alt": "2023 年运动会开幕式航拍（鄞中电视台）"}],
    "校运风采/0_导读.md": [{"art": "track", "args": {"seed": 41}, "min": 1, "alt": "伸向远方的跑道"}],
    "校运风采/1_等一场风_2503_陈雨佳.md": [{"art": "startline", "alt": "黄昏的起跑线与旗杆上的绸旗"}],
    "校运风采/2_喧嚣未至，期待已至_2407_刘易.md": [{"art": "paper_doodle", "min": 7, "alt": "草稿纸角落里画下的小跑道"}],
    "校运风采/3_静待风起_2620_徐九安.md": [{"photo": "资产/配图/2023运动会开幕式_方阵_鄞中电视台.jpg",
                                           "crop": (0, 0.1, 1, 1), "pos": "50% 60%", "alt": "方阵走过跑道（鄞中电视台）"}],
    "校运风采/6_秋，运动，青春丰收_2503_陈思妤.md": [{"art": "ginkgo", "args": {"seed": 5}, "alt": "飘落的银杏叶"}],
    "校运风采/8_日光_2516_王子琼.md": [{"art": "book_leaf", "min": 7, "alt": "单词书里夹着的银杏叶"}],
    "校运风采/9_一圈_2403_江钡薏.md": [{"art": "oval_track", "alt": "一圈跑道"}],
    "少年心语/0_导读.md": [{"art": "mountains", "args": {"mist": True, "birds_n": 2, "horizon": 0.3, "seed": 7},
                          "min": 1, "alt": "雾中群山"}],
    "少年心语/1_山顶的云海日出_2610_董排彤.md": [
        {"where": "head", "lines": 13, "art": "cloudsea", "args": {"seed": 3}, "alt": "云海日出"},
        {"art": "mountains", "args": {"sun": True, "path": True}, "alt": "晨光里的下山路"}],
    "少年心语/2_雏鸟_2512_张子童.md": [{"art": "tower", "args": {"birds_n": 7, "wall": True}, "alt": "钟楼、红墙与雏鸟"}],
    "少年心语/3_凌汐_2509_张瑜璐.md": [{"art": "seawaves", "args": {"birds": 3}, "alt": "海上落日"}],
    "校园绘卷/0_导读.md": [{"art": "tower", "args": {"campus": True, "leaves": 7, "seed": 11}, "min": 1,
                          "alt": "钟楼、教学楼与银杏叶"}],
    "校园绘卷/2_我们的「纸老虎」政治老师_2517_傅欣妍.md": [{"art": "origami_tiger", "alt": "折纸老虎"}],
    "校园绘卷/4_光影_2615_王莘乔.md": [{"art": "tower", "args": {"sun": True, "cat": True, "night": True},
                                      "alt": "黄昏的钟楼与草地上的猫"}],
    "社会观察/0_导读.md": [{"art": "window_view", "min": 1, "alt": "推开的窗"}],
    "社会观察/2_飞鸟与透明的墙_2509_梁琼文.md": [
        {"where": "head", "lines": 12, "art": "glass_bird", "alt": "玻璃采光室里的飞鸟"},
        {"art": "feather", "alt": "一片落羽"}],
    "社会观察/6_从「石骨铁硬」到「式微之音」_2609_王稼诺.md": [{"art": "gulou", "alt": "宁波鼓楼"}],
    "社会观察/8_跨越太平洋的青春力量_2602_杨日明.md": [{"art": "pingpong", "alt": "乒乓球拍、匹克球拍与太平洋"}],
    "古韵风雅/0_导读.md": [{"art": "moon_lake", "args": {"snow": True}, "min": 1, "alt": "湖心亭看雪"}],
    "古韵风雅/1_秋夜有感_2601_清兰居士.md": [{"art": "moon_bamboo", "alt": "明月、竹与雁"}],
    "古韵风雅/2_游天妃湖赏月有感_2614_康茵子.md": [{"grow": True, "min": 3}],
    "古韵风雅/6_风乎舞雩_2412_毛奕琳.md": [{"art": "mountains", "args": {"sun": True, "seed": 13, "horizon": 0.3},
                                            "min": 7, "alt": "泰山日出"}],
    "古韵风雅/8_把十八岁的信，寄给两千岁的少年_2605_邢敏谦.md": [{"art": "letter", "min": 7, "alt": "信笺、信封与毛笔"}],
    "古韵风雅/7_无用之用_2612_张鸣桐.md": [
        {"where": "head", "lines": 12, "art": "old_tree", "alt": "荒径旁的老槐"},
        {"art": "mountains", "args": {"frame": True}, "alt": "卧游：墙上的一幅山水"}],
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
    section: str = ""           # 板块；卷首语等为空
    key: str = ""               # 期刊目录下的相对路径，用于查配置
    kind: str = "article"       # front（卷首语、致辞）/ opener（板块导读）/ article
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


def to_print_gray(im: Image.Image, mix: tuple[float, float, float] | None = None) -> Image.Image:
    """转成适合黑白印刷的灰度：可自定通道配比，自动色阶，稍提中间调抵消网点扩大，轻度锐化。"""
    im = im.convert("RGB")
    if mix:
        r, g, b = mix
        gray = im.convert("L", (r, g, b, 0))
    else:
        gray = im.convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=(0.5, 0.3))
    gray = gray.point([round(255 * (v / 255) ** 0.9) for v in range(256)])
    return gray


def process_image(src: Path, crop: tuple[float, float, float, float] | None = None,
                  out_name: str | None = None, mix=None, max_side: int = 2000) -> tuple[Path, int, int]:
    IMG_DIR.mkdir(exist_ok=True)
    out = IMG_DIR / (out_name or (src.stem + ".jpg"))
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime or crop or mix:
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        if crop:
            w, h = im.size
            im = im.crop((round(crop[0] * w), round(crop[1] * h), round(crop[2] * w), round(crop[3] * h)))
        g = to_print_gray(im, mix)
        long_side = max(g.size)
        if long_side > max_side:
            g = g.resize((round(g.width * max_side / long_side), round(g.height * max_side / long_side)),
                         Image.LANCZOS)
        g = g.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
        g.save(out, "JPEG", quality=90, dpi=(300, 300), optimize=True)
    with Image.open(out) as im:
        return out, im.width, im.height


def rel(p: Path) -> str:
    return p.relative_to(HERE).as_posix()


def fill_figure(piece: Piece, spec: dict, lines: int, idx: int) -> str:
    """生成一幅通栏插图的 HTML；线描按实际尺寸出 SVG，照片裁成灰度。"""
    hgt = lines * LH
    where = spec.get("where", "end")
    cls = "fill fill-head" if where == "head" else "fill"
    if "art" in spec:
        svg = art.make(spec["art"], CONTENT_W, hgt, **spec.get("args", {}))
        out = IMG_DIR / "art" / f"{piece.key.replace('/', '_')[:-3]}-{where}{idx}.svg"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(svg, encoding="utf-8")
        src, alt = out, spec.get("alt", "插图")
    else:
        photo = ROOT / spec["photo"]
        src, _, _ = process_image(photo, spec.get("crop"), out_name=f"fill/{piece.key.replace('/', '_')[:-3]}-{where}{idx}.jpg",
                                  mix=spec.get("mix"))
        alt = spec.get("alt", "照片")
    pos = spec.get("pos", "50% 50%")
    return (f'<figure class="{cls}" style="height:{hgt:.3f}pt">'
            f'<img src="{rel(src)}" alt="{html.escape(alt)}" style="object-position:{pos}"></figure>')


# ---------------------------------------------------------------- 生成 HTML

def render_blocks(piece: Piece) -> str:
    out: list[str] = []
    opts = ARTICLE_OPTIONS.get(piece.key, {})
    first_para = True
    for b in piece.blocks:
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
            n = max(4, round(COL_W * h / w / LH))
            n = min(n, opts.get("max_img_lines", 99))
            out.append(f'<figure class="fig"><img src="{rel(path)}" alt="{html.escape(b.alt)}" '
                       f'style="height:{n * LH:.3f}pt"></figure>')
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


def wide_figure(piece: Piece, imgs: list[Block], extra_lines: int = 0) -> str:
    """若干张图并排成一行，铺满版心宽度，高度取整行；extra_lines 用来放大填满留白。"""
    opts = ARTICLE_OPTIONS.get(piece.key, {})
    items = []
    for b in imgs:
        crop = opts.get("crops", {}).get(Path(b.src).name)
        path, w, h = process_image(asset_path(piece, b.src), crop)
        items.append((path, w / h, b.alt))
    usable = CONTENT_W - GAP * (len(items) - 1)
    total_aspect = sum(a for _, a, _ in items)
    n = max(4, round(usable / total_aspect / LH)) + extra_lines
    hgt = n * LH
    natural = [a * hgt for _, a, _ in items]
    scale = usable / sum(natural)
    tags = [f'<img src="{rel(p)}" alt="{html.escape(alt)}" style="width:{nw * scale:.3f}pt;height:{hgt:.3f}pt;flex:none">'
            for (p, _, alt), nw in zip(items, natural)]
    return f'<figure class="fig-wide">{"".join(tags)}</figure>'


def render_piece(piece: Piece, fills: dict[str, dict[int, int]]) -> str:
    if piece.kind == "opener":
        classes = ["piece", "opener", "single"]
    elif piece.kind == "front":
        classes = ["piece", "front", "single"]
    else:
        classes = ["piece", f"sec-{SECTIONS[piece.section]}"]
    if piece.is_poem:
        classes.append("poem")
    head = [f'<h1 class="title{"" if piece.name else " bare"}">{centered(piece.title)}</h1>']
    if piece.subtitle:
        head.append(f'<p class="subtitle">{centered(piece.subtitle)}</p>')
    if piece.name:
        who = f"{piece.cls}　{piece.name}" if piece.cls else piece.name
        head.append(f'<p class="author">{inline(who)}</p>')

    specs = FILLS.get(piece.key, [])
    sized = fills.get(piece.pid, {})
    head_figs = "".join(fill_figure(piece, s, s["lines"], i)
                        for i, s in enumerate(specs) if s.get("where") == "head")

    body_blocks, tail = split_trailing_images(piece)
    saved = piece.blocks
    piece.blocks = body_blocks
    body = render_blocks(piece)
    piece.blocks = saved

    extra = ""
    grow = next((i for i, s in enumerate(specs) if s.get("grow")), None)
    if tail:
        extra = wide_figure(piece, tail, sized.get(grow, 0) if grow is not None else 0)
    for i, s in enumerate(specs):
        if s.get("where", "end") == "end" and not s.get("grow") and i in sized:
            extra += fill_figure(piece, s, sized[i], i)
    return (f'<article class="{" ".join(classes)}" id="{piece.pid}">\n'
            f'<header class="head">{"".join(head)}</header>\n{head_figs}'
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
        parts.append("<ol>" + "".join(entry(p) for p in items if p.kind == "article") + "</ol>")
    return ('<section class="piece front toc" id="toc">\n'
            '<header class="head"><h1 class="title bare">目录</h1></header>\n'
            f'<div class="list">\n{"".join(parts)}\n</div>\n</section>')


def load_issue(issue: str) -> tuple[list[Piece], list[tuple[str, list[Piece]]]]:
    cfg = ISSUES[issue]
    base = ROOT / issue
    front = [parse_piece(base / f) for f in cfg["front"]]
    for p in front:
        p.kind = "front"
    groups = []
    for sec in cfg["sections"]:
        files = sorted((base / sec).glob("*.md"), key=lambda p: int(p.name.split("_")[0]))
        items = [parse_piece(f) for f in files]
        for it in items:
            it.section = sec
            if it.path.name.startswith("0_"):
                it.kind = "opener"
        groups.append((sec, items))
    for n, p in enumerate(front + [x for _, items in groups for x in items], 1):
        p.pid = f"p{n:02d}"
        p.key = p.path.relative_to(base).as_posix()
    return front, groups


def all_pieces(issue: str) -> list[Piece]:
    front, groups = load_issue(issue)
    return front + [x for _, items in groups for x in items]


def build_html(issue: str, pages: dict[str, int], fills: dict[str, dict[int, int]]) -> str:
    cfg = ISSUES[issue]
    front, groups = load_issue(issue)
    body = [render_piece(p, fills) for p in front]
    body.append(render_toc(front, groups, pages))
    for _, items in groups:
        body.extend(render_piece(p, fills) for p in items)
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
    order = [(p.pid, p.title) for p in front] + [("toc", "目录")] + \
            [(x.pid, x.title) for _, items in groups for x in items]
    doc = pymupdf.open(pdf_path)
    tops = [(t, pg) for lvl, t, pg in doc.get_toc(simple=True) if lvl == 1]
    starts: dict[str, int] = {}
    j = 0
    for pid, title in order:
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


def free_lines(pdf_path: Path, spans: dict[str, tuple[int, int]]) -> dict[str, int]:
    """每篇末页最下面一行内容以下还空着几行（按 40 行网格计）。"""
    doc = pymupdf.open(pdf_path)
    out = {}
    for pid, (_, end) in spans.items():
        page = doc[end - 1]
        boxes = [b["bbox"] for b in page.get_text("dict")["blocks"]]
        boxes += [i["bbox"] for i in page.get_image_info()]
        # 只算有描边或非白填充的图形（白色背景、白色遮挡块不算内容）
        boxes += [tuple(d["rect"]) for d in page.get_drawings()
                  if "s" in d["type"] or (d.get("fill") and min(d["fill"]) < 0.95)]
        bottom = CONTENT_TOP
        for x0, y0, x1, y1 in boxes:
            if y0 >= CONTENT_TOP - 2 and y1 <= CONTENT_BOTTOM + 4 and y1 > y0:
                bottom = max(bottom, y1)
        used = math.ceil((bottom - CONTENT_TOP) / LH - 0.3)
        out[pid] = LINES - max(used, 0)
    return out


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
    pieces = {p.pid: p for p in all_pieces(issue)}

    pages: dict[str, int] = {}
    fills: dict[str, dict[int, int]] = {}      # pid → {配图序号: 行数}
    base_len: dict[str, int] = {}              # 加文末配图前每篇的页数
    for rnd in range(1, 9):
        html_path.write_text(build_html(issue, pages, fills), encoding="utf-8")
        render_pdf(html_path, pdf_path)
        starts, spans = piece_pages(pdf_path, issue)
        free = free_lines(pdf_path, spans)
        changed = starts != pages
        pages = starts
        for pid, piece in pieces.items():
            specs = FILLS.get(piece.key, [])
            length = spans[pid][1] - spans[pid][0]
            for i, s in enumerate(specs):
                if s.get("where", "end") != "end":
                    continue
                cur = fills.get(pid, {}).get(i)
                if cur is None:
                    # 尚未配图：剩余行数够多才放；通栏图上方空 1 行
                    if free[pid] >= s.get("min", 9):
                        base_len[pid] = length
                        want = free[pid] - (0 if s.get("grow") else 1)
                        fills.setdefault(pid, {})[i] = min(want, s.get("max", LINES))
                        changed = True
                elif length > base_len.get(pid, length):
                    fills[pid][i] = cur - 1          # 挤出新页：缩一行重排
                    changed = True
        print(f"第 {rnd} 遍：{pymupdf.open(pdf_path).page_count} 页")
        if not changed:
            break

    report = []
    for pid, (a, b) in spans.items():
        title = "目录" if pid == "toc" else pieces[pid].title
        report.append({"pid": pid, "title": title, "pages": [a, b], "free_lines": free[pid],
                       "fills": fills.get(pid, {})})
    (HERE / f"{issue}版面.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    total = pymupdf.open(pdf_path).page_count
    preview = finalize(issue, pdf_path)
    print(f"完成：{pdf_path.name}（{total} 页），预览：{preview.name}")
    for r in report:
        flag = "  ← 留白多" if r["free_lines"] >= 9 else ""
        print(f"  {r['pages'][0]:>3}–{r['pages'][1]:<3} 末页余 {r['free_lines']:>3} 行  {r['title']}{flag}")


if __name__ == "__main__":
    sys.exit(main())
