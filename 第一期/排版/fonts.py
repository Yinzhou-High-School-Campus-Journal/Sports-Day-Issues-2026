#!/usr/bin/env python3
"""准备排版字体（输出到 第一期/排版/fonts/，该目录不进仓库）。

Chromium 打印 PDF 时，CFF 轮廓的 OTF 和可变字体会被转成 Type 3 字体，
印刷预检容易报错。这里把可变字体实例化成各字重的静态 TrueType：

  思源宋体 SC ← Noto Serif SC 可变字体（与思源宋体同一套字形）：400 / 500 / 600 / 700
  Noto Serif  ← Noto Serif 可变字体：350 / 500 / 600 / 700、斜体 350（正文里夹排的西文、数字）

以下商业字体需自行放进 fonts/（不进仓库）：
  方正恒仿宋：FZHengFSJF-R.TTF、FZHengFSJF-M.TTF（缺少时退回开源的朱雀仿宋 ZhuqueFangsong-Regular.ttf）
  Constantia：CONSTAN.TTF、CONSTANB.TTF、CONSTANI.TTF、CONSTANZ.TTF（成段西文、页码等独立西文）
"""
from __future__ import annotations

import urllib.request
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FONTS = Path(__file__).resolve().parent / "fonts"

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
