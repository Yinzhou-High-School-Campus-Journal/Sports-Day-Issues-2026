#!/usr/bin/env python3
"""《骋风逐曜》排版：Markdown 稿件 → HTML → PDF。

用法：python3 排版/第二期/build.py [第二期]

流程：
1. 读取期刊目录下的稿件（目录、人员表、各板块导读与文章、卷尾语），生成 HTML；
2. 调用 Chromium（render.cjs）打印成 PDF；
3. 从 PDF 书签读出每篇的起止页，回填目录页码；量出每篇末页剩下几行，
   按 FILLS 的配置在留白处放插图（线描按实际尺寸生成，照片按尺寸裁切），再排，直到版面稳定；
4. 写入 PDF 元数据和页码标签，另出一份页码用齐线数字的对照版；重建页码单独输出，不覆盖来源目录。
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
import fonts

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT_DIR = HERE
IMG_DIR = OUT_DIR / "images"
sys.path.insert(0, str(HERE.parent))
from preflight import check_fonts, require_single_page
from pdf_metadata import document_metadata

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

# 个别稿件的版面参数（键为期刊目录下的相对路径）
OPTIONS_2: dict[str, dict] = {
    # 诗行短、诗节多：排双栏，一页放下
    "1_红砖絮语/01_青春颂_2607_沈真一.md": {"poem_columns": 2},
    # 月亮照片大面积纯黑，先裁到月亮周围
    "4_思接千载/09_游天妃湖赏月有感_2614_康茵子.md": {
        "crops": {"游天妃湖赏月有感_2614_康茵子_02.jpeg": (0.389, 0.106, 0.877, 0.509)},
    },
}

# 留白配图（键为期刊目录下的相对路径）。每项：
#   where: "end" 文末通栏，高度按末页剩余行数自动取整；"head" 作者行下方通栏，lines 指定行数
#   art:   art.py 里的图样名，args 为参数；或 photo: 照片路径（相对仓库根目录），crop 裁切，pos 对齐
#   grow:  True 表示放大文末原有的图组来填满，不另加图
#   min:   剩余行数少于此值时不放（默认 9）
#   max:   图最多占几行（视频截图按原比例取高，免得裁掉太多）；anchor: "bottom" 时多出的行留在图上方，图沉到页底
# 第一期未刊发的五板块版（ShenZehou 分支）里画过、拍过的图，内容合适的直接沿用。
FILLS_2: dict[str, list[dict]] = {
    # 板块起始页。航拍原片左上角、开幕式原片右上角有水印，都裁掉
    "1_红砖絮语/0_导读.md": [{"photo": "资产/配图/校园航拍_钟楼_半岛第一飞手.jpg", "crop": (0.23, 0, 1, 1),
                            "pos": "50% 0%", "min": 1, "max": 17, "anchor": "bottom",
                            "alt": "钟楼（B 站用户半岛第一飞手航拍）"}],
    "2_赛道秋声/0_导读.md": [{"photo": "资产/配图/2023运动会开幕式_跑道_鄞中电视台.jpg", "crop": (0, 0.1, 1, 0.835),
                            "pos": "46% 50%", "min": 1, "max": 15, "anchor": "bottom",
                            "alt": "2023 年运动会开幕式，举班牌走过跑道（鄞中电视台）"}],
    # 笃前行没有贴题的图，导读写长，不配图
    "4_思接千载/0_导读.md": [{"art": "moon_lake", "args": {"snow": True}, "min": 1, "alt": "湖心亭看雪"}],
    # 风过鄞廊：一头一尾两张「廊」
    "1_红砖絮语/04_风过鄞廊_2505_周真真.md": [
        {"where": "head", "lines": 15, "photo": "资产/配图/2019校园_红砖拱廊_鄞中电视台.jpg", "alt": "红砖拱廊（鄞中电视台）"},
        {"photo": "资产/配图/校园航拍_钟楼与长廊_半岛第一飞手.jpg", "crop": (0.23, 0.09, 1, 1), "max": 17,
         "anchor": "bottom", "alt": "钟楼与红砖长廊（B 站用户半岛第一飞手航拍）"}],
    "1_红砖絮语/05_窗边夏_2512_黄子宸.md": [{"photo": "资产/配图/2019校园_窗外_鄞中电视台.jpg", "pos": "80% 50%",
                                          "max": 17, "anchor": "bottom", "alt": "窗外（鄞中电视台）"}],
    "1_红砖絮语/07_有风吹过_2509_邹奕晗.md": [{"photo": "资产/配图/2019校园_仰望树梢_鄞中电视台.jpg", "max": 17,
                                            "anchor": "bottom", "alt": "抬头望，风惊扰了疏柯（鄞中电视台）"}],
    # 青春颂：红砖楼与梧桐（「红砖覆上幽香，碧木点染暗黄」）
    "1_红砖絮语/01_青春颂_2607_沈真一.md": [{"photo": "资产/配图/2019校园_红砖楼与梧桐_鄞中电视台.jpg",
                                          "crop": (0, 0, 1, 0.8), "pos": "50% 35%", "alt": "红砖楼与梧桐（鄞中电视台）"}],
    # 2024 年开幕式的截图：右上角水印都裁掉。最后五十米配跑道上的同学（作者这回没报名的那场校运会），
    # 于喘息之间配看台边空着的蓝色跑道（「像一汪沉在校园角落的静海」），卷尾语配升旗
    "2_赛道秋声/01_最后五十米_2620_陈思妤.md": [{"photo": "资产/配图/2024运动会开幕式_跑道_鄞中电视台.jpg",
                                             "crop": (0, 0.417, 1, 0.878), "min": 7, "alt": "运动会上跑过跑道的同学（鄞中电视台）"}],
    "2_赛道秋声/09_于喘息之间，寻得生命的旷野_2501_潘峻昊.md": [
        {"photo": "资产/配图/2024运动会开幕式_看台与跑道_鄞中电视台.jpg", "crop": (0, 0.52, 1, 0.94), "min": 6,
         "alt": "看台边的蓝色跑道（鄞中电视台）"}],
    "卷尾语.md": [{"photo": "资产/配图/2024运动会开幕式_升旗_鄞中电视台.jpg", "crop": (0.105, 0.085, 0.895, 1),
                  "alt": "运动会开幕式升旗（鄞中电视台）"}],
    "2_赛道秋声/03_奋斗正青春，运动鄞中人_2505_沈子涵.md": [
        {"photo": "资产/配图/2023运动会开幕式_航拍全景_鄞中电视台.jpg", "crop": (0, 0, 0.86, 1), "pos": "50% 40%",
         "alt": "运动会航拍（鄞中电视台）"}],
    # 按内容画的线描
    "1_红砖絮语/06_寻猫记_2515_王艺宁.md": [{"art": "cat_sakura", "alt": "春雨里的樱花枝，树篱前的猫咪一家"}],
    "1_红砖絮语/08_余温如常_2514_王潇笑.md": [{"art": "bench", "alt": "银杏树下的空长椅，椅上一杯饮料还冒着热气"}],
    "1_红砖絮语/09_变声期_2513_高塔.md": [{"art": "lighthouse", "alt": "雨夜里的灯塔"}],
    "3_青衿问道/01_十八而立_2406_冯欣悦.md": [{"art": "desk_lamp", "alt": "深夜的书桌、台灯，墙上日历圈着生日"}],
    "3_青衿问道/07_相逢传赤心_2607_崔傲.md": [{"art": "scroll", "alt": "「天下为公」立轴"}],
    "3_青衿问道/08_赓续长征星火 续写时代华章_2618_杨嘉亿.md": [{"art": "chain_bridge", "alt": "泸定桥的铁索"}],
    "4_思接千载/02_无题_2616_严若馨.md": [{"art": "sky_birds", "alt": "飞鸟和云"}],
    "4_思接千载/04_落叶知秋_2407_汪鑫瑶.md": [{"art": "falling_leaf", "alt": "一片梧桐叶飘落"}],
    "4_思接千载/13_浙里皮影流年，月光映照归途_2506_包轩瑜.md": [{"art": "jiangnan_moon", "alt": "月光下的江南水乡"}],
    "1_红砖絮语/02_山顶的云海日出_2610_董臙彤.md": [
        {"where": "head", "lines": 20, "art": "cloudsea", "args": {"seed": 3}, "alt": "云海日出"},
        {"art": "ink_ridges", "alt": "云下的山脊，像用墨随意勾了几笔"}],
    "2_赛道秋声/06_日光_2516_王子琼.md": [{"art": "book_leaf", "min": 7, "alt": "单词书里夹着的银杏叶"}],
    "2_赛道秋声/08_一圈_2403_江钡薏.md": [{"art": "oval_track", "args": {"sun": False}, "alt": "一圈跑道"}],
    "4_思接千载/09_游天妃湖赏月有感_2614_康茵子.md": [{"grow": True, "min": 3}],
    "4_思接千载/10_风乎舞雩_2412_毛奕琳.md": [{"art": "willow", "min": 7, "alt": "风里的垂柳"}],
    "4_思接千载/11_无用之用_2612_张鸣桐.md": [
        {"where": "head", "lines": 12, "art": "old_tree", "alt": "荒径旁的老槐"},
        {"art": "mountains", "args": {"frame": True}, "alt": "卧游：墙上的一幅山水"}],
}

# 各期配置。sections 为板块目录（可带「01_」这类序号前缀，页眉和目录里去掉）；
# 板块目录里序号为 0 的稿件（如 0_导读.md）排成板块起始页。
# 内页开头：扉页（右页）、人员表（左页）、目录（右页）、空白页（左页）不印页码、不计页数，其后的第一页（右页）为第 1 页。
# Chromium 只排人员表以后的部分；扉页和凑双数的空白页在 finalize() 里拼上。
ISSUES = {
    "第二期": {
        "journal": "校运会特刊",
        "name": "骋风逐曜",             # 本期名：印在左页页眉（右页页眉为板块名）
        "front": [],                    # 目录之前的稿件：这期不放卷首语、致辞
        "sections": ["1_红砖絮语", "2_赛道秋声", "3_青衿问道", "4_思接千载"],
        # 印出来的板块名（四字，不与第一期重复）；稿件目录名与编辑部成品分类一致
        "section_names": {"1_红砖絮语": "红砖絮语", "2_赛道秋声": "赛道秋声",
                          "3_青衿问道": "青衿问道", "4_思接千载": "思接千载"},
        "back": ["卷尾语.md"],          # 全刊最后
        "title_page": "排版/封面/第二期扉页.pdf",  # 另做的扉页，拼在内页最前
        "staff": "0_前置/01_人员表.md",           # 扉页背面，在目录前（封面另做）
        "toc_class": True,              # 目录标班级
        "options": OPTIONS_2,
        "fills": FILLS_2,
    },
}
OPTIONS: dict[str, dict] = {}           # 当前这期的 options / fills，main() 里按期设定
FILLS: dict[str, list[dict]] = {}


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
    section: str = ""           # 板块名（已去掉序号前缀）；前置稿件为空
    page: str = ""              # 命名页（决定页眉），如 sec1
    key: str = ""               # 期刊目录下的相对路径，用于查配置
    kind: str = "article"       # front（目录前的稿件）/ opener（板块导读）/ article / back（卷尾语）
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
        # 篇首题记：「引文」——出处
        if not blocks and len(ch) == 1 and (m := re.match(r"^(「.+」)\s*——\s*(.+)$", first)):
            blocks.append(Block("epigraph", lines=[m.group(1), m.group(2)]))
        elif m := re.match(r"^(#{2,6})\s+(.+)$", first):
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
    # 诗里单独成段的一句（如每节后的叠句）也是诗行：全篇只有诗行和短单句时，合成一首诗
    if any(b.kind == "verse" for b in blocks) and all(
            b.kind == "verse" or (b.kind == "p" and len(b.text) <= 24) for b in blocks):
        stanzas = [s for b in blocks for s in (b.stanzas if b.kind == "verse" else [[b.text]])]
        blocks = [Block("verse", stanzas=stanzas)]
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


STAFF_NAME_EM = 7                # 人员表姓名栏宽：两个三字名加一个空格


def render_staff(issue: str) -> str:
    """人员表单占一页（扉页背面，左页；扉页在 finalize() 里拼上）。仿 V5 竖式：窄窄一栏，每行至多两个姓名，转行与首个姓名对齐；
    职务撑成同宽，冒号、姓名上下对齐。「特别致谢」紧接着排在最后一行，单位名不折行。
    整块排在版心左上角，从第一行起，基线落在行线上。"""
    cfg = ISSUES[issue]
    entries = parse_staff(ROOT / issue / cfg["staff"])
    label = max(len(r) for r, _ in entries)
    items = []
    for r, ns in entries:
        role = f'<dt><span class="r">{html.escape(r)}</span>：</dt>'
        if r.startswith("特别致谢"):
            items.append(f'<div class="e thanks">{role}<dd>{html.escape("".join(ns))}</dd></div>')
        else:
            items.append(f'<div class="e">{role}<dd>'
                         + "　".join(f'<span class="n">{html.escape(n)}</span>' for n in ns) + "</dd></div>")
    return (f'<section class="piece staff staff-page" id="staff" aria-label="人员表" '
            f'style="--staff-label:{label}em;--staff-names:{STAFF_NAME_EM}em"><dl>{"".join(items)}</dl></section>')


def fill_figure(piece: Piece, spec: dict, lines: int, idx: int, pad: int = 0) -> str:
    """生成一幅通栏插图的 HTML；线描按实际尺寸出 SVG，照片裁成灰度。pad：图上方再空几行（沉底用）。"""
    hgt = lines * LH
    where = spec.get("where", "end")
    cls = "fill fill-head" if where == "head" else "fill"
    top = f"margin-top:{(1 + pad) * LH:.3f}pt;" if pad else ""
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
    opts = OPTIONS.get(piece.key, {})
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
        elif b.kind == "epigraph":
            out.append(f'<blockquote class="epi"><p class="l">{inline(b.lines[0])}</p>'
                       f'<p class="src">——{inline(b.lines[1])}</p></blockquote>')
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
    opts = OPTIONS.get(piece.key, {})
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
                 pads: dict[str, dict[int, int]] | None = None, tops: dict[str, int] | None = None) -> str:
    if piece.kind == "opener":
        classes = ["piece", "opener", "single"]
    elif piece.kind in ("front", "back"):
        classes = ["piece", "front", "single"]
    else:
        classes = ["piece", piece.page]
    if piece.is_poem and not OPTIONS.get(piece.key, {}).get("poem_columns"):
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
    # 起始页：整组内容上下居中，上方补的空白取整行，不离开网格
    top = (tops or {}).get(piece.pid, 0)
    style = f' style="padding-top:{top * LH:.3f}pt"' if top else ""
    return (f'<article class="{" ".join(classes)}" id="{piece.pid}"{style}>\n'
            f'<header class="head">{"".join(head)}</header>\n{head_figs}'
            f'<div class="body">\n{body}\n</div>\n{extra}</article>')


def render_toc(front: list[Piece], groups: list[tuple[str, list[Piece]]], pages: dict[str, int],
               with_class: bool = False, back: list[Piece] | None = None) -> str:
    """目录：两栏；每条为 题目、（班级）作者、页码。卷尾语等排在各板块之后，隔一行。"""
    def title(t: str) -> str:
        # 长题目只在逗号、冒号、空格后断行（各段不拆开）；没有这类断点的交给 text-wrap: balance
        # 空格留在不断行的片段外面，否则浏览器不在空格处转行，整行撑出栏外
        parts = [x for x in re.split(r"(?<=[，：　 ])", t) if x]
        if len(parts) > 1 and all(len(x) <= 11 for x in parts):
            return "".join(f'<span class="nb">{inline(x.rstrip(" 　"))}</span>{x[len(x.rstrip(" 　")):]}'
                           for x in parts)
        return inline(t)

    def entry(p: Piece) -> str:
        num = pages.get(p.pid, 0)
        # 班级号是独立西文，用 Constantia；单占一格，与姓名分开，上下对齐
        cls = p.cls if with_class else ""
        return (f'<li><span class="t">{title(p.title)}</span>'
                f'<span class="c">{cls}</span>'
                f'<span class="a">{inline(p.name)}</span>'
                f'<span class="p">{num if num else "00"}</span></li>')
    parts = []
    if front:
        parts.append('<ol class="front-list">' + "".join(entry(p) for p in front) + "</ol>")
    for sec, items in groups:
        parts.append(f"<h2>{inline(sec)}</h2>")
        parts.append("<ol>" + "".join(entry(p) for p in items if p.kind == "article") + "</ol>")
    if back:
        parts.append('<ol class="back-list">' + "".join(entry(p) for p in back) + "</ol>")
    return ('<section class="piece front toc" id="toc">\n'
            '<header class="head"><h1 class="title bare">目录</h1></header>\n'
            f'<div class="list">\n{"".join(parts)}\n</div>\n</section>')


def sec_name(folder: str, cfg: dict | None = None) -> str:
    """印出来的板块名：配置里另起了名字就用它，否则是目录名去掉序号前缀（01_赴新征 → 赴新征）。"""
    return (cfg or {}).get("section_names", {}).get(folder) or re.sub(r"^\d+_", "", folder)


def num_prefix(path: Path) -> int:
    m = re.match(r"^(\d+)_", path.name)
    return int(m.group(1)) if m else 999


def load_issue(issue: str) -> tuple[list[Piece], list[tuple[str, list[Piece]]], list[Piece]]:
    """返回（目录前的稿件，[(板块名, 稿件)]，卷尾的稿件）。"""
    cfg = ISSUES[issue]
    base = ROOT / issue
    front = [parse_piece(base / f) for f in cfg["front"]]
    for p in front:
        p.kind = "front"
    groups = []
    for k, sec in enumerate(cfg["sections"], 1):
        files = sorted((base / sec).glob("*.md"), key=num_prefix)
        items = [parse_piece(f) for f in files]
        for it in items:
            it.section = sec_name(sec, cfg)
            it.page = f"sec{k}"
            if num_prefix(it.path) == 0:
                it.kind = "opener"
        groups.append((sec_name(sec, cfg), items))
    back = [parse_piece(base / f) for f in cfg.get("back", [])]
    for p in back:
        p.kind = "back"
    for n, p in enumerate(front + [x for _, items in groups for x in items] + back, 1):
        p.pid = f"p{n:02d}"
        p.key = p.path.relative_to(base).as_posix()
    return front, groups, back


def all_pieces(issue: str) -> list[Piece]:
    front, groups, back = load_issue(issue)
    return front + [x for _, items in groups for x in items] + back


HEADER_STYLE = ('font-family: "YZ FangSong Supp", "YZ FangSong", "YZ Song", serif; font-weight: 500; font-size: 9pt; '
                'vertical-align: bottom; padding-bottom: 8mm;')


def supplement_css() -> str:
    """方正恒仿宋缺的字（如「臙」）用同一字体的部件拼成补字字体（见 fonts.py），按 unicode-range 只管这几个字。"""
    faces = fonts.make_fangsong_supplement()
    chars = ", ".join(f"U+{ord(c):04X}" for c in fonts.FANGSONG_COMPOSED)
    weights = {"R": "100 450", "M": "451 1000"}
    return "".join(f'@font-face {{ font-family: "YZ FangSong Supp"; src: url("{rel(p)}") format("truetype"); '
                   f'font-weight: {weights[w]}; unicode-range: {chars}; }}\n' for w, p in faces.items())


def section_pages_css(cfg: dict) -> str:
    """每个板块一种命名页。页眉字间加全角空格：左页（偶数页）为本期名，右页（奇数页）为板块名；
    没有本期名时两边都是板块名。"""
    out = []
    name = "　".join(cfg.get("name", ""))
    for k, sec in enumerate(cfg["sections"], 1):
        label = "　".join(sec_name(sec, cfg))
        if name:
            out.append(f'@page sec{k}:left {{ @top-center {{ content: "{name}"; {HEADER_STYLE} }} }}\n'
                       f'@page sec{k}:right {{ @top-center {{ content: "{label}"; {HEADER_STYLE} }} }}')
        else:
            out.append(f'@page sec{k} {{ @top-center {{ content: "{label}"; {HEADER_STYLE} }} }}')
        out.append(f'.sec{k} {{ page: sec{k}; }}')
    return "\n".join(out)


def build_html(issue: str, pages: dict[str, int], fills: dict[str, dict[int, int]],
               pads: dict[str, dict[int, int]] | None = None, tops: dict[str, int] | None = None,
               extra_css: str = "") -> str:
    """pages 为各篇印出来的页码（目录、人员表不计页数，其后的第一页是第 1 页）。"""
    cfg = ISSUES[issue]
    front, groups, back = load_issue(issue)
    body = [render_staff(issue)] if cfg.get("staff") else []
    body += [render_piece(p, fills, pads, tops) for p in front]
    body.append(render_toc(front, groups, pages, cfg.get("toc_class", False), back))
    for _, items in groups:
        body.extend(render_piece(p, fills, pads, tops) for p in items)
    body.extend(render_piece(p, fills, pads, tops) for p in back)
    title = " ".join(x for x in (cfg["journal"], issue, cfg.get("name", "")) if x)
    return ("<!doctype html>\n<html lang=\"zh-Hans\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>{title}</title>\n"
            f'<link rel="stylesheet" href="{rel(HERE / "style.css")}">\n'
            f"<style>\n{supplement_css()}{section_pages_css(cfg)}\n{extra_css}</style>\n</head>\n<body>\n"
            + "\n\n".join(body) + "\n</body>\n</html>\n")


# ---------------------------------------------------------------- 输出与分析

def render_pdf(html_path: Path, pdf_path: Path) -> None:
    subprocess.run(["node", str(HERE / "render.cjs"), str(html_path), str(pdf_path)], check=True)


def piece_pages(pdf_path: Path, issue: str) -> tuple[dict[str, int], dict[str, tuple[int, int]]]:
    """根据 PDF 书签（每篇的 h1）确定每篇的起止页。人员表页（第 1 页）没有标题，不在书签里。"""
    front, groups, back = load_issue(issue)
    order = [(p.pid, p.title) for p in front] + [("toc", "目录")] + \
            [(x.pid, x.title) for _, items in groups for x in items] + [(p.pid, p.title) for p in back]
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
            # 水平线的包围框高度为 0，也算内容
            if y0 >= CONTENT_TOP - 2 and y1 <= CONTENT_BOTTOM + 4 and y1 >= y0 and (x1 > x0 or y1 > y0):
                bottom = max(bottom, y1)
        used = math.ceil((bottom - CONTENT_TOP) / LH - 0.3)
        out[pid] = LINES - max(used, 0)
    return out


def pdf_text(s: str) -> str:
    """PDF 文本串：UTF-16BE 加 BOM 的十六进制串，中文在各阅读器里都不乱码。"""
    return "<FEFF" + s.encode("utf-16-be").hex().upper() + ">"


def uncounted_pages(spans: dict[str, tuple[int, int]], staff: bool) -> dict[int, str]:
    """不印页码、不计页数的页：{PDF 里的第几页（从 1 数）: 页码标签}。人员表是第 1 页，目录随后。"""
    out = {1: "人员表"} if staff else {}
    out.update({n: "目录" for n in range(spans["toc"][0], spans["toc"][1] + 1)})
    return out


def printed_page(n: int, uncounted: dict[int, str]) -> int:
    """PDF 里的第 n 页印出来是第几页：前面不计页数的页不算。"""
    return n - sum(1 for u in uncounted if u < n)


def set_page_labels(doc: pymupdf.Document, uncounted: dict[int, str]) -> None:
    """PDF 页码标签，与印出来的页码一致：人员表、目录这两页的标签直接写「人员表」「目录」，不用罗马数字；
    其余页用印出来的页码。
    （PyMuPDF 的 set_page_labels 把中文前缀存成不带 BOM 的 UTF-8，有的阅读器显示乱码，所以直接写页码树。）"""
    nums, in_run = [], False
    for n in range(1, doc.page_count + 1):
        if n in uncounted:
            nums.append(f"{n - 1} <</P {pdf_text(uncounted[n])}>>")
            in_run = False
        elif not in_run:
            nums.append(f"{n - 1} <</S /D /St {printed_page(n, uncounted)}>>")
            in_run = True
    doc.xref_set_key(doc.pdf_catalog(), "PageLabels", f"<</Nums [{' '.join(nums)}]>>")


def finalize(issue: str, pdf_path: Path, uncounted: dict[int, str], note: str = "") -> tuple[dict[int, str], list[int]]:
    """拼上扉页、写入元数据和页码标签。Chromium 排好的版面不动：扉页（另做的 PDF）插在最前；
    开头不计页数的页若是奇数张，在其后补一张空白页，让第 1 页仍落在右页（页眉的左右页也就不变）。
    uncounted 为 Chromium 输出里不计页数的页；返回（最终 PDF 里不计页数的页，插入的页在最终 PDF 里的页序）。"""
    cfg = ISSUES[issue]
    doc = pymupdf.open(pdf_path)
    final, inserted = dict(uncounted), []
    if cfg.get("title_page"):
        with pymupdf.open(ROOT / cfg["title_page"]) as tp:
            doc.insert_pdf(tp, from_page=0, to_page=0, start_at=0)
        final = {1: "扉页", **{n + 1: label for n, label in uncounted.items()}}
        inserted.append(1)
    front = 0
    while front + 1 in final:                     # 开头连续的不计页数的页
        front += 1
    if front % 2:
        size = doc[front - 1].rect
        doc.new_page(pno=front, width=size.width, height=size.height)
        final = {(n + 1 if n > front else n): label for n, label in final.items()}
        final[front + 1] = "空白页"
        inserted.append(front + 1)
    # 书签：Chromium 按标题生成的书签随页面移动；前面补上扉页、人员表
    extra = [[1, final[n], n] for n in sorted(final) if final[n] in ("扉页", "人员表")]
    doc.set_toc(extra + doc.get_toc(simple=False))
    doc.set_metadata(document_metadata(issue, "内页", doc.metadata.get("producer", ""), note))
    set_page_labels(doc, final)
    doc.save(pdf_path.with_suffix(".tmp.pdf"), garbage=3, deflate=True)
    doc.close()
    pdf_path.with_suffix(".tmp.pdf").replace(pdf_path)
    return final, inserted


def final_page(n: int, inserted: list[int]) -> int:
    """Chromium 输出里的第 n 页在拼好的 PDF 里是第几页。"""
    for p in sorted(inserted):
        if p <= n:
            n += 1
    return n


# 对照版：页码（页脚、目录）不用 Constantia 默认的旧式数字，改用齐线数字
LINING_CSS = ("@page { @bottom-center { font-variant-numeric: lining-nums; } }\n"
              ".toc li .p { font-variant-numeric: lining-nums tabular-nums; }\n")


def write_build_index(issue: str, pages: dict[str, int], uncounted: dict[int, str]) -> None:
    """只输出本次重建页码，来源目录及其发行、版本导航由人工维护。"""
    cfg = ISSUES[issue]
    front, groups, back = load_issue(issue)
    names = "、".join(n for n, _ in groups)
    lead = "、".join(uncounted[n] for n in sorted(uncounted))
    out = [f"# {issue}重建页码", "",
           f"按刊登顺序排列；页码为最新一次排版印出来的页码：内页开头的{lead}不印页码、不计页数，"
           f"其后的第一页为第 1 页。板块名印作{names}（目录名与刊载板块名一致）；各板块起始页的导读在各板块目录的 `0_导读.md`，"
           f"人员表在 [`{cfg['staff']}`](<{rel(ROOT / issue / cfg['staff'])}>)。", ""]

    def line(p: Piece) -> str:
        who = f" — {p.cls} {p.name}".rstrip() if p.name else ""
        return f"[《{p.title}》](<{rel(p.path)}>){who}，第 {pages.get(p.pid, '?')} 页"
    out += [line(p) for p in front]
    for sec, items in groups:
        out += [f"### {sec}", ""]
        out += [f"{k}. {line(p)}" for k, p in enumerate([x for x in items if x.kind == "article"], 1)]
        out.append("")
    for p in back:
        out += [f"### {p.title}", "", line(p), ""]
    (OUT_DIR / f"{issue}重建页码.md").write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def main() -> None:
    global OPTIONS, FILLS, IMG_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("issue", nargs="?", default="第二期")
    args = ap.parse_args()
    issue = args.issue
    cfg = ISSUES[issue]
    check_fonts()
    require_single_page([ROOT / cfg["title_page"], HERE.parent / "封面" / "第一期封面.pdf",
                         HERE.parent / "封面" / "第二期封面.pdf"])
    OPTIONS, FILLS = cfg.get("options", {}), cfg.get("fills", {})
    IMG_DIR = OUT_DIR / "images"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUT_DIR / f"{issue}.html"
    pdf_path = OUT_DIR / f"{issue}内页.pdf"
    pieces = {p.pid: p for p in all_pieces(issue)}

    phys: dict[str, int] = {}                  # 各篇起始页（PDF 里的第几页）
    pages: dict[str, int] = {}                 # 印出来的页码：扉页、人员表、目录（及空白页）不计页数
    fills: dict[str, dict[int, int]] = {}      # pid → {配图序号: 行数}
    pads: dict[str, dict[int, int]] = {}       # pid → {配图序号: 图上方多空的行数}（anchor: bottom）
    tops: dict[str, int] = {}                  # 起始页：整组内容上方补的空行，让内容上下居中
    base_len: dict[str, int] = {}              # 加文末配图前每篇的页数
    for rnd in range(1, 9):
        html_path.write_text(build_html(issue, pages, fills, pads, tops), encoding="utf-8")
        render_pdf(html_path, pdf_path)
        starts, spans = piece_pages(pdf_path, issue)
        free = free_lines(pdf_path, spans)
        changed = starts != phys
        phys = starts
        skip = uncounted_pages(spans, bool(cfg.get("staff")))
        pages = {pid: printed_page(n, skip) for pid, n in starts.items()}
        # 没有配图的起始页：文字整组上下居中
        for pid, piece in pieces.items():
            if piece.kind == "opener" and not FILLS.get(piece.key) and pid not in tops and free[pid] > 1:
                tops[pid] = free[pid] // 2
                changed = True
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
                        n = min(want, s.get("max", LINES))
                        fills.setdefault(pid, {})[i] = n
                        if piece.kind == "opener" and want > n:
                            # 起始页：图紧跟导读，多出的空白一半放在整组上方，上下对称
                            tops[pid] = (want - n) // 2
                        elif s.get("anchor") == "bottom" and want > n:
                            pads.setdefault(pid, {})[i] = want - n
                        changed = True
                elif length > base_len.get(pid, length):
                    # 挤出新页：先减上方、沉底的空行，再缩图，一次一行重排
                    if tops.get(pid):
                        tops[pid] -= 1
                    elif pads.get(pid, {}).get(i):
                        pads[pid][i] -= 1
                    else:
                        fills[pid][i] = cur - 1
                    changed = True
        print(f"第 {rnd} 遍：{pymupdf.open(pdf_path).page_count} 页")
        if not changed:
            break

    final, inserted = finalize(issue, pdf_path, skip)
    total = pymupdf.open(pdf_path).page_count
    report = []                                # 起止页按拼好扉页、空白页后的 PDF 计
    for pid, (a, b) in spans.items():
        title = "目录" if pid == "toc" else pieces[pid].title
        report.append({"pid": pid, "title": title, "pages": [final_page(a, inserted), final_page(b, inserted)],
                       "page_no": pages.get(pid), "free_lines": free[pid], "fills": fills.get(pid, {})})
    (OUT_DIR / f"{issue}版面.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    # 对照版：只换页码数字的样式，版面不变
    alt_html = OUT_DIR / f"{issue}（齐线数字）.tmp.html"
    alt_pdf = OUT_DIR / f"{issue}内页（齐线数字）.pdf"
    alt_html.write_text(build_html(issue, pages, fills, pads, tops, LINING_CSS), encoding="utf-8")
    render_pdf(alt_html, alt_pdf)
    alt_html.unlink()
    finalize(issue, alt_pdf, skip, "（页码用齐线数字）")
    write_build_index(issue, pages, final)
    # 删掉这一版没用到的图（改名、撤稿后留下的旧图）
    used = set(re.findall(r'src="([^"]+)"', html_path.read_text(encoding="utf-8")))
    for f in IMG_DIR.rglob("*"):
        if f.is_file() and rel(f) not in used:
            f.unlink()
    # 旧版的封面预览、单页人员表不再生成
    for old in (f"{issue}（含封面预览）.pdf", f"{issue}人员表（扉页背面）.pdf", f"{issue}人员表.html"):
        (OUT_DIR / old).unlink(missing_ok=True)
    print(f"完成：{pdf_path.name}（{total} 页），对照版：{alt_pdf.name}")
    for r in report:
        flag = "  ← 留白多" if r["free_lines"] >= 9 else ""
        print(f"  {r['pages'][0]:>3}–{r['pages'][1]:<3} 末页余 {r['free_lines']:>3} 行  {r['title']}{flag}")


if __name__ == "__main__":
    sys.exit(main())
