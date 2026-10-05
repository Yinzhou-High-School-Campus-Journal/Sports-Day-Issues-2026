#!/usr/bin/env python3
"""准备排版字体（输出到已纳入仓库的 排版/fonts/）。

Chromium 打印 PDF 时，CFF 轮廓的 OTF 和可变字体会被转成 Type 3 字体，
印刷预检容易报错。这里把可变字体实例化成各字重的静态 TrueType：

  思源宋体 SC ← Noto Serif SC 可变字体（与思源宋体同一套字形）：400 / 500 / 600 / 700
  Noto Serif  ← Noto Serif 可变字体：350 / 500 / 600 / 700、斜体 350（正文里夹排的西文、数字）

以下商业字体已随项目收录在 fonts/：
  方正恒仿宋：FZHengFSJF-R.TTF、FZHengFSJF-M.TTF（缺少时退回开源的朱雀仿宋 ZhuqueFangsong-Regular.ttf）
  Constantia：CONSTAN.TTF、CONSTANB.TTF、CONSTANI.TTF、CONSTANZ.TTF（成段西文、页码等独立西文）
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FONTS = Path(__file__).resolve().parents[1] / "fonts"

SOURCES = {
    "NotoSerifSC-VF.ttf": "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Serif/Variable/TTF/Subset/NotoSerifSC-VF.ttf",
    "NotoSerif-VF.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserif/NotoSerif%5Bwdth%2Cwght%5D.ttf",
    "NotoSerif-Italic-VF.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserif/NotoSerif-Italic%5Bwdth%2Cwght%5D.ttf",
}

# 输出文件名 → (源可变字体, 轴坐标, 家族名, 字重名)
INSTANCES = {
    "YZSong-400.ttf": ("NotoSerifSC-VF.ttf", {"wght": 400}, "Noto Serif SC", "Regular"),
    "YZSong-500.ttf": ("NotoSerifSC-VF.ttf", {"wght": 500}, "Noto Serif SC", "Medium"),
    "YZSong-600.ttf": ("NotoSerifSC-VF.ttf", {"wght": 600}, "Noto Serif SC", "SemiBold"),
    "YZSong-700.ttf": ("NotoSerifSC-VF.ttf", {"wght": 700}, "Noto Serif SC", "Bold"),
    "YZLatin-350.ttf": ("NotoSerif-VF.ttf", {"wght": 350, "wdth": 100}, "Noto Serif", "W350"),
    "YZLatin-500.ttf": ("NotoSerif-VF.ttf", {"wght": 500, "wdth": 100}, "Noto Serif", "Medium"),
    "YZLatin-600.ttf": ("NotoSerif-VF.ttf", {"wght": 600, "wdth": 100}, "Noto Serif", "SemiBold"),
    "YZLatin-700.ttf": ("NotoSerif-VF.ttf", {"wght": 700, "wdth": 100}, "Noto Serif", "Bold"),
    "YZLatin-Italic-350.ttf": ("NotoSerif-Italic-VF.ttf", {"wght": 350, "wdth": 100}, "Noto Serif", "W350 Italic"),
}


GEN = FONTS / "gen"          # 从商业字体派生的补字：构建时生成，不纳入仓库（PDF 里照常嵌入子集）

# 方正恒仿宋缺的字，用同一字体里的部件拼出来。每个部件：(取自哪个字, 取哪些轮廓, 目标框)
#   取哪些轮廓："left" / "right" 按轮廓包围框中心在 x = 500 哪一侧分，"all" 为整个字；
#   目标框 (x0, x1, y0, y1)：把这些轮廓的包围框缩放、平移到这里（单位 1/1000 em）。
# 比例参照思源宋体的「臙」：左旁「月」收窄一成多，「燕」压到原宽的七成左右（压窄后笔画略细，
# 但「燕」笔画密，正文字号下灰度反而与左右的字最接近，不另加粗）。
FANGSONG_COMPOSED = {
    "臙": [("胭", "left", (24, 350, -76, 741)),
           ("燕", "all", (366, 922, -78, 790))],
}


def make_fangsong_supplement() -> dict[str, Path]:
    """生成方正恒仿宋补字字体（fonts/gen/FZHengFSJF-{R,M}-supp.ttf），返回 {字重代号: 路径}；缺源字体时跳过。"""
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools import subset

    out: dict[str, Path] = {}
    for weight in ("R", "M"):
        src = FONTS / f"FZHengFSJF-{weight}.TTF"
        dest = GEN / f"FZHengFSJF-{weight}-supp.ttf"
        if not src.exists():
            continue
        if dest.exists() and dest.stat().st_mtime >= max(src.stat().st_mtime, Path(__file__).stat().st_mtime):
            out[weight] = dest
            continue
        font = TTFont(src)
        cmap, gs = font.getBestCmap(), font.getGlyphSet()
        glyf, hmtx = font["glyf"], font["hmtx"]
        added = []
        for ch, parts in FANGSONG_COMPOSED.items():
            if ord(ch) in cmap:
                continue
            pen = TTGlyphPen(gs)
            for base, pick, (x0, x1, y0, y1) in parts:
                rec = RecordingPen()
                gs[cmap[ord(base)]].draw(rec)
                contours, cur = [], []
                for op, args in rec.value:
                    cur.append((op, args))
                    if op in ("closePath", "endPath"):
                        contours.append(cur)
                        cur = []
                boxes = []
                for c in contours:
                    bp = BoundsPen(gs)
                    for op, args in c:
                        getattr(bp, op)(*args)
                    boxes.append(bp.bounds)
                chosen = [c for c, b in zip(contours, boxes) if b and (
                    pick == "all" or (pick == "left") == ((b[0] + b[2]) / 2 < 500))]
                bb = [b for c, b in zip(contours, boxes) if c in chosen]
                bx0, by0 = min(b[0] for b in bb), min(b[1] for b in bb)
                bx1, by1 = max(b[2] for b in bb), max(b[3] for b in bb)
                sx, sy = (x1 - x0) / (bx1 - bx0), (y1 - y0) / (by1 - by0)
                tp = TransformPen(pen, (sx, 0, 0, sy, x0 - bx0 * sx, y0 - by0 * sy))
                for c in chosen:
                    for op, args in c:
                        getattr(tp, op)(*args)
            name = f"uni{ord(ch):04X}"
            font.setGlyphOrder(font.getGlyphOrder() + [name])
            glyf.glyphOrder = font.getGlyphOrder()
            glyf.glyphs[name] = pen.glyph()
            glyf[name].recalcBounds(glyf)
            hmtx[name] = (1000, glyf[name].xMin)
            if "vmtx" in font:                       # 竖排度量：照搬第一个部件所在字，按字顶高差调整
                ref = cmap[ord(parts[0][0])]
                adv, tsb = font["vmtx"][ref]
                font["vmtx"][name] = (adv, tsb + glyf[ref].yMax - glyf[name].yMax)
            for table in font["cmap"].tables:
                if table.isUnicode():
                    table.cmap[ord(ch)] = name
            added.append(ord(ch))
        if not added:
            continue
        for tag in ("hdmx", "LTSH", "VDMX"):             # 逐字形的设备度量表：补字没有，删掉
            if tag in font:
                del font[tag]
        opts = subset.Options()
        opts.hinting = False
        opts.name_IDs = ["*"]
        opts.notdef_outline = True
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=added)
        sub.subset(font)
        # 另起名字，PDF 里与方正恒仿宋本体区分开（印前检查看得出哪些字是补的）
        set_names(font, "FZHengFSJF Supp", {"R": "Regular", "M": "Medium"}[weight])
        GEN.mkdir(parents=True, exist_ok=True)
        font.save(dest)
        out[weight] = dest
    return out


def set_names(font: TTFont, family: str, style: str) -> None:
    """实例化后写入对应字重的名字，免得 PDF 里各字重都叫 ExtraLight。"""
    ps = f"{family.replace(' ', '')}-{style.replace(' ', '')}"
    name = font["name"]
    for rec in list(name.names):
        if rec.nameID in (1, 2, 3, 4, 6, 16, 17, 21, 22, 25):
            name.removeNames(nameID=rec.nameID)
    for nid, val in {1: f"{family} {style}", 2: "Italic" if "Italic" in style else "Regular",
                     3: f"{ps};YZ", 4: f"{family} {style}", 6: ps, 16: family, 17: style}.items():
        name.setName(val, nid, 3, 1, 0x409)


def main() -> None:
    FONTS.mkdir(exist_ok=True)
    for name, url in SOURCES.items():
        dest = FONTS / name
        if not dest.exists():
            print("下载", name)
            urllib.request.urlretrieve(url, dest)
    for out, (src, axes, family, style) in INSTANCES.items():
        dest = FONTS / out
        if dest.exists():
            continue
        print("实例化", out)
        vf = TTFont(FONTS / src)
        static = instancer.instantiateVariableFont(vf, axes, inplace=False,
                                                  overlap=instancer.OverlapMode.KEEP_AND_SET_FLAGS)
        set_names(static, family, style)
        static.save(dest)


if __name__ == "__main__":
    main()
