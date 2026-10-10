#!/usr/bin/env python3
"""《云图试骏》排版：Markdown 稿件 → HTML → PDF。

用法：python3 排版/第一期/build.py [第一期]

流程：
1. 读取期刊目录下的稿件（卷首语、开幕式致辞、各板块导读与文章），生成 HTML；
2. 调用 Chromium（排版/render.cjs，两期共用）打印成 PDF；
3. 从 PDF 书签读出每篇的起止页，回填目录页码；量出每篇末页剩下几行，
   按 FILLS 的配置在留白处放插图（线描按实际尺寸生成，照片按尺寸裁切），再排，直到版面稳定；
4. 保存正文 PDF，拼入扉页生成完整内页，再拼封面生成预览版。
稿件解析、配图与版面测量两期共用，见 排版/typeset.py。
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT_DIR = HERE
sys.path.insert(0, str(HERE.parent))
from preflight import check_requirements, prepare_fonts, require_single_page, sources_unchanged
check_requirements()            # 先核对依赖：没装或版本不对时给出安装提示，而不是在下面导入时报错

import pymupdf

from pdf_metadata import document_metadata, drop_toc_children, outline_from_html, save_pdf, set_page_labels
from typeset import (LH, Book, Piece, check_glyphs, fangsong_texts, free_lines, inline, load_issue, page_count,
                     parse_staff, piece_pages, piece_texts, render_pdf, supplement_css)

ISSUES = {
    "第一期": {
        "journal": "校运会特刊",
        "name": "云图试骏",             # 本期名
        "front": ["0_前置/01_卷首语.md", "0_前置/03_开幕式致辞.md"],
        "sections": ["1_校运风采", "2_少年心语", "3_校园绘卷", "4_社会观察", "5_古韵风雅"],
        # 板块 → 正文的命名页（各板块的页眉写在 style.css 里）
        "page_classes": {"校运风采": "sec-xiaoyun", "少年心语": "sec-shaonian", "校园绘卷": "sec-xiaoyuan",
                         "社会观察": "sec-shehui", "古韵风雅": "sec-guyun"},
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
# 留白配图（键为期刊目录下的相对路径），写法见 typeset.Book；本期另有：
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
    "2_少年心语/01_山顶的云海日出_2610_董臙彤.md": [
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


# ---------------------------------------------------------------- 人员表（卷首语页底）

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


class FirstIssue(Book):
    """第一期的留白配图另有人员表：排在卷首语页底，高度按名单算。"""

    def fill_figure(self, piece: Piece, spec: dict, lines: int, idx: int, pad: int = 0) -> str:
        if "staff" in spec:
            top = f"margin-top:{(1 + pad) * LH:.3f}pt;" if pad else ""
            return staff_block(parse_staff(piece.path.parent / spec["staff"]), lines, top)
        return super().fill_figure(piece, spec, lines, idx, pad)

    def fill_limits(self, piece: Piece, spec: dict) -> dict:
        if "staff" in spec:                         # 上方至少空 1 行
            need = staff_split(parse_staff(piece.path.parent / spec["staff"]))[1]
            return {**spec, "max": need, "min": need + 1}
        return spec


# ---------------------------------------------------------------- HTML

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


def build_html(book: Book, issue: str, front: list[Piece], groups: list[tuple[str, list[Piece]]],
               pages: dict[str, int], fills: dict[str, dict[int, int]], pads: dict[str, dict[int, int]]) -> str:
    cfg = ISSUES[issue]
    body = [book.render_piece(p, fills, pads) for p in front]
    body.append(render_toc(front, groups, pages))
    for _, items in groups:
        body.extend(book.render_piece(p, fills, pads) for p in items)
    return ("<!doctype html>\n<html lang=\"zh-Hans\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>{cfg['journal']} {issue} {cfg['name']}</title>\n"
            f'<link rel="stylesheet" href="{book.rel(HERE / "style.css")}">\n'
            f"<style>\n{supplement_css(book.rel)}</style>\n</head>\n<body>\n"
            + "\n\n".join(body) + "\n</body>\n</html>\n")


# ---------------------------------------------------------------- 拼页

def finalize(issue: str, raw: Path, html_text: str) -> tuple[Path, Path, Path]:
    """Chromium 的输出补上书签文字与文件信息，存为正文；拼上扉页为发行内页，再拼上封面为预览。
    每个文件都先写临时文件，写完再替换。"""
    cfg = ISSUES[issue]
    cover, title_page = [ROOT / name for name in cfg["cover"]]
    require_single_page([cover, title_page])
    body_path = OUT_DIR / f"{issue}正文.pdf"
    with pymupdf.open(raw) as doc:
        doc.set_toc(drop_toc_children(outline_from_html(doc.get_toc(simple=False), html_text)))
        doc.set_metadata(document_metadata(issue, "正文", doc.metadata.get("producer", "")))
        save_pdf(doc, body_path.with_suffix(".tmp.pdf"))
    body_path.with_suffix(".tmp.pdf").replace(body_path)

    # 发布内页 = 后来独立制作的扉页 + 原正文；正文的纸面页码不变。
    inner_path = OUT_DIR / f"{issue}内页.pdf"
    with pymupdf.open() as out:
        with pymupdf.open(title_page) as title, pymupdf.open(body_path) as body:
            out.insert_pdf(title)
            out.insert_pdf(body)
            # 书签沿用正文里的落点（指向各标题所在位置），页序整体后移一页
            out.set_toc([[1, "扉页", 1]] + [[t[0], t[1], t[2] + 1, t[3]] for t in body.get_toc(simple=False)])
            out.set_metadata(document_metadata(issue, "内页", body.metadata.get("producer", "")))
        set_page_labels(out, {1: "扉页"})
        temp = inner_path.with_suffix(".tmp.pdf")
        save_pdf(out, temp)
    temp.replace(inner_path)

    preview = OUT_DIR / f"{issue}（含封面预览）.pdf"
    with pymupdf.open() as out, pymupdf.open(cover) as cd, pymupdf.open(inner_path) as inner:
        out.insert_pdf(cd)
        out.insert_pdf(inner)
        out.set_toc([[1, "封面", 1]] + [[t[0], t[1], t[2] + 1, t[3]] for t in inner.get_toc(simple=False)])
        set_page_labels(out, {1: "封面", 2: "扉页"})
        out.set_metadata(document_metadata(issue, "含封面预览", inner.metadata.get("producer", "")))
        temp = preview.with_suffix(".tmp.pdf")
        save_pdf(out, temp)
    temp.replace(preview)
    return body_path, inner_path, preview


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("issue", nargs="?", default="第一期", choices=list(ISSUES))
    args = ap.parse_args()
    issue = args.issue
    prepare_fonts()
    require_single_page([ROOT / name for name in ISSUES[issue]["cover"]])
    with sources_unchanged():
        build(issue)


def build(issue: str) -> None:
    cfg = ISSUES[issue]
    book = FirstIssue(OUT_DIR, ARTICLE_OPTIONS, FILLS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUT_DIR / f"{issue}.html"
    raw = OUT_DIR / f"{issue}.tmp.pdf"          # Chromium 的输出；成品在 finalize() 里写出
    front, groups, back = load_issue(issue, cfg)
    pieces = {p.pid: p for p in front + [x for _, items in groups for x in items] + back}
    staff = [(ROOT / issue / key).parent.joinpath(s["staff"]).read_text(encoding="utf-8")
             for key, specs in FILLS.items() for s in specs if "staff" in s]
    check_glyphs([t for p in pieces.values() for t in piece_texts(p)] + staff,
                 fangsong_texts(list(pieces.values())) + staff + [name for name, _ in groups])

    pages: dict[str, int] = {}
    fills: dict[str, dict[int, int]] = {}      # pid → {配图序号: 行数}
    pads: dict[str, dict[int, int]] = {}       # pid → {配图序号: 图上方多空的行数}（anchor: bottom）
    base_len: dict[str, int] = {}              # 加文末配图前每篇的页数
    for rnd in range(1, 9):
        html_path.write_text(build_html(book, issue, front, groups, pages, fills, pads), encoding="utf-8")
        render_pdf(html_path, raw)
        starts, spans = piece_pages(raw, front, groups, back, html_path.read_text(encoding="utf-8"))
        free = free_lines(raw, spans)
        changed = starts != pages
        pages = starts
        changed |= book.place_fills(pieces, spans, free, fills, pads, base_len)
        print(f"第 {rnd} 遍：{page_count(raw)} 页")
        if not changed:
            break
    else:
        # 第 8 遍还在变：目录页码或配图行数与版面对不上，不能当成品
        raise RuntimeError("排了 8 遍版面仍未稳定，目录页码或配图可能与版面不符；请检查 FILLS 配置")

    report = []
    for pid, (a, b) in spans.items():
        title = "目录" if pid == "toc" else pieces[pid].title
        report.append({"pid": pid, "title": title, "pages": [a + 1, b + 1], "page_no": a, "free_lines": free[pid],
                       "fills": fills.get(pid, {})})
    (OUT_DIR / f"{issue}版面.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    html_text = html_path.read_text(encoding="utf-8")
    book.remove_unused_images(html_text)
    total = page_count(raw)
    body, inner, preview = finalize(issue, raw, html_text)
    raw.unlink()
    print(f"完成：{body.name}（{total} 页），{inner.name}（{total + 1} 页），预览：{preview.name}（{total + 2} 页）")
    for r in report:
        flag = "  ← 留白多" if r["free_lines"] >= 9 else ""
        print(f"  {r['pages'][0]:>3}–{r['pages'][1]:<3} 末页余 {r['free_lines']:>3} 行  {r['title']}{flag}")


if __name__ == "__main__":
    sys.exit(main())
