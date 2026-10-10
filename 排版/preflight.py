"""构建前的检查与准备：依赖版本、字体（生成静态字重并校验指纹）、拼页用的单页 PDF，以及来源稿保护。"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FONTS = HERE / "fonts"

# Chromium 打印 PDF 时，可变字体会被转成 Type 3 字体，印刷预检容易报错，所以正文用实例化后的静态 TrueType。
# 输出文件名 → (源可变字体, 轴坐标, 家族名, 字重名)；输出不纳入仓库，指纹记录在 manifest.json。
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

# 方正恒仿宋缺的字：借用别的码位的字形（值为一个字），或用同一字体里的部件拼（值为 (取哪个字, 取哪部分[, 放进的框]) 的序列）。
# 取哪部分："left"/"right" 按轮廓中心落在字身左半或右半取舍，"all" 取整个字；不给框时位置不变，给了框
# (x0, x1, y0, y1)（字体单位）就缩放到框里。生成补字字体，样式表按 unicode-range 只把这几个字交给它。
# 出现新的缺字时排版前的查字会报错，在这里补一条即可。
FANGSONG_SUPPLEMENT = {
    "・": "·",                                       # 《鄞年・思叙》：借用「·」
    "晅": (("暄", "left"), ("恒", "right")),         # 日 + 亘
    # 月 + 燕：比例参照思源宋体的「臙」，「月」收窄一成多，「燕」压到原宽的七成左右
    "臙": (("胭", "left", (24, 350, -76, 741)), ("燕", "all", (366, 922, -78, 790))),
}
# 补字字体 → (源字体, CSS 字重范围，与样式表里的方正恒仿宋一致)；输出不纳入仓库，指纹记录在 manifest.json
SUPPLEMENT_FONTS = {
    "YZFangSong-Supplement-R.ttf": ("FZHengFSJF-R.TTF", "100 450"),
    "YZFangSong-Supplement-M.ttf": ("FZHengFSJF-M.TTF", "451 1000"),
}

# 构建只读不写的来源目录
SOURCE_DIRS = ("第一期", "第二期", "未选入", "信息缺失", "资产", "版本记录")


def requirements() -> dict[str, str]:
    """读取 requirements.txt 里锁定的「包名==版本」；跳过空行和注释。"""
    out = {}
    for line in (HERE / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.fullmatch(r"([A-Za-z0-9_.\-]+)\s*==\s*([^\s;]+)", line)
        if not m:
            raise ValueError(f"requirements.txt 只支持「包名==版本」：{line}")
        out[m.group(1)] = m.group(2)
    return out


def check_requirements() -> None:
    for name, expected in requirements().items():
        try:
            actual = version(name)
        except PackageNotFoundError:
            actual = "未安装"
        if actual != expected:
            raise RuntimeError(f"依赖版本不符：{name} 应为 {expected}，实际为 {actual}；"
                               "请先激活排版目录下的 .venv（source .venv/bin/activate），"
                               "或在排版目录运行 python -m pip install -r requirements.txt")


def check_fonts() -> None:
    """按 manifest.json 逐一核对字体指纹，缺失或不一致时报错。"""
    expected = json.loads((FONTS / "manifest.json").read_text(encoding="utf-8"))
    errors = []
    for name, digest in expected.items():
        path = FONTS / name
        if not path.is_file():
            errors.append(f"缺少字体：{path}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(f"字体版本不符：{path}")
    if errors:
        raise RuntimeError("\n".join(errors) + "\n源字体请从仓库恢复；生成的静态字重删除后重新构建即可。")


def _set_names(font, family: str, style: str) -> None:
    """实例化后写入对应字重的名字，免得 PDF 里各字重都叫 ExtraLight。"""
    ps = f"{family.replace(' ', '')}-{style.replace(' ', '')}"
    name = font["name"]
    for rec in list(name.names):
        if rec.nameID in (1, 2, 3, 4, 6, 16, 17, 21, 22, 25):
            name.removeNames(nameID=rec.nameID)
    for nid, val in {1: f"{family} {style}", 2: "Italic" if "Italic" in style else "Regular",
                     3: f"{ps};YZ", 4: f"{family} {style}", 6: ps, 16: family, 17: style}.items():
        name.setName(val, nid, 3, 1, 0x409)


def make_static_font(name: str, dest: Path) -> None:
    """从可变字体生成一个静态字重。修改时间沿用源字体，同一版本的 FontTools 每次生成的文件逐字节相同。"""
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    src, axes, family, style = INSTANCES[name]
    vf = TTFont(FONTS / src)
    static = instancer.instantiateVariableFont(vf, axes, inplace=False,
                                              overlap=instancer.OverlapMode.KEEP_AND_SET_FLAGS)
    _set_names(static, family, style)
    static["head"].modified = vf["head"].modified
    static.recalcTimestamp = False
    temp = dest.with_suffix(".tmp")
    static.save(temp)
    temp.replace(dest)


def make_supplement_font(name: str, dest: Path) -> None:
    """生成方正恒仿宋的补字字体，只含 FANGSONG_SUPPLEMENT 里的字；同一版本的 FontTools 每次生成的文件逐字节相同。"""
    from fontTools import subset
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont
    src, _ = SUPPLEMENT_FONTS[name]
    font = TTFont(FONTS / src)
    cmap, gs, glyf = font.getBestCmap(), font.getGlyphSet(), font["glyf"]
    order = font.getGlyphOrder()
    half = font["head"].unitsPerEm / 2
    mapping = {}
    for ch, recipe in FANGSONG_SUPPLEMENT.items():
        if isinstance(recipe, str):
            mapping[ord(ch)] = cmap[ord(recipe)]
            continue
        pen = TTGlyphPen(gs)
        for donor, part, *box in recipe:
            rec, contour, chosen = RecordingPen(), [], []
            gs[cmap[ord(donor)]].draw(rec)
            for op, args in rec.value:
                contour.append((op, args))
                if op in ("closePath", "endPath"):
                    bounds = BoundsPen(gs)
                    for o, a in contour:
                        getattr(bounds, o)(*a)
                    x0, y0, x1, y1 = bounds.bounds
                    if part == "all" or ((x0 + x1) / 2 < half) == (part == "left"):
                        chosen.append((contour, bounds.bounds))
                    contour = []
            target = pen
            if box:
                (x0, x1, y0, y1), (bx0, by0) = box[0], (min(b[0] for _, b in chosen), min(b[1] for _, b in chosen))
                sx = (x1 - x0) / (max(b[2] for _, b in chosen) - bx0)
                sy = (y1 - y0) / (max(b[3] for _, b in chosen) - by0)
                target = TransformPen(pen, (sx, 0, 0, sy, x0 - bx0 * sx, y0 - by0 * sy))
            for c, _ in chosen:
                for o, a in c:
                    getattr(target, o)(*a)
        glyph, first = f"uni{ord(ch):04X}", cmap[ord(recipe[0][0])]
        order.append(glyph)
        glyf.glyphOrder = order
        glyf.glyphs[glyph] = pen.glyph()
        glyf[glyph].recalcBounds(glyf)
        font["hmtx"][glyph] = (font["hmtx"][first][0], glyf[glyph].xMin)
        if "vmtx" in font:                     # 竖排度量照搬第一个部件所在的字，按字顶高差调整
            adv, tsb = font["vmtx"][first]
            font["vmtx"][glyph] = (adv, tsb + glyf[first].yMax - glyf[glyph].yMax)
        mapping[ord(ch)] = glyph
    font.setGlyphOrder(order)
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap.update(mapping)
    options = subset.Options()
    options.layout_features, options.name_IDs, options.notdef_outline = [], ["*"], True
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=mapping)
    subsetter.subset(font)
    _set_names(font, "YZ FangSong Supplement", "Regular" if src.endswith("-R.TTF") else "Medium")
    font.recalcTimestamp = False
    temp = dest.with_suffix(".tmp")
    font.save(temp)
    temp.replace(dest)


def prepare_fonts() -> None:
    """补齐缺失的静态字重与补字字体，再核对全部字体指纹。"""
    check_requirements()
    for name, make in [*((n, make_static_font) for n in INSTANCES),
                       *((n, make_supplement_font) for n in SUPPLEMENT_FONTS)]:
        dest = FONTS / name
        if not dest.is_file():
            print("生成字体：", name)
            make(name, dest)
    check_fonts()


def require_single_page(paths: list[Path]) -> None:
    import pymupdf              # 在这里才导入：本模块须在依赖装好之前就能载入，好先做 check_requirements()
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"缺少拼页文件：{path}；请先运行 python 排版/封面/build.py")
    for path in paths:
        with pymupdf.open(path) as doc:
            if doc.page_count != 1 or doc.is_encrypted:
                raise ValueError(f"拼页文件须为未加密的单页 PDF：{path}")
            rect = doc[0].rect
            if abs(rect.width - 210 * 72 / 25.4) > 1 or abs(rect.height - 297 * 72 / 25.4) > 1:
                raise ValueError(f"拼页文件须为 A4 竖页：{path}")


def source_snapshot(root: Path = ROOT) -> dict[str, str]:
    """来源目录里每个文件的指纹。"""
    out = {}
    for folder in SOURCE_DIRS:
        for path in sorted((root / folder).rglob("*")):
            if path.is_file():
                out[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


@contextmanager
def sources_unchanged(root: Path = ROOT):
    """构建前后比对来源目录；构建改动、增删了其中的文件就报错。"""
    before = source_snapshot(root)
    yield
    after = source_snapshot(root)
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    if changed:
        raise RuntimeError("构建改动了来源文件：" + "、".join(changed))
