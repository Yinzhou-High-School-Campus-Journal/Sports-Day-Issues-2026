#!/usr/bin/env python3
"""《云图试骏》排版：Markdown 稿件 → HTML → PDF。

用法：python3 排版/第一期/build.py [第一期]

流程：
1. 读取期刊目录下的稿件（卷首语、开幕式致辞、各板块导读与文章），生成 HTML；
2. 调用 Chromium（render.cjs）打印成 PDF；
3. 从 PDF 书签读出每篇的起止页，回填目录页码；量出每篇末页剩下几行，
   按 FILLS 的配置在留白处放插图（线描按实际尺寸生成，照片按尺寸裁切），再排，直到版面稳定；
4. 保存正文 PDF，拼入扉页生成完整内页，再拼封面生成预览版。
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter, ImageOps

import art

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT_DIR = HERE
IMG_DIR = OUT_DIR / "images"
sys.path.insert(0, str(HERE.parent))
from preflight import prepare_fonts, require_single_page, sources_unchanged
from pdf_metadata import document_metadata, outline_from_html, set_page_labels

PT_PER_MM = 72 / 25.4
LH = 17.35                      # 1 行
LINES = 40                      # 每页 40 行
PAGE_H = 297 * PT_PER_MM
CONTENT_TOP = 24.5 * PT_PER_MM
CONTENT_BOTTOM = PAGE_H - 27.5 * PT_PER_MM
CONTENT_W = (210 - 2 * 27.2) * PT_PER_MM
GAP = 21.0
COL_W = (CONTENT_W - GAP) / 2
# 插图对齐网格：图占整数行，图片上下各内缩到汉字字面框（基线在行框内 12.75 pt，字面框 3.51–14.01 pt）
IMG_INSET_TOP = 3.51
IMG_INSET_BOTTOM = LH - 14.01
IMG_TRIM = IMG_INSET_TOP + IMG_INSET_BOTTOM        # 6.85 pt = 行距 − 字号

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
        "front": ["0_前置/01_卷首语.md", "0_前置/03_开幕式致辞.md"],
        "sections": ["1_校运风采", "2_少年心语", "3_校园绘卷", "4_社会观察", "5_古韵风雅"],
        "cover": ["排版/封面/第一期封面.pdf", "排版/封面/第一期扉页.pdf"],
    },
}

# 个别稿件的版面参数（键为期刊目录下的相对路径）
ARTICLE_OPTIONS: dict[str, dict] = {
    # 五张照片各收到 6 行高，让全文排进一页
    "3_校园绘卷/06_忙碌的高三生的苦中寻乐……_2418_朱麒荣.md": {"max_img_lines": 6},
    # 月亮照片大面积纯黑，先裁到月亮周围
    "5_古韵风雅/02_游天妃湖赏月有感_2614_康茵子.md": {
        "crops": {"游天妃湖赏月有感_2614_康茵子_02.jpeg": (0.389, 0.106, 0.877, 0.509)},
    },
}

# 留白配图（键为期刊目录下的相对路径）。每项：
#   where: "end" 文末通栏，高度按末页剩余行数自动取整；"head" 作者行下方通栏，lines 指定行数
#   art:   art.py 里的图样名，args 为参数；或 photo: 照片路径（相对仓库根目录），crop 裁切，pos 对齐
#   grow:  True 表示放大文末原有的图组来填满，不另加图
#   min:   剩余行数少于此值时不放（默认 9）
#   max:   图最多占几行（视频截图按原比例取高，免得裁掉太多）；anchor: "bottom" 时多出的行留在图上方，图沉到页底
#   staff: 不放图，改排人员表（值为稿件目录下的文件名，每行「职务：姓名　姓名」）
FILLS: dict[str, list[dict]] = {
    # 人员表放在全刊开头：卷首语页底
    "0_前置/01_卷首语.md": [{"staff": "02_人员表.md", "anchor": "bottom"}],
    # 原片右上角有水印：裁掉顶部一成和右侧
    "0_前置/03_开幕式致辞.md": [{"photo": "资产/配图/2023运动会开幕式_航拍全景_鄞中电视台.jpg", "crop": (0, 0.1, 0.86, 1),
                       "pos": "50% 0%", "min": 5, "alt": "2023 年运动会开幕式航拍（鄞中电视台）"}],
    # 原片右上角有水印、底边有摄像机入镜，都裁掉
    "1_校运风采/00_导读.md": [{"photo": "资产/配图/2023运动会开幕式_跑道_鄞中电视台.jpg", "crop": (0, 0.1, 1, 0.835),
                          "pos": "46% 50%", "min": 1, "max": 15, "anchor": "bottom",
                          "alt": "2023 年运动会开幕式，举班牌走过跑道（鄞中电视台）"}],
    "1_校运风采/01_等一场风_2503_陈雨佳.md": [{"art": "startline", "args": {"sun": False},
                                          "alt": "起跑线与旗杆上被风吹起的绸旗"}],
    "1_校运风采/02_喧嚣未至，期待已至_2407_刘易.md": [{"art": "paper_doodle", "min": 7, "alt": "草稿纸角落里画下的小跑道"}],
    "1_校运风采/03_静待风起_2620_徐九安.md": [{"photo": "资产/配图/2023运动会开幕式_方阵_鄞中电视台.jpg",
                                           "crop": (0, 0.1, 1, 1), "pos": "50% 60%", "alt": "方阵走过跑道（鄞中电视台）"}],
    "1_校运风采/06_秋，运动，青春丰收_2503_陈思妤.md": [{"art": "ginkgo", "args": {"seed": 5}, "alt": "飘落的银杏叶"}],
    "1_校运风采/08_日光_2516_王子琼.md": [{"art": "book_leaf", "min": 7, "alt": "单词书里夹着的银杏叶"}],
    "1_校运风采/09_一圈_2403_江钡薏.md": [{"art": "oval_track", "args": {"sun": False}, "alt": "一圈跑道"}],
    "2_少年心语/00_导读.md": [{"photo": "资产/配图/2019校园_仰望树梢_鄞中电视台.jpg", "min": 1, "max": 17,
                          "anchor": "bottom", "alt": "从树下仰望天空（鄞中电视台）"}],
    "2_少年心语/01_山顶的云海日出_2610_董排彤.md": [
        {"where": "head", "lines": 20, "art": "cloudsea", "args": {"seed": 3}, "alt": "云海日出"},
        {"art": "ink_ridges", "alt": "云下的山脊，像用墨随意勾了几笔"}],
    # 航拍原片左上角有水印，裁掉
    "2_少年心语/02_雏鸟_2512_张子童.md": [{"photo": "资产/配图/校园航拍_钟楼_半岛第一飞手.jpg", "crop": (0.23, 0.02, 1, 0.55),
                                     "pos": "50% 0%", "anchor": "bottom", "alt": "钟楼（B 站用户半岛第一飞手航拍）"}],
    "2_少年心语/03_凌汐_2509_张瑜璐.md": [{"art": "seawaves", "args": {"birds": 3}, "alt": "海上落日"}],
    "3_校园绘卷/00_导读.md": [{"photo": "资产/配图/校园航拍_钟楼与长廊_半岛第一飞手.jpg", "crop": (0.23, 0.09, 1, 1),
                          "min": 1, "max": 17, "anchor": "bottom", "alt": "钟楼与红砖长廊（B 站用户半岛第一飞手航拍）"}],
    "3_校园绘卷/02_我们的「纸老虎」政治老师_2517_傅欣妍.md": [{"art": "origami_tiger", "alt": "折纸老虎"}],
    "3_校园绘卷/04_光影_2615_王莘乔.md": [{"photo": "资产/配图/2019校园_红砖拱廊_鄞中电视台.jpg", "max": 17, "anchor": "bottom",
                                      "alt": "红砖拱廊下的光与影（鄞中电视台）"}],
    "4_社会观察/00_导读.md": [{"photo": "资产/配图/2019校园_窗外_鄞中电视台.jpg", "pos": "80% 50%", "min": 1, "max": 17,
                          "anchor": "bottom", "alt": "窗外（鄞中电视台）"}],
    "4_社会观察/02_飞鸟与透明的墙_2509_梁琼文.md": [
        {"where": "head", "lines": 12, "art": "glass_bird", "alt": "玻璃采光室里的飞鸟"},
        {"art": "feather", "alt": "一片落羽"}],
    "4_社会观察/06_从「石骨铁硬」到「式微之音」_2609_王稼诺.md": [{"art": "gulou", "alt": "宁波鼓楼"}],
    "4_社会观察/08_跨越太平洋的青春力量_2602_杨日明.md": [{"art": "pingpong", "alt": "乒乓球拍、匹克球拍与太平洋"}],
    "5_古韵风雅/00_导读.md": [{"art": "moon_lake", "args": {"snow": True}, "min": 1, "alt": "湖心亭看雪"}],
    "5_古韵风雅/01_秋夜有感_2601_清兰居士.md": [{"art": "moon_bamboo", "alt": "明月、竹与雁"}],
    "5_古韵风雅/02_游天妃湖赏月有感_2614_康茵子.md": [{"grow": True, "min": 3}],
    "5_古韵风雅/06_风乎舞雩_2412_毛奕琳.md": [{"art": "willow", "min": 7, "alt": "风里的垂柳"}],
    "5_古韵风雅/08_把十八岁的信，寄给两千岁的少年_2605_邢敏谦.md": [{"art": "letter", "min": 7, "alt": "信笺、信封与毛笔"}],
    "5_古韵风雅/07_无用之用_2612_张鸣桐.md": [
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
    """转义 HTML；*西文书名* 转成斜体（西文书名不用书名号）。"""
    out = html.escape(s, quote=False)
    return re.sub(r"\*([^*\n]+)\*", r'<i lang="en">\1</i>', out)


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
    IMG_DIR.mkdir(parents=True, exist_ok=True)
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
    return Path(os.path.relpath(p, OUT_DIR)).as_posix()


def parse_staff(path: Path) -> list[tuple[str, list[str]]]:
    """人员表：每行「职务：姓名　姓名……」。"""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if "：" in line and not line.startswith("#"):
            role, names = line.split("：", 1)
            out.append((role.strip(), names.split()))
    return out


def staff_split(entries: list[tuple[str, list[str]]]) -> tuple[int, int]:
    """人员表分两栏：返回（左栏项数，整块行数 = 细线 1 行 + 较长一栏的行数）。
    每栏 20 字；职务一律撑到最长职务的字数，加冒号后剩下的字数排姓名，姓名不拆开。"""
    room = 20 - (max(len(r) for r, _ in entries) + 1)

    def n_lines(names):
        lines, cur = 1, 0
        for n in names:
            need = len(n) + (1 if cur else 0)
            if cur + need > room:
                lines, cur = lines + 1, len(n)
            else:
                cur += need
        return lines
    sizes = [n_lines(ns) for _, ns in entries]
    k = min(range(1, len(entries)), key=lambda i: (max(sum(sizes[:i]), sum(sizes[i:])), -i))
    return k, 1 + max(sum(sizes[:k]), sum(sizes[k:]))


def staff_block(entries: list[tuple[str, list[str]]], lines: int, top: str) -> str:
    """人员表：一道细线，下面两栏与正文栏对齐。职务两端撑满同一宽度，冒号、姓名上下对齐，
    姓名落在整字格上；转行时与首个姓名对齐。"""
    k, _ = staff_split(entries)
    label = max(len(r) for r, _ in entries)

    def col(items):
        return "<dl>" + "".join(
            f'<div class="e"><dt><span class="r">{html.escape(r)}</span>：</dt><dd>'
            + "　".join(f'<span class="n">{html.escape(n)}</span>' for n in ns) + "</dd></div>"
            for r, ns in items) + "</dl>"
    return (f'<section class="fill staff" style="{top}height:{lines * LH:.3f}pt;--staff-label:{label}em" '
            f'aria-label="人员表"><div class="staff-rule"></div>'
            f'<div class="staff-cols">{col(entries[:k])}{col(entries[k:])}</div></section>')


def fill_figure(piece: Piece, spec: dict, lines: int, idx: int, pad: int = 0) -> str:
    """生成一幅通栏插图的 HTML；线描按实际尺寸出 SVG，照片裁成灰度。pad：图上方再空几行（沉底用）。"""
    hgt = lines * LH
    where = spec.get("where", "end")
    cls = "fill fill-head" if where == "head" else "fill"
    top = f"margin-top:{(1 + pad) * LH:.3f}pt;" if pad else ""
    if "staff" in spec:
        return staff_block(parse_staff(piece.path.parent / spec["staff"]), lines, top)
    if "art" in spec:
        svg = art.make(spec["art"], CONTENT_W, hgt - IMG_TRIM, **spec.get("args", {}))
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
    return (f'<figure class="{cls}" style="{top}height:{hgt:.3f}pt">'
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
                    # 中文破折号留在中文里，其后的西文出处标成英文
                    inner.append(f'<p class="src">——<span class="w" lang="en">{inline(l[2:])}</span></p>')
                else:
                    inner.append(f'<span class="l"><span class="w" lang="en">{inline(l.rstrip())}</span></span>')
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
            out.append(f'<figure class="fig" style="height:{n * LH:.3f}pt">'
                       f'<img src="{rel(path)}" alt="{html.escape(b.alt)}"></figure>')
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
    natural = [a * (hgt - IMG_TRIM) for _, a, _ in items]
    scale = usable / sum(natural)
    tags = [f'<img src="{rel(p)}" alt="{html.escape(alt)}" style="width:{nw * scale:.3f}pt;flex:none">'
            for (p, _, alt), nw in zip(items, natural)]
    return f'<figure class="fig-wide" style="height:{hgt:.3f}pt">{"".join(tags)}</figure>'


def render_piece(piece: Piece, fills: dict[str, dict[int, int]],
                 pads: dict[str, dict[int, int]] | None = None) -> str:
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
        # 班级号是独立西文，单独用 Constantia
        who = (f'<span class="num">{piece.cls}</span>　{inline(piece.name)}' if piece.cls
               else inline(piece.name))
        head.append(f'<p class="author">{who}</p>')

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
    padded = (pads or {}).get(piece.pid, {})
    for i, s in enumerate(specs):
        if s.get("where", "end") == "end" and not s.get("grow") and i in sized:
            extra += fill_figure(piece, s, sized[i], i, padded.get(i, 0))
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
            it.section = re.sub(r"^\d+_", "", sec)
            if int(it.path.name.split("_")[0]) == 0:     # 00_导读.md：板块起始页
                it.kind = "opener"
        groups.append((re.sub(r"^\d+_", "", sec), items))
    for n, p in enumerate(front + [x for _, items in groups for x in items], 1):
        p.pid = f"p{n:02d}"
        p.key = p.path.relative_to(base).as_posix()
    return front, groups


def all_pieces(issue: str) -> list[Piece]:
    front, groups = load_issue(issue)
    return front + [x for _, items in groups for x in items]


def build_html(issue: str, pages: dict[str, int], fills: dict[str, dict[int, int]],
               pads: dict[str, dict[int, int]] | None = None) -> str:
    cfg = ISSUES[issue]
    front, groups = load_issue(issue)
    body = [render_piece(p, fills, pads) for p in front]
    body.append(render_toc(front, groups, pages))
    for _, items in groups:
        body.extend(render_piece(p, fills, pads) for p in items)
    return ("<!doctype html>\n<html lang=\"zh-Hans\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>{cfg['journal']} {issue}</title>\n"
            f'<link rel="stylesheet" href="{rel(HERE / "style.css")}">\n</head>\n<body>\n'
            + "\n\n".join(body) + "\n</body>\n</html>\n")


# ---------------------------------------------------------------- 输出与分析

def render_pdf(html_path: Path, pdf_path: Path) -> None:
    subprocess.run(["node", str(HERE / "render.cjs"), str(html_path), str(pdf_path)], check=True)


def piece_pages(pdf_path: Path, issue: str, html_text: str) -> tuple[dict[str, int], dict[str, tuple[int, int]]]:
    """根据 PDF 书签（每篇的 h1）确定每篇的起止页。"""
    front, groups = load_issue(issue)
    order = [(p.pid, p.title) for p in front] + [("toc", "目录")] + \
            [(x.pid, x.title) for _, items in groups for x in items]
    doc = pymupdf.open(pdf_path)
    tops = [(t, pg) for lvl, t, pg in outline_from_html(doc.get_toc(simple=True), html_text) if lvl == 1]
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


def finalize(issue: str, pdf_path: Path, html_text: str) -> tuple[Path, Path]:
    cfg = ISSUES[issue]
    cover, title_page = [ROOT / name for name in cfg["cover"]]
    require_single_page([cover, title_page])
    doc = pymupdf.open(pdf_path)
    doc.set_toc(outline_from_html(doc.get_toc(simple=False), html_text))
    doc.set_metadata(document_metadata(issue, "正文", doc.metadata.get("producer", "")))
    doc.save(pdf_path.with_suffix(".tmp.pdf"), garbage=3, deflate=True)
    doc.close()
    pdf_path.with_suffix(".tmp.pdf").replace(pdf_path)

    # 发布内页 = 后来独立制作的扉页 + 原正文；正文的纸面页码不变。
    inner_path = OUT_DIR / f"{issue}内页.pdf"
    with pymupdf.open() as out:
        with pymupdf.open(title_page) as title, pymupdf.open(pdf_path) as body:
            out.insert_pdf(title)
            out.insert_pdf(body)
            out.set_toc([[1, "扉页", 1]] + [[t[0], t[1], t[2] + 1] for t in body.get_toc()])
            out.set_metadata({**body.metadata, **document_metadata(issue, "内页", body.metadata.get("producer", ""))})
        set_page_labels(out, {1: "扉页"})
        temp = inner_path.with_suffix(".tmp.pdf")
        out.save(temp, garbage=3, deflate=True)
    temp.replace(inner_path)

    preview = OUT_DIR / f"{issue}（含封面预览）.pdf"
    with pymupdf.open() as out, pymupdf.open(cover) as cd, pymupdf.open(inner_path) as inner:
        out.insert_pdf(cd)
        out.insert_pdf(inner)
        out.set_toc([[1, "封面", 1]] + [[t[0], t[1], t[2] + 1] for t in inner.get_toc()])
        set_page_labels(out, {1: "封面", 2: "扉页"})
        out.set_metadata(document_metadata(issue, "含封面预览", inner.metadata.get("producer", "")))
        temp = preview.with_suffix(".tmp.pdf")
        out.save(temp, garbage=3, deflate=True)
    temp.replace(preview)
    return inner_path, preview


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("issue", nargs="?", default="第一期")
    args = ap.parse_args()
    issue = args.issue
    prepare_fonts()
    require_single_page([ROOT / name for name in ISSUES[issue]["cover"]])
    with sources_unchanged():
        build(issue)


def build(issue: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUT_DIR / f"{issue}.html"
    pdf_path = OUT_DIR / f"{issue}正文.pdf"
    pieces = {p.pid: p for p in all_pieces(issue)}

    pages: dict[str, int] = {}
    fills: dict[str, dict[int, int]] = {}      # pid → {配图序号: 行数}
    pads: dict[str, dict[int, int]] = {}       # pid → {配图序号: 图上方多空的行数}（anchor: bottom）
    base_len: dict[str, int] = {}              # 加文末配图前每篇的页数
    for rnd in range(1, 9):
        html_path.write_text(build_html(issue, pages, fills, pads), encoding="utf-8")
        render_pdf(html_path, pdf_path)
        starts, spans = piece_pages(pdf_path, issue, html_path.read_text(encoding="utf-8"))
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
                if "staff" in s:                     # 人员表高度按名单算，上方至少空 1 行
                    need = staff_split(parse_staff(piece.path.parent / s["staff"]))[1]
                    s = {**s, "max": need, "min": need + 1}
                if cur is None:
                    # 尚未配图：剩余行数够多才放；通栏图上方空 1 行
                    if free[pid] >= s.get("min", 9):
                        base_len[pid] = length
                        want = free[pid] - (0 if s.get("grow") else 1)
                        n = min(want, s.get("max", LINES))
                        fills.setdefault(pid, {})[i] = n
                        if s.get("anchor") == "bottom" and want > n:
                            pads.setdefault(pid, {})[i] = want - n
                        changed = True
                elif length > base_len.get(pid, length):
                    # 挤出新页：先减沉底的空行，再缩图，一次一行重排
                    if pads.get(pid, {}).get(i):
                        pads[pid][i] -= 1
                    else:
                        fills[pid][i] = cur - 1
                    changed = True
        print(f"第 {rnd} 遍：{pymupdf.open(pdf_path).page_count} 页")
        if not changed:
            break

    report = []
    for pid, (a, b) in spans.items():
        title = "目录" if pid == "toc" else pieces[pid].title
        report.append({"pid": pid, "title": title, "pages": [a + 1, b + 1], "page_no": a, "free_lines": free[pid],
                       "fills": fills.get(pid, {})})
    (OUT_DIR / f"{issue}版面.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    total = pymupdf.open(pdf_path).page_count
    inner, preview = finalize(issue, pdf_path, html_path.read_text(encoding="utf-8"))
    print(f"完成：{pdf_path.name}（{total} 页），{inner.name}（{total + 1} 页），预览：{preview.name}（{total + 2} 页）")
    for r in report:
        flag = "  ← 留白多" if r["free_lines"] >= 9 else ""
        print(f"  {r['pages'][0]:>3}–{r['pages'][1]:<3} 末页余 {r['free_lines']:>3} 行  {r['title']}{flag}")


if __name__ == "__main__":
    sys.exit(main())
