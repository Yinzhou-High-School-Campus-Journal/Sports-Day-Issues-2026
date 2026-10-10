#!/usr/bin/env python3
"""《骋风逐曜》排版：Markdown 稿件 → HTML → PDF。

用法：python3 排版/第二期/build.py [第二期]

流程：
1. 读取期刊目录下的稿件（人员表、各板块导读与文章、卷尾语），生成 HTML；
2. 调用 Chromium（排版/render.cjs，两期共用）打印成 PDF；
3. 从 PDF 书签读出每篇的起止页，回填目录页码；量出每篇末页剩下几行，
   按 FILLS 的配置在留白处放插图（线描按实际尺寸生成，照片按尺寸裁切），再排，直到版面稳定；
4. 拼上扉页，写入书签、PDF 元数据和页码标签。
稿件解析、配图与版面测量两期共用，见 排版/typeset.py。
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT_DIR = HERE
sys.path.insert(0, str(HERE.parent))
from preflight import check_requirements, prepare_fonts, require_single_page, sources_unchanged
check_requirements()            # 先核对依赖：没装或版本不对时给出安装提示，而不是在下面导入时报错

import pymupdf

from pdf_metadata import document_metadata, outline_from_html, save_pdf, set_page_labels
from typeset import (Book, Piece, check_glyphs, fangsong_texts, free_lines, inline, load_issue, page_count,
                     parse_staff, piece_pages, piece_texts, render_pdf, supplement_css)

# 各期配置。sections 为板块目录，去掉「1_」这类序号前缀即印出的板块名；
# 板块目录里序号为 0 的稿件（00_导读.md）排成板块起始页。
# 内页开头：扉页（右页）、人员表（左页）、目录（右页）、空白页（左页）不印页码、不计页数，其后的第一页（右页）为第 1 页。
# Chromium 只排人员表以后的部分；扉页和凑双数的空白页在 finalize() 里拼上。
ISSUES = {
    "第二期": {
        "journal": "校运会特刊",
        "name": "骋风逐曜",             # 本期名：印在左页页眉（右页页眉为板块名）
        "front": [],                    # 目录之前的稿件：这期不放卷首语、致辞
        "sections": ["1_红砖絮语", "2_赛道秋声", "3_青衿问道", "4_思接千载"],
        "back": ["卷尾语.md"],          # 全刊最后
        "title_page": "排版/封面/第二期扉页.pdf",  # 另做的扉页，拼在内页最前
        "staff": "0_前置/01_人员表.md",           # 扉页背面，在目录前（封面另做）
        "toc_class": True,              # 目录标班级
    },
}

# 个别稿件的版面参数（键为期刊目录下的相对路径）
OPTIONS: dict[str, dict] = {
    # 诗行短、诗节多：排双栏，一页放下
    "1_红砖絮语/01_青春颂_2607_沈真一.md": {"poem_columns": 2},
    # 月亮照片大面积纯黑，先裁到月亮周围
    "4_思接千载/09_游天妃湖赏月有感_2614_康茵子.md": {
        "crops": {"游天妃湖赏月有感_2614_康茵子_02.jpeg": (0.389, 0.106, 0.877, 0.509)},
    },
}
# 留白配图（键为期刊目录下的相对路径），写法见 typeset.Book。
# 第一期编辑部版里画过、拍过的图，内容合适的直接沿用。
FILLS: dict[str, list[dict]] = {
    # 板块起始页。航拍原片左上角、开幕式原片右上角有水印，都裁掉
    "1_红砖絮语/00_导读.md": [{"photo": "资产/配图/校园航拍_钟楼_半岛第一飞手.jpg", "crop": (0.23, 0, 1, 1),
                            "pos": "50% 0%", "min": 1, "max": 17, "anchor": "bottom",
                            "alt": "钟楼（B 站用户半岛第一飞手航拍）"}],
    "2_赛道秋声/00_导读.md": [{"photo": "资产/配图/2023运动会开幕式_跑道_鄞中电视台.jpg", "crop": (0, 0.1, 1, 0.835),
                            "pos": "46% 50%", "min": 1, "max": 15, "anchor": "bottom",
                            "alt": "2023 年运动会开幕式，举班牌走过跑道（鄞中电视台）"}],
    # 青衿问道没有贴题的图，导读写长，不配图
    "4_思接千载/00_导读.md": [{"art": "moon_lake", "args": {"snow": True}, "min": 1, "alt": "湖心亭看雪"}],
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


# ---------------------------------------------------------------- HTML

STAFF_NAME_EM = 7                # 人员表姓名栏宽：两个三字名加一个空格


def render_staff(issue: str) -> str:
    """人员表单占一页（扉页背面，左页；扉页在 finalize() 里拼上）。仿老师发来的付印版的竖式：窄窄一栏，每行至多两个姓名，转行与首个姓名对齐；
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


HEADER_STYLE = ('font-family: "YZ FangSong", "YZ Song", serif; font-weight: 500; font-size: 9pt; '
                'vertical-align: bottom; padding-bottom: 8mm;')


def section_pages_css(cfg: dict) -> str:
    """每个板块一种命名页。页眉字间加全角空格：左页（偶数页）为本期名，右页（奇数页）为板块名；
    没有本期名时两边都是板块名。"""
    out = []
    name = "　".join(cfg.get("name", ""))
    for k, sec in enumerate(cfg["sections"], 1):
        label = "　".join(re.sub(r"^\d+_", "", sec))
        if name:
            out.append(f'@page sec{k}:left {{ @top-center {{ content: "{name}"; {HEADER_STYLE} }} }}\n'
                       f'@page sec{k}:right {{ @top-center {{ content: "{label}"; {HEADER_STYLE} }} }}')
        else:
            out.append(f'@page sec{k} {{ @top-center {{ content: "{label}"; {HEADER_STYLE} }} }}')
        out.append(f'.sec{k} {{ page: sec{k}; }}')
    return "\n".join(out)


def build_html(book: Book, issue: str, front: list[Piece], groups: list[tuple[str, list[Piece]]], back: list[Piece],
               pages: dict[str, int], fills: dict[str, dict[int, int]], pads: dict[str, dict[int, int]],
               tops: dict[str, int]) -> str:
    """pages 为各篇印出来的页码（目录、人员表不计页数，其后的第一页是第 1 页）。"""
    cfg = ISSUES[issue]
    body = [render_staff(issue)] if cfg.get("staff") else []
    body += [book.render_piece(p, fills, pads, tops) for p in front]
    body.append(render_toc(front, groups, pages, cfg.get("toc_class", False), back))
    for _, items in groups:
        body.extend(book.render_piece(p, fills, pads, tops) for p in items)
    body.extend(book.render_piece(p, fills, pads, tops) for p in back)
    title = " ".join(x for x in (cfg["journal"], issue, cfg.get("name", "")) if x)
    return ("<!doctype html>\n<html lang=\"zh-Hans\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>{title}</title>\n"
            f'<link rel="stylesheet" href="{book.rel(HERE / "style.css")}">\n'
            f"<style>\n{supplement_css(book.rel)}{section_pages_css(cfg)}\n</style>\n</head>\n<body>\n"
            + "\n\n".join(body) + "\n</body>\n</html>\n")


# ---------------------------------------------------------------- 页码与拼页

def uncounted_pages(spans: dict[str, tuple[int, int]], staff: bool) -> dict[int, str]:
    """不印页码、不计页数的页：{PDF 里的第几页（从 1 数）: 页码标签}。人员表是第 1 页，目录随后。"""
    out = {1: "人员表"} if staff else {}
    out.update({n: "目录" for n in range(spans["toc"][0], spans["toc"][1] + 1)})
    return out


def printed_page(n: int, uncounted: dict[int, str]) -> int:
    """PDF 里的第 n 页印出来是第几页：前面不计页数的页不算。"""
    return n - sum(1 for u in uncounted if u < n)


def finalize(issue: str, raw: Path, pdf_path: Path, uncounted: dict[int, str],
             html_text: str) -> tuple[dict[int, str], list[int]]:
    """拼上扉页、写入元数据和页码标签，写完再替换 pdf_path。Chromium 排好的版面（raw）不动：扉页（另做的 PDF）插在最前；
    开头不计页数的页若是奇数张，在其后补一张空白页，让第 1 页仍落在右页（页眉的左右页也就不变）。
    uncounted 为 Chromium 输出里不计页数的页；返回（最终 PDF 里不计页数的页，插入的页在最终 PDF 里的页序）。"""
    cfg = ISSUES[issue]
    with pymupdf.open(raw) as doc:
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
        doc.set_toc(extra + outline_from_html(doc.get_toc(simple=False), html_text))
        doc.set_metadata(document_metadata(issue, "内页", doc.metadata.get("producer", "")))
        set_page_labels(doc, final)
        save_pdf(doc, pdf_path.with_suffix(".tmp.pdf"))
    pdf_path.with_suffix(".tmp.pdf").replace(pdf_path)
    return final, inserted


def final_page(n: int, inserted: list[int]) -> int:
    """Chromium 输出里的第 n 页在拼好的 PDF 里是第几页。"""
    for p in sorted(inserted):
        if p <= n:
            n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("issue", nargs="?", default="第二期", choices=list(ISSUES))
    args = ap.parse_args()
    issue = args.issue
    cfg = ISSUES[issue]
    prepare_fonts()
    require_single_page([ROOT / cfg["title_page"]])
    with sources_unchanged():
        build(issue)


def build(issue: str) -> None:
    cfg = ISSUES[issue]
    book = Book(OUT_DIR, OPTIONS, FILLS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUT_DIR / f"{issue}.html"
    raw = OUT_DIR / f"{issue}.tmp.pdf"          # Chromium 的输出；成品在 finalize() 里写出
    pdf_path = OUT_DIR / f"{issue}内页.pdf"
    front, groups, back = load_issue(issue, cfg)
    pieces = {p.pid: p for p in front + [x for _, items in groups for x in items] + back}
    staff = (ROOT / issue / cfg["staff"]).read_text(encoding="utf-8") if cfg.get("staff") else ""
    check_glyphs([t for p in pieces.values() for t in piece_texts(p)] + [staff],
                 fangsong_texts(list(pieces.values())) + [staff, cfg["name"]] + [name for name, _ in groups])

    phys: dict[str, int] = {}                  # 各篇起始页（PDF 里的第几页）
    pages: dict[str, int] = {}                 # 印出来的页码：扉页、人员表、目录（及空白页）不计页数
    fills: dict[str, dict[int, int]] = {}      # pid → {配图序号: 行数}
    pads: dict[str, dict[int, int]] = {}       # pid → {配图序号: 图上方多空的行数}（anchor: bottom）
    tops: dict[str, int] = {}                  # 起始页：整组内容上方补的空行，让内容上下居中
    base_len: dict[str, int] = {}              # 加文末配图前每篇的页数
    for rnd in range(1, 9):
        html_path.write_text(build_html(book, issue, front, groups, back, pages, fills, pads, tops), encoding="utf-8")
        render_pdf(html_path, raw)
        starts, spans = piece_pages(raw, front, groups, back, html_path.read_text(encoding="utf-8"))
        free = free_lines(raw, spans)
        changed = starts != phys
        phys = starts
        skip = uncounted_pages(spans, bool(cfg.get("staff")))
        pages = {pid: printed_page(n, skip) for pid, n in starts.items()}
        changed |= book.place_fills(pieces, spans, free, fills, pads, base_len, tops)
        print(f"第 {rnd} 遍：{page_count(raw)} 页")
        if not changed:
            break
    else:
        # 第 8 遍还在变：目录页码或配图行数与版面对不上，不能当成品
        raise RuntimeError("排了 8 遍版面仍未稳定，目录页码或配图可能与版面不符；请检查 FILLS 配置")

    html_text = html_path.read_text(encoding="utf-8")
    final, inserted = finalize(issue, raw, pdf_path, skip, html_text)
    raw.unlink()
    total = page_count(pdf_path)
    report = []                                # 起止页按拼好扉页、空白页后的 PDF 计
    for pid, (a, b) in spans.items():
        title = "目录" if pid == "toc" else pieces[pid].title
        report.append({"pid": pid, "title": title, "pages": [final_page(a, inserted), final_page(b, inserted)],
                       "page_no": None if a in skip else pages.get(pid),   # 不计页数的页没有页码
                       "free_lines": free[pid], "fills": fills.get(pid, {})})
    (OUT_DIR / f"{issue}版面.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    book.remove_unused_images(html_text)
    print(f"完成：{pdf_path.name}（{total} 页）")
    for r in report:
        flag = "  ← 留白多" if r["free_lines"] >= 9 else ""
        print(f"  {r['pages'][0]:>3}–{r['pages'][1]:<3} 末页余 {r['free_lines']:>3} 行  {r['title']}{flag}")


if __name__ == "__main__":
    sys.exit(main())
