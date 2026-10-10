"""构建前后的检查与准备：依赖版本、字体（生成静态字重并校验指纹）、PDF 只嵌入仓库字体、拼页用的单页 PDF，
以及来源稿保护。"""
from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from functools import lru_cache
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

# 方正恒仿宋缺的字。值为一个字：借用它的字形；值为 (甲, 乙)：左右结构，左部件取自甲，右部件取自乙。
# 拼法：甲、乙的轮廓按中心横坐标排序，在相邻中心相差最大处分开左右部件，部件都留在原位；右部件挤到左部件时，
# 才以右缘为准横向收窄，收到与甲自身左右部件间的最小间隙相同为止，高度不变。所以乙宜选右部件宽窄相近的
# 左右结构字，收窄得越少，竖笔越不会变细。出现新的缺字时排版前的查字会报错，在这里补一条即可。
FANGSONG_SUPPLEMENT = {
    "・": "·",              # 《鄞年・思叙》：借用「·」
    "晅": ("暄", "恒"),     # 日 + 亘，不用收窄
    "臙": ("胭", "嬿"),     # 月 + 燕：「嬿」里的「燕」本就比单字窄，只需收到约 0.85
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
    """按 manifest.json 逐一核对字体指纹，缺失或不一致时报错。构建时生成的字体（静态字重与补字）不一致，
    多半是拉取了改动生成方式的提交，删掉后重新运行即会重新生成；其余字体须从仓库恢复。"""
    expected = json.loads((FONTS / "manifest.json").read_text(encoding="utf-8"))
    errors = []
    for name, digest in expected.items():
        path = FONTS / name
        fix = "删掉后重新运行即可重新生成" if name in INSTANCES or name in SUPPLEMENT_FONTS else "请从仓库恢复"
        if not path.is_file():
            errors.append(f"缺少字体：{path}；{fix}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            errors.append(f"字体版本不符：{path}；{fix}")
    if errors:
        raise RuntimeError("\n".join(errors))


@lru_cache(maxsize=None)
def repo_font_names(fonts: Path = FONTS) -> frozenset[str]:
    """manifest.json 所列字体（含构建时生成的）的 PostScript 名。Chromium 把字体嵌入 PDF 时用的就是这个名字，
    前面另加「ABCDEF+」形式的子集标记。"""
    from fontTools.ttLib import TTFont
    names = json.loads((fonts / "manifest.json").read_text(encoding="utf-8"))
    return frozenset(TTFont(fonts / name, lazy=True)["name"].getDebugName(6) for name in names)


def check_pdf_fonts(path: Path) -> None:
    """Chromium 输出的 PDF 只能嵌入仓库字体。仓库字体缺字时，Chromium 会悄悄换用本机字体，各台机器装的字体不同，
    印出来的字形和版面也就不同；Type 3 字体（可变字体和 CFF 轮廓的字体会被打印成这种）印刷预检容易报错。
    出现这两种字体就报错，列出页码和用到它们的文字。"""
    import pymupdf              # 在这里才导入：本模块须在依赖装好之前就能载入，好先做 check_requirements()
    allowed = repo_font_names()
    pages: dict[tuple[str, str], set[int]] = {}
    samples: dict[str, str] = {}
    with pymupdf.open(path) as doc:
        for page in doc:
            bad = set()
            for _, _, kind, basefont, *_ in page.get_fonts(full=True):
                name = re.sub(r"^[A-Z]{6}\+", "", basefont)
                if kind == "Type3" or name not in allowed:
                    pages.setdefault((name, kind), set()).add(page.number + 1)
                    bad.add(name)
            if not bad:
                continue
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        # PyMuPDF 报告的字体名去掉了子集标记，过长时还会截断
                        font = re.sub(r"^[A-Z]{6}\+", "", span["font"])
                        for name in bad:
                            if font and name.startswith(font) and len(samples.get(name, "")) < 20:
                                samples[name] = samples.get(name, "") + span["text"].strip()
    if pages:
        lines = []
        for (name, kind), nums in sorted(pages.items()):
            where = "、".join(str(n) for n in sorted(nums)[:10]) + ("等" if len(nums) > 10 else "")
            sample = samples.get(name, "")[:20]
            lines.append(f"  {name or '无名字体'}（{kind}）：第 {where} 页" + (f"，如「{sample}」" if sample else ""))
        raise RuntimeError(f"{path.name} 里有仓库以外的字体或 Type 3 字体：\n" + "\n".join(lines) +
                           "\n多半是仓库字体缺字，Chromium 换用了本机字体：方正恒仿宋缺的字在 preflight.py 的 "
                           "FANGSONG_SUPPLEMENT 里补上，其他字体缺字须换用有这个字的字体")


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
    from fontTools.pens.basePen import BasePen
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont

    class Polyline(BasePen):
        """轮廓压成折线（二次曲线每段取 8 点），用来量每一行墨迹的左右边缘。"""
        def __init__(self, glyphs):
            super().__init__(glyphs)
            self.points = []

        def _moveTo(self, p):
            self.points = [p]

        def _lineTo(self, p):
            self.points.append(p)

        def _qCurveToOne(self, p1, p2):
            (x0, y0) = self.points[-1]
            self.points += [((1 - t) ** 2 * x0 + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
                             (1 - t) ** 2 * y0 + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
                            for t in (i / 8 for i in range(1, 9))]

    src, _ = SUPPLEMENT_FONTS[name]
    font = TTFont(FONTS / src)
    cmap, gs, glyf = font.getBestCmap(), font.getGlyphSet(), font["glyf"]
    order = font.getGlyphOrder()
    rows = range(font["head"].yMin, font["head"].yMax, 5)

    def halves(ch):
        """一个字的轮廓按中心横坐标排序，在相邻中心相差最大处分成左右两个部件，每个轮廓为 (绘制步骤, 折线)。"""
        rec, steps, contours = RecordingPen(), [], []
        gs[cmap[ord(ch)]].draw(rec)
        for op, args in rec.value:
            steps.append((op, args))
            if op in ("closePath", "endPath"):
                line = Polyline(gs)
                for o, a in steps:
                    getattr(line, o)(*a)
                xs = [x for x, _ in line.points]
                contours.append(((min(xs) + max(xs)) / 2, steps, line.points))
                steps = []
        centers = sorted(c[0] for c in contours)
        k = max(range(1, len(centers)), key=lambda i: centers[i] - centers[i - 1])
        split = (centers[k - 1] + centers[k]) / 2
        return [c[1:] for c in contours if c[0] < split], [c[1:] for c in contours if c[0] > split]

    def edge(part, y, pick):
        """部件在高度 y 那一行墨迹的最左（pick=min）或最右（pick=max）横坐标；这一行没有墨迹时为 None。"""
        xs = [x0 + (y - y0) * (x1 - x0) / (y1 - y0)
              for _, line in part for (x0, y0), (x1, y1) in zip(line, line[1:] + line[:1])
              if y0 <= y < y1 or y1 <= y < y0]
        return pick(xs) if xs else None

    def gaps(left, right):
        """逐行量左部件右缘与右部件左缘：[(左部件右缘, 右部件左缘)]。"""
        pairs = [(edge(left, y, max), edge(right, y, min)) for y in rows]
        return [(l, r) for l, r in pairs if l is not None and r is not None]

    mapping = {}
    for ch, recipe in FANGSONG_SUPPLEMENT.items():
        if isinstance(recipe, str):
            mapping[ord(ch)] = cmap[ord(recipe)]
            continue
        left, own_right = halves(recipe[0])
        right = halves(recipe[1])[1]
        clearance = min(r - l for l, r in gaps(left, own_right))
        x_end = max(x for _, line in right for x, _ in line)
        scale = min([1.0] + [(x_end - l - clearance) / (x_end - r) for l, r in gaps(left, right) if r < x_end])
        pen = TTGlyphPen(gs)
        for steps, _ in left:
            for o, a in steps:
                getattr(pen, o)(*a)
        narrowed = TransformPen(pen, (scale, 0, 0, 1, x_end * (1 - scale), 0))
        for steps, _ in right:
            for o, a in steps:
                getattr(narrowed, o)(*a)
        glyph, first = f"uni{ord(ch):04X}", cmap[ord(recipe[0])]
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
