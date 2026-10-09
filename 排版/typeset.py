"""两期内页共用的排版程序：稿件解析、HTML 片段、配图、版面测量与留白配图。
各期的 build.py 只放本期的配置、目录、人员表、页码与拼页。"""
from __future__ import annotations

import html
import math
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import pymupdf
from PIL import Image, ImageFilter, ImageOps

import art
from pdf_metadata import outline_from_html

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

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


# ---------------------------------------------------------------- 解析稿件

@dataclass
class Block:
    kind: str                   # p / h / quote / epigraph / verse / img
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
    section: str = ""           # 板块名（已去掉序号前缀）；前置、后置稿件为空
    page: str = ""              # 正文用的命名页 class，决定页眉
    key: str = ""               # 期刊目录下的相对路径，用于查配置
    kind: str = "article"       # front（目录前的稿件）/ opener（板块导读）/ article / back（卷尾语）
    pid: str = ""

    @property
    def is_poem(self) -> bool:
        return bool(self.blocks) and all(b.kind == "verse" for b in self.blocks)


HEADING = re.compile(r"^(#{2,6})\s+(.+)$")
IMAGE = re.compile(r"^!\[(.*?)\]\((.+?)\)$")


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
    # 空行分段；标题、图片各占一段，前后没空行也不会并进相邻的段落
    chunks: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or HEADING.match(s) or IMAGE.match(s):
            if cur:
                chunks.append(cur)
            cur = [line] if s else []
            if s:
                chunks.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        chunks.append(cur)

    blocks: list[Block] = []
    for ch in chunks:
        first = ch[0].strip()
        # 篇首题记：「引文」——出处
        if not blocks and len(ch) == 1 and (m := re.match(r"^(「.+」)\s*——\s*(.+)$", first)):
            blocks.append(Block("epigraph", lines=[m.group(1), m.group(2)]))
        elif m := HEADING.match(first):
            blocks.append(Block("h", text=m.group(2).strip(), level=len(m.group(1))))
        elif m := IMAGE.match(first):
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


def parse_staff(path: Path) -> list[tuple[str, list[str]]]:
    """人员表：每行「职务：姓名　姓名……」。"""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if "：" in line and not line.startswith("#"):
            role, names = line.split("：", 1)
            out.append((role.strip(), names.split()))
    return out


def num_prefix(path: Path) -> int:
    m = re.match(r"^(\d+)_", path.name)
    return int(m.group(1)) if m else 999


def load_issue(issue: str, cfg: dict) -> tuple[list[Piece], list[tuple[str, list[Piece]]], list[Piece]]:
    """返回（目录前的稿件，[(板块名, 稿件)]，卷尾的稿件）。板块目录名去掉序号前缀即印出的板块名；
    序号为 0 的稿件（00_导读.md）排成板块起始页。"""
    base = ROOT / issue
    front = [parse_piece(base / f) for f in cfg["front"]]
    for p in front:
        p.kind = "front"
    groups = []
    for k, sec in enumerate(cfg["sections"], 1):
        name = re.sub(r"^\d+_", "", sec)
        items = [parse_piece(f) for f in sorted((base / sec).glob("*.md"), key=num_prefix)]
        for it in items:
            it.section = name
            it.page = cfg.get("page_classes", {}).get(name, f"sec{k}")
            if num_prefix(it.path) == 0:
                it.kind = "opener"
        groups.append((name, items))
    back = [parse_piece(base / f) for f in cfg.get("back", [])]
    for p in back:
        p.kind = "back"
    for n, p in enumerate(front + [x for _, items in groups for x in items] + back, 1):
        p.pid = f"p{n:02d}"
        p.key = p.path.relative_to(base).as_posix()
    return front, groups, back


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


# ---------------------------------------------------------------- 输出与分析

def render_pdf(html_path: Path, pdf_path: Path) -> None:
    subprocess.run(["node", str(HERE / "render.cjs"), str(html_path), str(pdf_path)], check=True)


def piece_pages(pdf_path: Path, front: list[Piece], groups: list[tuple[str, list[Piece]]], back: list[Piece],
                html_text: str) -> tuple[dict[str, int], dict[str, tuple[int, int]]]:
    """根据 PDF 书签（每篇的 h1）确定每篇的起止页（Chromium 输出里的第几页）。"""
    order = [(p.pid, p.title) for p in front] + [("toc", "目录")] + \
            [(x.pid, x.title) for _, items in groups for x in items] + [(p.pid, p.title) for p in back]
    with pymupdf.open(pdf_path) as doc:
        tops = [(t, pg) for lvl, t, pg in outline_from_html(doc.get_toc(simple=True), html_text) if lvl == 1]
        count = doc.page_count
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
        end = starts[pids[k + 1]] - 1 if k + 1 < len(pids) else count
        spans[pid] = (starts[pid], end)
    return starts, spans


def free_lines(pdf_path: Path, spans: dict[str, tuple[int, int]]) -> dict[str, int]:
    """每篇末页最下面一行内容以下还空着几行（按 40 行网格计）。"""
    out = {}
    with pymupdf.open(pdf_path) as doc:
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


def page_count(pdf_path: Path) -> int:
    with pymupdf.open(pdf_path) as doc:
        return doc.page_count


# ---------------------------------------------------------------- 一期的配图与 HTML

class Book:
    """一期内页的输出目录、个别稿件的版面参数（options）、留白配图（fills），以及本次构建已生成的图。

    fills 每项：
      where: "end" 文末通栏，高度按末页剩余行数自动取整；"head" 作者行下方通栏，lines 指定行数
      art:   art.py 里的图样名，args 为参数；或 photo: 照片路径（相对仓库根目录），crop 裁切，pos 对齐
      grow:  True 表示放大文末原有的图组来填满，不另加图
      min:   剩余行数少于此值时不放（默认 9）
      max:   图最多占几行（视频截图按原比例取高，免得裁掉太多）；anchor: "bottom" 时多出的行留在图上方，图沉到页底
    """

    def __init__(self, out_dir: Path, options: dict[str, dict], fills: dict[str, list[dict]]):
        self.out_dir = out_dir
        self.img_dir = out_dir / "images"
        self.options = options
        self.fills = fills
        self._processed: dict[Path, tuple] = {}        # 输出路径 → 生成参数

    def rel(self, p: Path) -> str:
        """文件在 HTML 里的相对 URL；文件名里有 #、?、% 也能正确载入。"""
        return quote(Path(os.path.relpath(p, self.out_dir)).as_posix())

    @staticmethod
    def to_print_gray(im: Image.Image, mix: tuple[float, float, float] | None = None) -> Image.Image:
        """转成适合黑白印刷的灰度：可自定通道配比，自动色阶，稍提中间调抵消网点扩大。"""
        im = im.convert("RGB")
        if mix:
            r, g, b = mix
            gray = im.convert("L", (r, g, b, 0))
        else:
            gray = im.convert("L")
        gray = ImageOps.autocontrast(gray, cutoff=(0.5, 0.3))
        return gray.point([round(255 * (v / 255) ** 0.9) for v in range(256)])

    def process_image(self, src: Path, crop: tuple[float, float, float, float] | None = None,
                      out_name: str | None = None, mix=None, max_side: int = 2000) -> tuple[Path, int, int]:
        """每次构建都从原图重新生成一次（同一次构建里只生成一次），不沿用上次留下的图，
        免得改了处理参数却用上旧图。同一输出文件只能对应一组参数。"""
        out = self.img_dir / (out_name or (src.stem + ".jpg"))
        out.parent.mkdir(parents=True, exist_ok=True)
        params = (src, crop, mix, max_side)
        if out not in self._processed:
            im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
            if crop:
                w, h = im.size
                im = im.crop((round(crop[0] * w), round(crop[1] * h), round(crop[2] * w), round(crop[3] * h)))
            g = self.to_print_gray(im, mix)
            long_side = max(g.size)
            if long_side > max_side:
                g = g.resize((round(g.width * max_side / long_side), round(g.height * max_side / long_side)),
                             Image.LANCZOS)
            g = g.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2))
            g.save(out, "JPEG", quality=90, dpi=(300, 300), optimize=True)
            self._processed[out] = params
        elif self._processed[out] != params:
            raise RuntimeError(f"两处配图要写到同一个文件 {out.name}，但裁切或处理参数不同")
        with Image.open(out) as im:
            return out, im.width, im.height

    def remove_unused_images(self, html_text: str) -> None:
        """删掉这一版没用到的图（改名、撤稿后留下的旧图）。"""
        used = set(re.findall(r'src="([^"]+)"', html_text))
        for f in self.img_dir.rglob("*"):
            if f.is_file() and self.rel(f) not in used:
                f.unlink()

    def fill_figure(self, piece: Piece, spec: dict, lines: int, idx: int, pad: int = 0) -> str:
        """生成一幅通栏插图的 HTML；线描按实际尺寸出 SVG，照片裁成灰度。pad：图上方再空几行（沉底用）。"""
        hgt = lines * LH
        where = spec.get("where", "end")
        cls = "fill fill-head" if where == "head" else "fill"
        top = f"margin-top:{(1 + pad) * LH:.3f}pt;" if pad else ""
        if "art" in spec:
            svg = art.make(spec["art"], CONTENT_W, hgt - IMG_TRIM, **spec.get("args", {}))
            out = self.img_dir / "art" / f"{piece.key.replace('/', '_')[:-3]}-{where}{idx}.svg"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(svg, encoding="utf-8")
            src, alt = out, spec.get("alt", "插图")
        else:
            src, _, _ = self.process_image(ROOT / spec["photo"], spec.get("crop"), mix=spec.get("mix"),
                                           out_name=f"fill/{piece.key.replace('/', '_')[:-3]}-{where}{idx}.jpg")
            alt = spec.get("alt", "照片")
        pos = spec.get("pos", "50% 50%")
        return (f'<figure class="{cls}" style="{top}height:{hgt:.3f}pt">'
                f'<img src="{self.rel(src)}" alt="{html.escape(alt)}" style="object-position:{pos}"></figure>')

    def render_blocks(self, piece: Piece) -> str:
        out: list[str] = []
        opts = self.options.get(piece.key, {})
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
                path, w, h = self.process_image((piece.path.parent / b.src).resolve())
                n = max(4, round(COL_W * h / w / LH))
                n = min(n, opts.get("max_img_lines", 99))
                out.append(f'<figure class="fig" style="height:{n * LH:.3f}pt">'
                           f'<img src="{self.rel(path)}" alt="{html.escape(b.alt)}"></figure>')
        return "\n".join(out)

    @staticmethod
    def split_trailing_images(piece: Piece) -> tuple[list[Block], list[Block]]:
        """文末连续的图片单独拿出来排成通栏图组。"""
        blocks = list(piece.blocks)
        tail: list[Block] = []
        while blocks and blocks[-1].kind == "img":
            tail.insert(0, blocks.pop())
        if len(tail) < 2:
            return piece.blocks, []
        return blocks, tail

    def wide_figure(self, piece: Piece, imgs: list[Block], extra_lines: int = 0) -> str:
        """若干张图并排成一行，铺满版心宽度，高度取整行；extra_lines 用来放大填满留白。"""
        crops = self.options.get(piece.key, {}).get("crops", {})
        items = []
        for b in imgs:
            path, w, h = self.process_image((piece.path.parent / b.src).resolve(), crops.get(Path(b.src).name))
            items.append((path, w / h, b.alt))
        usable = CONTENT_W - GAP * (len(items) - 1)
        total_aspect = sum(a for _, a, _ in items)
        n = max(4, round(usable / total_aspect / LH)) + extra_lines
        hgt = n * LH
        natural = [a * (hgt - IMG_TRIM) for _, a, _ in items]
        scale = usable / sum(natural)
        tags = [f'<img src="{self.rel(p)}" alt="{html.escape(alt)}" style="width:{nw * scale:.3f}pt;flex:none">'
                for (p, _, alt), nw in zip(items, natural)]
        return f'<figure class="fig-wide" style="height:{hgt:.3f}pt">{"".join(tags)}</figure>'

    def render_piece(self, piece: Piece, fills: dict[str, dict[int, int]],
                     pads: dict[str, dict[int, int]] | None = None, tops: dict[str, int] | None = None) -> str:
        if piece.kind == "opener":
            classes = ["piece", "opener", "single"]
        elif piece.kind in ("front", "back"):
            classes = ["piece", "front", "single"]
        else:
            classes = ["piece", piece.page]
        if piece.is_poem and not self.options.get(piece.key, {}).get("poem_columns"):
            classes.append("poem")
        head = [f'<h1 class="title{"" if piece.name else " bare"}">{centered(piece.title)}</h1>']
        if piece.subtitle:
            head.append(f'<p class="subtitle">{centered(piece.subtitle)}</p>')
        if piece.name:
            # 班级号是独立西文，单独用 Constantia
            who = (f'<span class="num">{piece.cls}</span>　{inline(piece.name)}' if piece.cls
                   else inline(piece.name))
            head.append(f'<p class="author">{who}</p>')

        specs = self.fills.get(piece.key, [])
        sized = fills.get(piece.pid, {})
        head_figs = "".join(self.fill_figure(piece, s, s["lines"], i)
                            for i, s in enumerate(specs) if s.get("where") == "head")

        body_blocks, tail = self.split_trailing_images(piece)
        saved = piece.blocks
        piece.blocks = body_blocks
        body = self.render_blocks(piece)
        piece.blocks = saved

        extra = ""
        grow = next((i for i, s in enumerate(specs) if s.get("grow")), None)
        if tail:
            extra = self.wide_figure(piece, tail, sized.get(grow, 0) if grow is not None else 0)
        padded = (pads or {}).get(piece.pid, {})
        for i, s in enumerate(specs):
            if s.get("where", "end") == "end" and not s.get("grow") and i in sized:
                extra += self.fill_figure(piece, s, sized[i], i, padded.get(i, 0))
        # 起始页：整组内容上下居中，上方补的空白取整行，不离开网格
        top = (tops or {}).get(piece.pid, 0)
        style = f' style="padding-top:{top * LH:.3f}pt"' if top else ""
        return (f'<article class="{" ".join(classes)}" id="{piece.pid}"{style}>\n'
                f'<header class="head">{"".join(head)}</header>\n{head_figs}'
                f'<div class="body">\n{body}\n</div>\n{extra}</article>')

    def fill_limits(self, piece: Piece, spec: dict) -> dict:
        """某项留白配图的行数限制；各期可以按需改写（第一期的人员表按名单算高度）。"""
        return spec

    def place_fills(self, pieces: dict[str, Piece], spans: dict[str, tuple[int, int]], free: dict[str, int],
                    fills: dict[str, dict[int, int]], pads: dict[str, dict[int, int]], base_len: dict[str, int],
                    tops: dict[str, int] | None = None) -> bool:
        """按每篇末页的剩余行数放置留白配图；配图把文章挤出新页时，一次一行地缩回去。有改动返回 True。
        tops 不为 None 时，板块起始页的内容上下居中（上方补的空行记在 tops 里）。"""
        changed = False
        if tops is not None:
            # 没有配图的起始页：文字整组上下居中
            for pid, piece in pieces.items():
                if piece.kind == "opener" and not self.fills.get(piece.key) and pid not in tops and free[pid] > 1:
                    tops[pid] = free[pid] // 2
                    changed = True
        for pid, piece in pieces.items():
            length = spans[pid][1] - spans[pid][0]
            for i, s in enumerate(self.fills.get(piece.key, [])):
                if s.get("where", "end") != "end":
                    continue
                s = self.fill_limits(piece, s)
                cur = fills.get(pid, {}).get(i)
                if cur is None:
                    # 尚未配图：剩余行数够多才放；通栏图上方空 1 行
                    if free[pid] >= s.get("min", 9):
                        base_len[pid] = length
                        want = free[pid] - (0 if s.get("grow") else 1)
                        n = min(want, s.get("max", LINES))
                        fills.setdefault(pid, {})[i] = n
                        if tops is not None and piece.kind == "opener" and want > n:
                            # 起始页：图紧跟导读，多出的空白一半放在整组上方，上下对称
                            tops[pid] = (want - n) // 2
                        elif s.get("anchor") == "bottom" and want > n:
                            pads.setdefault(pid, {})[i] = want - n
                        changed = True
                elif length > base_len.get(pid, length):
                    # 挤出新页：先减上方、沉底的空行，再缩图，一次一行重排
                    if tops and tops.get(pid):
                        tops[pid] -= 1
                    elif pads.get(pid, {}).get(i):
                        pads[pid][i] -= 1
                    else:
                        fills[pid][i] = cur - 1
                    changed = True
        return changed
