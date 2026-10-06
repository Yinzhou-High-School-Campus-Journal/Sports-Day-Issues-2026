"""线描插图生成器：沿用封面画风（黑色描线、白色遮挡、等高线式云海），按版面尺寸输出 SVG。

每个图样是一个函数 f(w, h, seed, **参数)，w、h 以 pt 计，返回 SVG 字符串。
坐标单位即 pt；主线 0.85 pt，次线 0.5 pt，细线 0.34 pt，与封面一致。
"""
from __future__ import annotations

import math
import random
from functools import lru_cache
from pathlib import Path

MAIN, THIN, HAIR = 0.85, 0.5, 0.34
HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------- 基础工具

class Canvas:
    def __init__(self, w: float, h: float):
        self.w, self.h = w, h
        self.parts: list[str] = []
        self.defs: list[str] = []

    def add(self, s: str) -> None:
        self.parts.append(s)

    def path(self, d: str, sw: float = MAIN, fill: str = "none", stroke: str = "#000", extra: str = "") -> None:
        st = f' stroke="{stroke}" stroke-width="{sw:.2f}"' if sw else ' stroke="none"'
        self.parts.append(f'<path d="{d}" fill="{fill}"{st}{extra}/>')

    def svg(self) -> str:
        defs = f"<defs>{''.join(self.defs)}</defs>" if self.defs else ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w:.2f} {self.h:.2f}" '
                f'width="{self.w:.2f}pt" height="{self.h:.2f}pt" stroke-linecap="round" stroke-linejoin="round">'
                f'{defs}<rect width="100%" height="100%" fill="#fff"/>{"".join(self.parts)}</svg>')


def f2(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def poly(pts, closed: bool = False) -> str:
    d = "M" + " L".join(f"{f2(x)},{f2(y)}" for x, y in pts)
    return d + ("Z" if closed else "")


def smooth(pts, closed: bool = False, t: float = 1.0) -> str:
    """Catmull-Rom 样条转三次贝塞尔。"""
    n = len(pts)
    if n < 3:
        return poly(pts, closed)
    P = list(pts)
    d = [f"M{f2(P[0][0])},{f2(P[0][1])}"]
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = P[(i - 1) % n] if (closed or i > 0) else P[i]
        p1 = P[i]
        p2 = P[(i + 1) % n]
        p3 = P[(i + 2) % n] if (closed or i + 2 < n) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) * t / 6, p1[1] + (p2[1] - p0[1]) * t / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) * t / 6, p2[1] - (p3[1] - p1[1]) * t / 6)
        d.append(f"C{f2(c1[0])},{f2(c1[1])} {f2(c2[0])},{f2(c2[1])} {f2(p2[0])},{f2(p2[1])}")
    return "".join(d) + ("Z" if closed else "")


def streak(c: Canvas, x0, y0, x1, y1, thick=1.6) -> None:
    """封面上那种两头尖的细长笔触（天空里的风线）。"""
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    L = math.hypot(x1 - x0, y1 - y0) or 1
    nx, ny = -(y1 - y0) / L, (x1 - x0) / L
    a = (mx + nx * thick, my + ny * thick)
    b = (mx - nx * thick * 0.35, my - ny * thick * 0.35)
    c.path(f"M{f2(x0)},{f2(y0)} Q{f2(a[0])},{f2(a[1])} {f2(x1)},{f2(y1)} "
           f"Q{f2(b[0])},{f2(b[1])} {f2(x0)},{f2(y0)}Z", sw=0, fill="#000")


def circle(c: Canvas, cx, cy, r, sw=MAIN, fill="#fff") -> None:
    c.add(f'<circle cx="{f2(cx)}" cy="{f2(cy)}" r="{f2(r)}" fill="{fill}" stroke="#000" stroke-width="{sw}"/>')


# ---------------------------------------------------------------- 等高线云海

class Terrain:
    """左右（x，pt）× 前后（z，0 远 → 1 近）的地形，由若干圆顶叠成；取各圆顶高度的最大值。"""

    def __init__(self, rng: random.Random, w: float, amp: float = 1.0, density: float = 1.0,
                 avoid: tuple[float, float] | None = None, puffy: bool = True):
        self.domes = []
        n = max(10, round(density * 64 * w / 441))
        made = 0
        for _ in range(n * 4):
            if made >= n:
                break
            z = rng.random() ** 0.62                      # 近处多、远处少
            s = self.scale(z)
            x = rng.uniform(-0.08 * w, 1.08 * w)
            if avoid and avoid[0] - 30 * s < x < avoid[1] + 30 * s:
                continue
            made += 1
            rx = rng.uniform(30, 92) * s
            rz = rng.uniform(0.05, 0.14)
            hh = rng.uniform(11, 32) * s * amp
            self.domes.append((x, z, rx, rz, hh))
            if puffy and rng.random() < 0.8:              # 顶上再长出小云团
                for _ in range(rng.randint(1, 3)):
                    self.domes.append((x + rng.uniform(-0.6, 0.6) * rx, z + rng.uniform(-0.3, 0.3) * rz,
                                       rx * rng.uniform(0.35, 0.55), rz * rng.uniform(0.4, 0.6),
                                       hh * rng.uniform(1.05, 1.35)))

    @staticmethod
    def scale(z: float) -> float:
        return 0.22 + 0.78 * z

    def height(self, x: float, z: float) -> float:
        v = 0.0
        for dx, dz, rx, rz, hh in self.domes:
            u = ((x - dx) / rx) ** 2 + ((z - dz) / rz) ** 2
            if u < 1:
                v = max(v, hh * (1 - u) ** 0.5)
        return v


def ridge_rows(c: Canvas, x0: float, x1: float, y_top: float, y_bot: float, rows: int, rng: random.Random,
               amp: float = 1.0, density: float = 1.0, avoid=None, sw_far=HAIR, sw_near=MAIN, persp=1.6,
               clip_poly: str | None = None, step: float = 1.5, puffy: bool = True) -> list[float]:
    """一排排水平线被圆顶地形顶起、前排白色遮住后排——封面云海、山峦的画法。返回各排基线 y。"""
    w = x1 - x0
    terr = Terrain(rng, w, amp=amp, density=density, puffy=puffy,
                   avoid=None if avoid is None else (avoid[0] - x0, avoid[1] - x0))
    ys = []
    cp = f' clip-path="url(#{clip_poly})"' if clip_poly else ""
    for i in range(rows):
        z = i / max(rows - 1, 1)
        y = y_top + (y_bot - y_top) * (z ** persp)
        ys.append(y)
        pts = []
        x = 0.0
        while x <= w + step:
            pts.append((x0 + x, y - terr.height(x, z)))
            x += step
        sw = sw_far + (sw_near - sw_far) * min(1, z * 1.3)
        top = poly(pts)
        area = top + f" L{f2(x1)},{f2(y_bot + 400)} L{f2(x0)},{f2(y_bot + 400)}Z"
        c.add(f'<path d="{area}" fill="#fff" stroke="none"{cp}/>')
        c.add(f'<path d="{top}" fill="none" stroke="#000" stroke-width="{sw:.2f}"{cp}/>')
    return ys


# ---------------------------------------------------------------- 图样

def cloudsea(w: float, h: float, seed: int = 1, sun: bool = True, horizon: float = 0.34,
             sun_x: float = 0.62, streaks: int = 3, rows: int | None = None) -> str:
    """云海日出：天空风线、半没于云的太阳、层层云海。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    hy = h * horizon
    if sun:
        r = min(w * 0.11, h * 0.22)
        circle(c, w * sun_x, hy + r * 0.25, r)
    for k in range(streaks):
        y = hy * rng.uniform(0.25, 0.85)
        x0 = w * rng.uniform(0.05, 0.55)
        L = w * rng.uniform(0.22, 0.4)
        streak(c, x0, y + 4, x0 + L, y - 5, thick=rng.uniform(1.0, 1.8))
    n = rows or max(16, round((h - hy) / 4.2))
    ridge_rows(c, 0, w, hy, h + 6, n, rng, amp=0.8 + h / 500, persp=1.7)
    return c.svg()


def seawaves(w: float, h: float, seed: int = 2, horizon: float = 0.42, sun: bool = True, birds: int = 0) -> str:
    """海面落日：波纹由远及近渐疏，太阳半沉，水面拖出倒影短线。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    hy = h * horizon
    r = min(w * 0.12, h * 0.2)
    sx = w * 0.5
    if sun:
        circle(c, sx, hy, r)
        c.add(f'<rect x="0" y="{f2(hy)}" width="{f2(w)}" height="{f2(h - hy)}" fill="#fff"/>')
    for k in range(3):
        y = hy * rng.uniform(0.2, 0.7)
        x0 = w * rng.uniform(0.02, 0.3) if k % 2 == 0 else w * rng.uniform(0.6, 0.75)
        streak(c, x0, y + 3, x0 + w * rng.uniform(0.18, 0.3), y - 3, thick=rng.uniform(0.9, 1.5))
    for _ in range(birds):
        bird(c, rng.uniform(0.1, 0.9) * w, rng.uniform(0.15, 0.7) * hy, rng.uniform(4, 8), rng)
    c.path(f"M0,{f2(hy)} L{f2(w)},{f2(hy)}", sw=MAIN)
    n = max(12, round((h - hy) / 6))
    for i in range(1, n + 1):
        t = i / n
        y = hy + (h - hy) * t ** 1.7
        amp = 0.6 + 3.2 * t
        wl = 18 + 60 * t
        ph = rng.uniform(0, math.tau)
        pts = [(x, y + amp * math.sin(x / wl * math.tau + ph) * (0.6 + 0.4 * math.sin(x / (wl * 3.7) + ph)))
               for x in frange(0, w, 2)]
        sw = HAIR + (MAIN - HAIR) * t
        # 倒影：太阳正下方的波纹断开成短线
        if sun and t < 0.8:
            half = r * (0.9 - 0.7 * t) * (1 + 0.4 * math.sin(i * 1.7))
            left = [p for p in pts if p[0] < sx - half]
            right = [p for p in pts if p[0] > sx + half]
            for seg in (left, right):
                if len(seg) > 1:
                    c.path(poly(seg), sw=sw)
            dash = [p for p in pts if sx - half * 0.55 < p[0] < sx + half * 0.55]
            if len(dash) > 1 and i % 2 == 0:
                c.path(poly(dash), sw=sw)
        else:
            c.path(poly(pts), sw=sw)
    return c.svg()


def frange(a: float, b: float, s: float):
    x = a
    while x <= b + 1e-9:
        yield x
        x += s


def bird(c: Canvas, x: float, y: float, s: float, rng: random.Random, sw: float = THIN) -> None:
    lift = rng.uniform(0.3, 0.8)
    c.path(f"M{f2(x - s)},{f2(y - s * lift)} Q{f2(x - s * 0.45)},{f2(y - s * 0.55)} {f2(x)},{f2(y)} "
           f"Q{f2(x + s * 0.45)},{f2(y - s * 0.6)} {f2(x + s)},{f2(y - s * lift * 1.1)}", sw=sw)


def ginkgo_leaf(c: Canvas, x: float, y: float, s: float, ang: float, sw: float = THIN) -> None:
    """银杏叶：扇形叶片、顶端浅缺口、细叶脉、弯曲叶柄；(x, y) 为叶柄末端，ang 为朝向。"""
    ca, sa = math.cos(ang), math.sin(ang)

    def tr(px, py):
        return (x + px * ca - py * sa, y + px * sa + py * ca)

    stem = 0.75 * s
    bx, by = 0.0, -stem
    arc = []
    for k in range(25):
        a = math.radians(-66 + 132 * k / 24)
        rr = s * (0.93 + 0.07 * math.cos(a * 3.2))
        if abs(k - 12) < 1.5:
            rr *= 0.86                                  # 中间的浅缺口
        arc.append((bx + rr * math.sin(a), by - rr * math.cos(a)))
    left = (bx - 0.12 * s, by - 0.1 * s)
    right = (bx + 0.12 * s, by - 0.1 * s)
    d = (f"M{f2(tr(bx, by)[0])},{f2(tr(bx, by)[1])} L{f2(tr(*left)[0])},{f2(tr(*left)[1])} "
         + smooth([tr(*p) for p in [left] + arc + [right]], t=0.9)[1:].replace("M", "L", 1)
         + f" L{f2(tr(bx, by)[0])},{f2(tr(bx, by)[1])}Z")
    c.path(d, sw=sw, fill="#fff")
    for k in range(1, 10):
        a = math.radians(-60 + 120 * k / 10)
        e = (bx + 0.8 * s * math.sin(a), by - 0.8 * s * math.cos(a))
        p0, p1 = tr(bx, by - 0.1 * s), tr(*e)
        c.path(f"M{f2(p0[0])},{f2(p0[1])} L{f2(p1[0])},{f2(p1[1])}", sw=HAIR * 0.8)
    p0, p1 = tr(0, 0), tr(bx, by)
    m = tr(0.12 * s, -stem * 0.5)
    c.path(f"M{f2(p0[0])},{f2(p0[1])} Q{f2(m[0])},{f2(m[1])} {f2(p1[0])},{f2(p1[1])}", sw=sw)


def ginkgo(w: float, h: float, seed: int = 3, count: int | None = None, ground: bool = True) -> str:
    """飘落的银杏叶，下方几道等高线托底。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    gy = h * 0.8 if ground else h + 10
    if ground:
        ridge_rows(c, 0, w, gy, h + 4, max(4, round((h - gy) / 6)), rng, amp=0.35, persp=1.3)
    n = count or max(4, round(w * h / 7800))
    placed = []
    for _ in range(n * 20):
        if len(placed) >= n:
            break
        s = rng.uniform(11, 24) if rng.random() < 0.8 else rng.uniform(26, 34)
        x = rng.uniform(s, w - s)
        y = rng.uniform(s * 1.8, gy - s * 0.4)
        if any(math.hypot(x - px, y - py) < (s + ps) * 1.25 for px, py, ps in placed):
            continue
        placed.append((x, y, s))
    for x, y, s in placed:
        ginkgo_leaf(c, x, y, s, rng.uniform(-2.4, 2.4))
    for x, y, s in rng.sample(placed, k=min(3, len(placed))):
        streak(c, x - s * 3.2, y - s * 1.9, x - s * 1.4, y - s * 1.1, thick=0.6)
    return c.svg()


def track(w: float, h: float, seed: int = 4, horizon: float = 0.3, lanes: int = 6, sun: bool = True,
          start_line: bool = True) -> str:
    """透视跑道伸向远方，两侧等高线云海，远处落日。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    hy = h * horizon
    vx = w * 0.5
    if sun:
        r = min(w * 0.08, h * 0.16)
        circle(c, w * 0.7, hy - r * 0.35, r)
        streak(c, w * 0.48, hy - r * 1.3, w * 0.88, hy - r * 1.55, thick=1.2)
        streak(c, w * 0.08, hy * 0.45, w * 0.36, hy * 0.35, thick=1.0)
    c.path(f"M0,{f2(hy)} L{f2(w)},{f2(hy)}", sw=THIN)
    # 跑道在底边的宽度与远端宽度
    bw = w * 0.62
    tw = w * 0.05
    bl, br = vx - bw / 2, vx + bw / 2
    tl, trr = vx - tw / 2, vx + tw / 2
    c.defs.append(f'<clipPath id="side"><path d="M0,0 L{f2(w)},0 L{f2(w)},{f2(h)} L{f2(br)},{f2(h + 1)} '
                  f'L{f2(trr)},{f2(hy)} L{f2(tl)},{f2(hy)} L{f2(bl)},{f2(h + 1)} L0,{f2(h)}Z"/></clipPath>')
    ridge_rows(c, 0, w, hy, h + 6, max(16, round((h - hy) / 4.2)), rng, amp=0.8 + h / 500, persp=1.7,
               clip_poly="side", avoid=(tl - 20, trr + 20))
    # 跑道
    c.path(poly([(bl, h + 1), (tl, hy), (trr, hy), (br, h + 1)], closed=True), sw=0, fill="#fff")
    for k in range(lanes + 1):
        u = k / lanes
        xb = bl + (br - bl) * u
        xt = tl + (trr - tl) * u
        sw = MAIN if k in (0, lanes) else THIN
        c.path(f"M{f2(xb)},{f2(h + 1)} L{f2(xt)},{f2(hy)}", sw=sw)
    if start_line:
        y = h - (h - hy) * 0.14
        f = (y - hy) / (h - hy)
        xl = tl + (bl - tl) * f
        xr = trr + (br - trr) * f
        c.path(f"M{f2(xl)},{f2(y)} L{f2(xr)},{f2(y)}", sw=MAIN)
        y2 = h - (h - hy) * 0.07
        f2_ = (y2 - hy) / (h - hy)
        c.path(f"M{f2(tl + (bl - tl) * f2_)},{f2(y2)} L{f2(trr + (br - trr) * f2_)},{f2(y2)}", sw=THIN)
    return c.svg()


def stars(c: Canvas, rng: random.Random, n: int, x0: float, x1: float, y0: float, y1: float) -> None:
    for _ in range(n):
        x, y, s = rng.uniform(x0, x1), rng.uniform(y0, y1), rng.uniform(1.2, 2.6)
        c.path(f"M{f2(x - s)},{f2(y)} L{f2(x + s)},{f2(y)} M{f2(x)},{f2(y - s)} L{f2(x)},{f2(y + s)}", sw=HAIR)


def brick_wall(c: Canvas, x0: float, y0: float, x1: float, y1: float, course: float = 5.2) -> None:
    c.path(poly([(x0, y1), (x0, y0), (x1, y0), (x1, y1)], closed=True), sw=MAIN, fill="#fff")
    y, row = y0 + course, 0
    while y < y1 - 0.5:
        c.path(f"M{f2(x0)},{f2(y)} L{f2(x1)},{f2(y)}", sw=HAIR)
        y += course
    y, row = y0, 0
    while y < y1 - 0.5:
        off = (row % 2) * course * 1.1
        x = x0 + off + course * 2.2
        while x < x1 - 1:
            c.path(f"M{f2(x)},{f2(y)} L{f2(x)},{f2(min(y + course, y1))}", sw=HAIR)
            x += course * 2.2
        y += course
        row += 1


def cat_back(c: Canvas, x: float, y: float, s: float) -> None:
    """坐着的猫的背影，(x, y) 为底边中点。"""
    pts = [(-0.42, 0), (-0.47, -0.35), (-0.36, -0.7), (-0.22, -0.9), (-0.25, -1.12), (-0.2, -1.38),
           (-0.12, -1.25), (0.0, -1.3), (0.12, -1.25), (0.2, -1.38), (0.25, -1.12), (0.22, -0.9),
           (0.34, -0.72), (0.46, -0.36), (0.44, 0)]
    c.path(smooth([(x + px * s, y + py * s) for px, py in pts], t=0.7) + "Z", sw=MAIN, fill="#fff")
    c.path(f"M{f2(x + 0.42 * s)},{f2(y - 0.03 * s)} C{f2(x + 0.75 * s)},{f2(y - 0.02 * s)} "
           f"{f2(x + 0.8 * s)},{f2(y - 0.35 * s)} {f2(x + 0.62 * s)},{f2(y - 0.5 * s)}", sw=MAIN)


def clock_tower(c: Canvas, x: float, y_bot: float, H: float) -> float:
    """按封面样式画鄞中钟楼：顶部缺口、方框钟面、成对小窗、右侧竖条侧板。x 为左边，返回总宽。"""
    W = 0.21 * H
    P = 0.072 * H
    top = y_bot - H
    # 侧板
    c.path(poly([(x + W, y_bot), (x + W, top + 0.02 * H), (x + W + P, top + 0.02 * H), (x + W + P, y_bot)], closed=True),
           sw=MAIN, fill="#fff")
    c.path(poly([(x + W + P * 0.32, top + 0.1 * H), (x + W + P * 0.68, top + 0.1 * H),
                 (x + W + P * 0.68, top + 0.36 * H), (x + W + P * 0.32, top + 0.36 * H)], closed=True), sw=0, fill="#000")
    y = top + 0.42 * H
    while y < y_bot - 0.5:
        c.path(f"M{f2(x + W)},{f2(y)} L{f2(x + W + P)},{f2(y)}", sw=HAIR)
        y += max(1.6, H * 0.011)
    # 主体与顶部缺口
    nw, nd = 0.22 * W, 0.022 * H
    c.path(poly([(x, y_bot), (x, top), (x + W / 2 - nw / 2, top), (x + W / 2 - nw / 2, top + nd),
                 (x + W / 2 + nw / 2, top + nd), (x + W / 2 + nw / 2, top), (x + W, top), (x + W, y_bot)], closed=True),
           sw=MAIN, fill="#fff")
    # 钟面
    cs = 0.46 * W
    cx, cy = x + W / 2, top + 0.105 * H
    c.path(poly([(cx - cs / 2, cy - cs / 2), (cx + cs / 2, cy - cs / 2), (cx + cs / 2, cy + cs / 2),
                 (cx - cs / 2, cy + cs / 2)], closed=True), sw=MAIN, fill="#fff")
    circle(c, cx, cy, cs * 0.36, sw=MAIN)
    circle(c, cx, cy, cs * 0.27, sw=THIN)
    # 成对小窗
    sq = 0.075 * W
    y = top + 0.3 * H
    while y < y_bot - 0.03 * H:
        for colx in (x + 0.22 * W, x + 0.62 * W):
            for k in (0, 1):
                xx = colx + k * sq * 1.7
                c.path(poly([(xx, y), (xx + sq, y), (xx + sq, y + sq), (xx, y + sq)], closed=True), sw=0, fill="#000")
        y += 0.052 * H
    return W + P


def building(c: Canvas, x0: float, x1: float, y_top: float, y_bot: float, slit: float = 5.0) -> None:
    """封面式教学楼：屋檐横带 + 一排排竖向窗条。"""
    c.path(poly([(x0, y_bot), (x0, y_top), (x1, y_top), (x1, y_bot)], closed=True), sw=MAIN, fill="#fff")
    band = min(9.0, (y_bot - y_top) * 0.16)
    c.path(f"M{f2(x0)},{f2(y_top + band)} L{f2(x1)},{f2(y_top + band)}", sw=THIN)
    c.path(f"M{f2(x0)},{f2(y_top + band * 0.45)} L{f2(x1)},{f2(y_top + band * 0.45)}", sw=HAIR)
    rows = max(1, int((y_bot - y_top - band) / (band * 2.2)))
    for r in range(rows):
        ya = y_top + band * 1.6 + r * band * 2.2
        yb = ya + band * 1.2
        if yb > y_bot - 2:
            break
        x = x0 + slit
        while x < x1 - slit * 0.6:
            c.path(f"M{f2(x)},{f2(ya)} L{f2(x)},{f2(yb)}", sw=HAIR * 1.3)
            x += slit


def tower(w: float, h: float, seed: int = 5, birds_n: int = 0, wall: bool = False, sun: bool = False,
          cat: bool = False, night: bool = False, leaves: int = 0, campus: bool = False, tx: float | None = None) -> str:
    """鄞中钟楼配飞鸟、红墙、落日、草地上的猫、星星或银杏叶；campus=True 时两侧加教学楼。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    ground = h * 0.8
    H = min(h * 0.72, w * 0.62)                    # 钟楼高，顶上留白
    txx = w * (tx if tx is not None else (0.26 if (cat or wall) else 0.5)) - 0.141 * H
    if sun:
        r = min(h * 0.2, w * 0.14)
        circle(c, w * 0.68, ground - r * 0.5, r)
        streak(c, w * 0.5, ground - r * 1.6, w * 0.92, ground - r * 1.85, thick=1.3)
    if night:
        stars(c, rng, round(w * h / 5200), w * 0.45, w, 0, h * 0.35)
        c.path(f"M{f2(w * 0.8)},{f2(h * 0.1)} L{f2(w * 0.85)},{f2(h * 0.088)}", sw=THIN)
    if campus:
        building(c, -4, txx - w * 0.01, ground - H * 0.34, ground + 4)
        building(c, txx + 0.29 * H + w * 0.03, w * 0.74, ground - H * 0.26, ground + 4, slit=4.2)
        building(c, w * 0.74, w + 4, ground - H * 0.2, ground + 4, slit=6)
    clock_tower(c, txx, ground + 4, H)
    if wall:
        brick_wall(c, -2, ground - h * 0.13, txx + 0.29 * H + w * 0.2, ground + 4)
    for _ in range(birds_n):
        bird(c, rng.uniform(0.48, 0.95) * w, rng.uniform(0.1, 0.6) * h, rng.uniform(4, 9), rng, sw=THIN)
    rows = max(8, round((h - ground) / 3.6))
    ridge_rows(c, 0, w, ground, h + 4, rows, rng, amp=0.55, density=0.8, persp=1.35)
    if cat:
        cat_back(c, w * 0.66, ground + (h - ground) * 0.55, min(h * 0.1, 30))
    for _ in range(leaves):
        s = rng.uniform(10, 22)
        ginkgo_leaf(c, rng.uniform(0.05, 0.95) * w, rng.uniform(0.08, 0.72) * h, s, rng.uniform(-2.4, 2.4))
    return c.svg()


# ---------------------------------------------------------------- 山峦

class Peaks(Terrain):
    """尖一些的山：圆锥形山头配圆顶小丘。"""

    def __init__(self, rng: random.Random, w: float, amp: float = 1.0, n: int = 9):
        self.domes = []
        for i in range(n):
            z = rng.uniform(0.02, 0.95) ** 0.8
            s = self.scale(z)
            self.domes.append((rng.uniform(-0.05, 1.05) * w, z, rng.uniform(55, 120) * s,
                               rng.uniform(0.08, 0.2), rng.uniform(35, 80) * s * amp, rng.uniform(1.2, 1.8)))

    def height(self, x: float, z: float) -> float:
        v = 0.0
        for dx, dz, rx, rz, hh, sharp in self.domes:
            u = ((x - dx) / rx) ** 2 + ((z - dz) / rz) ** 2
            if u < 1:
                v = max(v, hh * (1 - math.sqrt(u)) ** sharp * (1 + 0.05 * math.sin(x / 7 + dz * 40)))
        return v


def mountains(w: float, h: float, seed: int = 6, sun: bool = False, moon: bool = False, path: bool = False,
              horizon: float = 0.42, mist: bool = False, frame: bool = False, birds_n: int = 0) -> str:
    """山峦：等高线勾出的群山；可加日月、下山小路、山间雾带；frame=True 时画成墙上的一幅山水（卧游）。"""
    if frame:
        return framed_landscape(w, h, seed)
    rng = random.Random(seed)
    c = Canvas(w, h)
    hy = h * horizon
    if sun or moon:
        r = min(w * 0.07, h * 0.12)
        circle(c, w * 0.72, max(r + 3, hy - h * 0.2), r)
    for k in range(2):
        y = hy * rng.uniform(0.15, 0.5)
        x0 = w * rng.uniform(0.05, 0.4)
        streak(c, x0, y + 3, x0 + w * rng.uniform(0.2, 0.32), y - 3, thick=rng.uniform(0.9, 1.4))
    rows = max(18, round((h - hy) / 3.4))
    terr = Peaks(rng, w, amp=h / 260)
    fog = [(0.18, 0.34), (0.5, 0.64)] if mist else []
    for i in range(rows):
        z = i / (rows - 1)
        y = hy + (h + 6 - hy) * z ** 1.5
        hs = [(x, terr.height(x, z)) for x in frange(0, w, 1.5)]
        pts = [(x, y - v) for x, v in hs]
        sw = HAIR + (MAIN - HAIR) * min(1, z * 1.3)
        top = poly(pts)
        c.path(top + f" L{f2(w)},{f2(h + 50)} L0,{f2(h + 50)}Z", sw=0, fill="#fff")
        band = next(((a, b) for a, b in fog if a <= z <= b), None)
        if band:
            # 雾里：只有高出雾面的山头看得见
            depth = (z - band[0]) / (band[1] - band[0])
            cut = 4 + 26 * depth * h / 400
            seg = []
            for (x, v), q in zip(hs, pts):
                if v > cut:
                    seg.append(q)
                elif seg:
                    if len(seg) > 2:
                        c.path(poly(seg), sw=sw)
                    seg = []
            if len(seg) > 2:
                c.path(poly(seg), sw=sw)
        else:
            c.path(top, sw=sw)
    for _ in range(birds_n):
        bird(c, w * rng.uniform(0.15, 0.85), hy * rng.uniform(0.3, 0.9), rng.uniform(4, 8), rng)
    if path:
        # 蜿蜒的下山路：两条近乎平行的曲线，由远及近变宽
        pts_l, pts_r = [], []
        for k in range(40):
            t = k / 39
            y = hy + (h - hy) * (0.25 + 0.75 * t)
            cx = w * (0.5 + 0.18 * math.sin(t * 5.5 + 0.6) * (1 - 0.3 * t))
            half = 2 + 26 * t ** 1.6
            pts_l.append((cx - half, y))
            pts_r.append((cx + half, y))
        c.path(smooth(pts_l + pts_r[::-1], closed=True), sw=0, fill="#fff")
        c.path(smooth(pts_l), sw=MAIN)
        c.path(smooth(pts_r), sw=MAIN)
    return c.svg()


# ---------------------------------------------------------------- 明月、竹、雁

def bamboo(c: Canvas, x: float, y_bot: float, y_top: float, wid: float, rng: random.Random, lean: float = 0.0) -> None:
    n = rng.randint(5, 8)
    seg = (y_bot - y_top) / n
    for i in range(n):
        ya, yb = y_bot - i * seg, y_bot - (i + 1) * seg + 1.2
        xa, xb = x + lean * (y_bot - ya), x + lean * (y_bot - yb)
        c.path(poly([(xa - wid / 2, ya), (xb - wid / 2, yb), (xb + wid / 2, yb), (xa + wid / 2, ya)], closed=True),
               sw=MAIN, fill="#fff")
        c.path(f"M{f2(xb - wid * 0.7)},{f2(yb - 0.6)} L{f2(xb + wid * 0.7)},{f2(yb - 0.6)}", sw=THIN)


def bamboo_leaf(c: Canvas, x: float, y: float, L: float, ang: float) -> None:
    ca, sa = math.cos(ang), math.sin(ang)
    wd = L * 0.13
    tip = (x + L * ca, y + L * sa)
    m1 = (x + L * 0.45 * ca - wd * sa, y + L * 0.45 * sa + wd * ca)
    m2 = (x + L * 0.45 * ca + wd * sa, y + L * 0.45 * sa - wd * ca)
    c.path(f"M{f2(x)},{f2(y)} Q{f2(m1[0])},{f2(m1[1])} {f2(tip[0])},{f2(tip[1])} "
           f"Q{f2(m2[0])},{f2(m2[1])} {f2(x)},{f2(y)}Z", sw=THIN, fill="#fff")
    c.path(f"M{f2(x)},{f2(y)} L{f2(x + L * 0.8 * ca)},{f2(y + L * 0.8 * sa)}", sw=HAIR)


def moon_bamboo(w: float, h: float, seed: int = 8) -> str:
    """秋夜：明月、竹枝、一行雁，脚下几道云水纹。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    r = min(w, h) * 0.26
    mx, my = w * 0.63, h * 0.36
    circle(c, mx, my, r)
    for k in range(3):
        y = my + r * rng.uniform(-0.3, 0.6)
        x0 = mx - r * rng.uniform(1.1, 1.8)
        streak(c, x0, y + 2, x0 + r * rng.uniform(1.3, 2.2), y - 2, thick=rng.uniform(0.8, 1.3))
    # 雁阵
    gx, gy = mx - r * 0.2, my - r * 0.65
    for k in range(7):
        bird(c, gx + k * 13 - (k % 2) * 3, gy + abs(k - 3) * 6 + (k % 2) * 2, 4.2, rng, sw=THIN)
    ground = h * 0.84
    ridge_rows(c, 0, w, ground, h + 4, max(6, round((h - ground) / 4)), rng, amp=0.45, density=0.7, persp=1.3)
    # 竹子：左侧三竿，叶子成簇
    for i, (fx, lean) in enumerate([(0.12, 0.02), (0.2, -0.015), (0.27, 0.03)]):
        bamboo(c, w * fx, ground + 6, h * rng.uniform(0.02, 0.18), 5.2 - i * 0.8, rng, lean)
    for _ in range(9):
        bx = w * rng.uniform(0.1, 0.38)
        by = h * rng.uniform(0.08, 0.6)
        base_ang = rng.uniform(-0.2, 0.9) * math.pi
        for j in range(rng.randint(3, 5)):
            bamboo_leaf(c, bx, by, rng.uniform(22, 36), base_ang + (j - 2) * 0.35)
    return c.svg()


def moon_lake(w: float, h: float, seed: int = 9, snow: bool = False) -> str:
    """湖上：远山、湖心小亭、一叶扁舟，湖面细纹；默认有明月，snow=True 时是湖心亭看雪。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    hy = h * 0.5
    r = min(w, h) * 0.12
    if not snow:
        circle(c, w * 0.7, h * 0.18, r)
    streak(c, w * 0.08, h * 0.12, w * 0.4, h * 0.08, thick=1.1)
    # 远山（只画湖面以上）
    terr = Peaks(rng, w, amp=h / 420, n=7)
    rows = 14
    for i in range(rows):
        z = i / (rows - 1)
        y = h * 0.3 + (hy - h * 0.3) * z ** 1.2
        pts = [(x, y - terr.height(x, z) * 0.8) for x in frange(0, w, 1.5)]
        top = poly(pts)
        c.path(top + f" L{f2(w)},{f2(hy)} L0,{f2(hy)}Z", sw=0, fill="#fff")
        c.path(top, sw=HAIR + (THIN - HAIR) * z)
    c.path(f"M0,{f2(hy)} L{f2(w)},{f2(hy)}", sw=THIN)
    # 湖面细纹与月影
    for i in range(1, 26):
        t = i / 25
        y = hy + (h - hy) * t ** 1.5
        segs = rng.randint(3, 6)
        for _ in range(segs):
            x0 = rng.uniform(-20, w)
            L = rng.uniform(30, 120) * (0.5 + t)
            if abs(x0 + L / 2 - w * 0.7) < r * 0.8 and rng.random() < 0.7:
                continue
            c.path(f"M{f2(x0)},{f2(y)} L{f2(x0 + L)},{f2(y)}", sw=HAIR + (THIN - HAIR) * t)
    for i in range(0 if snow else 8):
        y = hy + 6 + i * (h - hy) * 0.07
        half = r * (0.9 - i * 0.08)
        c.path(f"M{f2(w * 0.7 - half)},{f2(y)} L{f2(w * 0.7 + half)},{f2(y)}", sw=THIN)
    # 湖心小岛与亭
    ix, iy = w * 0.28, hy + (h - hy) * 0.18
    c.path(f"M{f2(ix - 46)},{f2(iy)} Q{f2(ix)},{f2(iy - 12)} {f2(ix + 50)},{f2(iy)}Z", sw=MAIN, fill="#fff")
    px, py = ix - 4, iy - 7
    c.path(f"M{f2(px - 9)},{f2(py)} L{f2(px - 9)},{f2(py - 12)} M{f2(px + 9)},{f2(py)} L{f2(px + 9)},{f2(py - 12)}", sw=THIN)
    c.path(f"M{f2(px - 16)},{f2(py - 11)} Q{f2(px)},{f2(py - 16)} {f2(px)},{f2(py - 24)} "
           f"Q{f2(px)},{f2(py - 16)} {f2(px + 16)},{f2(py - 11)}Z", sw=MAIN, fill="#fff")
    # 小舟
    bx, by = w * 0.52, hy + (h - hy) * 0.42
    c.path(f"M{f2(bx - 26)},{f2(by - 3)} Q{f2(bx)},{f2(by + 6)} {f2(bx + 26)},{f2(by - 3)} "
           f"Q{f2(bx)},{f2(by + 1)} {f2(bx - 26)},{f2(by - 3)}Z", sw=MAIN, fill="#fff")
    c.path(f"M{f2(bx - 3)},{f2(by - 1)} L{f2(bx - 3)},{f2(by - 11)} M{f2(bx - 7)},{f2(by - 1)} "
           f"Q{f2(bx - 3)},{f2(by - 9)} {f2(bx + 2)},{f2(by - 2)}", sw=THIN)
    c.path(f"M{f2(bx + 14)},{f2(by - 2)} L{f2(bx + 30)},{f2(by - 16)}", sw=THIN)
    if snow:
        for _ in range(round(w * h / 900)):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            c.add(f'<circle cx="{f2(x)}" cy="{f2(y)}" r="{f2(rng.uniform(0.6, 1.4))}" fill="#fff" stroke="#000" stroke-width="{HAIR}"/>')
    return c.svg()


# ---------------------------------------------------------------- 跑道一圈

def stadium_pts(cx: float, cy: float, L: float, R: float, squash: float, n: int = 90):
    """跑道形（两段直道 + 两个半圆），从高处斜看：纵向压扁。"""
    pts = []
    for k in range(n):
        u = k / n
        per = 2 * L + 2 * math.pi * R
        s = u * per
        if s < L:
            x, y = cx - L / 2 + s, cy + R
        elif s < L + math.pi * R:
            a = (s - L) / R
            x, y = cx + L / 2 + R * math.sin(a), cy + R * math.cos(a)
        elif s < 2 * L + math.pi * R:
            x, y = cx + L / 2 - (s - L - math.pi * R), cy - R
        else:
            a = (s - 2 * L - math.pi * R) / R
            x, y = cx - L / 2 - R * math.sin(a), cy - R * math.cos(a)
        pts.append((x, cy + (y - cy) * squash))
    return pts


def oval_track(w: float, h: float, seed: int = 10, lanes: int = 6, sun: bool = True) -> str:
    """从高处望下去的一圈跑道，场心球场，远处落日，近处云海托底。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    squash = 0.34
    R = min(h * 0.62 / (2 * squash) / 1.25, w * 0.16)
    L = min(w * 0.42, w - 2 * R - 60)
    cx, cy = w * 0.5, h * 0.5
    lane = R * 0.075
    r = h * 0.13
    if sun:
        circle(c, w * 0.8, cy - R * squash - lane * lanes * squash - r * 0.4, r)
    streak(c, w * 0.05, h * 0.12, w * 0.35, h * 0.06, thick=1.1)
    outer = stadium_pts(cx, cy, L, R + lane * lanes, squash)
    c.path(poly(outer, closed=True), sw=MAIN, fill="#fff")
    for k in range(lanes - 1, 0, -1):
        c.path(poly(stadium_pts(cx, cy, L, R + lane * k, squash), closed=True), sw=THIN)
    c.path(poly(stadium_pts(cx, cy, L, R, squash), closed=True), sw=MAIN)
    # 球场
    fw, fh = L * 0.95, R * 1.3 * squash
    c.path(poly([(cx - fw / 2, cy - fh / 2), (cx + fw / 2, cy - fh / 2), (cx + fw / 2, cy + fh / 2),
                 (cx - fw / 2, cy + fh / 2)], closed=True), sw=THIN)
    c.path(f"M{f2(cx)},{f2(cy - fh / 2)} L{f2(cx)},{f2(cy + fh / 2)}", sw=THIN)
    c.add(f'<ellipse cx="{f2(cx)}" cy="{f2(cy)}" rx="{f2(fh * 0.55 / squash * 0.34)}" ry="{f2(fh * 0.2)}" '
          f'fill="none" stroke="#000" stroke-width="{THIN}"/>')
    # 起跑线
    ys = cy + (R) * squash
    c.path(f"M{f2(cx - L / 2 + L * 0.12)},{f2(ys)} L{f2(cx - L / 2 + L * 0.12)},{f2(ys + lane * lanes * squash)}", sw=MAIN)
    ground = cy + (R + lane * lanes) * squash + h * 0.1
    ridge_rows(c, 0, w, ground, h + 4, max(8, round((h - ground) / 3.6)), rng, amp=0.55, density=0.9, persp=1.35)
    return c.svg()


# ---------------------------------------------------------------- 草稿纸上的小跑道

def wobble(pts, rng: random.Random, amp: float = 0.6):
    return [(x + rng.uniform(-amp, amp), y + rng.uniform(-amp, amp)) for x, y in pts]


def paper_doodle(w: float, h: float, seed: int = 12) -> str:
    """草稿纸一角随手画下的小跑道，旁边一支铅笔。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    pw, ph = min(w * 0.62, h * 1.45), h * 0.86
    px, py = w * 0.5 - pw / 2, h * 0.07
    ang = -3.5
    g = [f'<g transform="rotate({ang} {f2(w / 2)} {f2(h / 2)})">']
    c.add("".join(g))
    c.path(poly([(px, py), (px + pw, py), (px + pw, py + ph), (px, py + ph)], closed=True), sw=MAIN, fill="#fff")
    y = py + 16
    while y < py + ph - 6:
        c.path(f"M{f2(px + 4)},{f2(y)} L{f2(px + pw - 4)},{f2(y)}", sw=HAIR)
        y += 11
    c.path(f"M{f2(px + 24)},{f2(py + 2)} L{f2(px + 24)},{f2(py + ph - 2)}", sw=THIN)
    # 演算的笔迹：一行行短促的起伏线
    y = py + 16 - 3
    for row in range(int((ph - 20) / 11)):
        if row % 3 == 2 or y > py + ph * 0.68:
            y += 11
            continue
        x = px + 32
        end = px + pw * rng.uniform(0.45, 0.62)
        pts = []
        while x < end:
            pts.append((x, y + rng.uniform(-2.2, 1.2)))
            x += rng.uniform(2.2, 3.6)
        c.path(poly(pts), sw=HAIR * 1.4)
        y += 11
    # 左下角的小跑道
    dx, dy = px + pw * 0.3, py + ph * 0.8
    for k, rr in enumerate((14, 20)):
        pts = stadium_pts(dx, dy, 26, rr, 0.62, n=60)
        c.path(poly(wobble(pts + pts[:3], rng, 0.5)), sw=THIN)
    c.path(f"M{f2(dx - 13)},{f2(dy + 8.6)} L{f2(dx - 13)},{f2(dy + 12.8)}", sw=THIN)
    c.add("</g>")
    # 铅笔
    L, wd = min(w * 0.3, 150), 7.0
    x0, y0 = w * 0.9, h * 0.95
    a = math.radians(-160)
    ca, sa = math.cos(a), math.sin(a)

    def T(u, v):
        return (x0 + u * ca - v * sa, y0 + u * sa + v * ca)
    body = [T(0, -wd / 2), T(L * 0.86, -wd / 2), T(L * 0.86, wd / 2), T(0, wd / 2)]
    c.path(poly(body, closed=True), sw=MAIN, fill="#fff")
    for v in (-wd / 6, wd / 6):
        q0, q1 = T(L * 0.08, v), T(L * 0.86, v)
        c.path(f"M{f2(q0[0])},{f2(q0[1])} L{f2(q1[0])},{f2(q1[1])}", sw=HAIR)
    tip = [T(L * 0.86, -wd / 2), T(L, 0), T(L * 0.86, wd / 2)]
    c.path(poly(tip, closed=True), sw=MAIN, fill="#fff")
    lead = [T(L * 0.955, -wd * 0.16), T(L, 0), T(L * 0.955, wd * 0.16)]
    c.path(poly(lead, closed=True), sw=0, fill="#000")
    band = [T(0, -wd / 2), T(L * 0.08, -wd / 2), T(L * 0.08, wd / 2), T(0, wd / 2)]
    c.path(poly(band, closed=True), sw=MAIN, fill="#fff")
    for u in (0.025, 0.055):
        q0, q1 = T(L * u, -wd / 2), T(L * u, wd / 2)
        c.path(f"M{f2(q0[0])},{f2(q0[1])} L{f2(q1[0])},{f2(q1[1])}", sw=HAIR)
    return c.svg()


# ---------------------------------------------------------------- 乒乓与匹克球

def pingpong(w: float, h: float, seed: int = 13) -> str:
    """乒乓球拍与匹克球拍隔着太平洋的浪，一只球划出弧线。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    hy = h * 0.56
    c.path(f"M0,{f2(hy)} L{f2(w)},{f2(hy)}", sw=THIN)
    n = max(12, round((h - hy) / 5))
    for i in range(1, n + 1):
        tt = i / n
        y = hy + (h - hy) * tt ** 1.6
        amp = 0.6 + 3 * tt
        wl = 16 + 50 * tt
        ph = rng.uniform(0, math.tau)
        c.path(poly([(x, y + amp * math.sin(x / wl * math.tau + ph)) for x in frange(0, w, 2)]),
               sw=HAIR + (MAIN - HAIR) * tt)
    # 乒乓球拍（左）
    r = min(h * 0.15, 40)
    bx, by = w * 0.15, hy - r * 2.3
    hdl = [(bx + r * 0.25, by + r * 0.85), (bx + r * 0.62, by + r * 1.75), (bx + r * 0.42, by + r * 1.88), (bx + r * 0.02, by + r * 0.98)]
    c.path(poly(hdl, closed=True), sw=MAIN, fill="#fff")
    c.add(f'<ellipse cx="{f2(bx)}" cy="{f2(by)}" rx="{f2(r)}" ry="{f2(r * 1.08)}" transform="rotate(-24 {f2(bx)} {f2(by)})" '
          f'fill="#fff" stroke="#000" stroke-width="{MAIN}"/>')
    c.add(f'<ellipse cx="{f2(bx)}" cy="{f2(by)}" rx="{f2(r * 0.88)}" ry="{f2(r * 0.96)}" transform="rotate(-24 {f2(bx)} {f2(by)})" '
          f'fill="none" stroke="#000" stroke-width="{HAIR}"/>')
    # 匹克球拍（右）
    qw, qh = min(h * 0.26, 58), min(h * 0.32, 70)
    qx, qy = w * 0.84, hy - qh * 1.35
    g = f'<g transform="rotate(20 {f2(qx)} {f2(qy)})">'
    c.add(g)
    c.add(f'<rect x="{f2(qx - qw / 2)}" y="{f2(qy - qh / 2)}" width="{f2(qw)}" height="{f2(qh)}" rx="{f2(qw * 0.28)}" '
          f'fill="#fff" stroke="#000" stroke-width="{MAIN}"/>')
    c.add(f'<rect x="{f2(qx - qw / 2 + 4)}" y="{f2(qy - qh / 2 + 4)}" width="{f2(qw - 8)}" height="{f2(qh - 8)}" rx="{f2(qw * 0.24)}" '
          f'fill="none" stroke="#000" stroke-width="{HAIR}"/>')
    c.add(f'<rect x="{f2(qx - qw * 0.13)}" y="{f2(qy + qh / 2)}" width="{f2(qw * 0.26)}" height="{f2(qh * 0.55)}" rx="3" '
          f'fill="#fff" stroke="#000" stroke-width="{MAIN}"/>')
    for k in range(4):
        yy = qy + qh / 2 + qh * 0.12 * (k + 1)
        c.path(f"M{f2(qx - qw * 0.13)},{f2(yy)} L{f2(qx + qw * 0.13)},{f2(yy)}", sw=HAIR)
    c.add("</g>")
    # 球的弧线
    x0, y0 = bx + r * 1.1, by - r * 0.4
    x1, y1 = qx - qw * 0.7, qy - qh * 0.1
    cxp, cyp = (x0 + x1) / 2, min(y0, y1) - h * 0.32
    c.path(f"M{f2(x0)},{f2(y0)} Q{f2(cxp)},{f2(cyp)} {f2(x1)},{f2(y1)}", sw=THIN, extra=' stroke-dasharray="2 4"')
    tt = 0.62
    ballx = (1 - tt) ** 2 * x0 + 2 * (1 - tt) * tt * cxp + tt ** 2 * x1
    bally = (1 - tt) ** 2 * y0 + 2 * (1 - tt) * tt * cyp + tt ** 2 * y1
    circle(c, ballx, bally, 5.2)
    for k in range(3):
        a = k * 2.1 + 0.4
        c.add(f'<circle cx="{f2(ballx + 2.4 * math.cos(a))}" cy="{f2(bally + 2.4 * math.sin(a))}" r="0.8" fill="#000"/>')
    return c.svg()


# ---------------------------------------------------------------- 羽毛与玻璃房

def feather(w: float, h: float, seed: int = 14) -> str:
    """一片飘落的羽毛，下方几道云纹。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    L = min(h * 0.62, w * 0.5)
    cx, cy = w * 0.5, h * 0.42
    a = math.radians(-58)
    ca, sa = math.cos(a), math.sin(a)

    def T(u, v):
        return (cx + u * ca - v * sa, cy + u * sa + v * ca)
    # 羽轴：略弯
    shaft = [T(-L / 2 + L * k / 20, 0.02 * L * math.sin(math.pi * k / 20)) for k in range(21)]
    vane_w = L * 0.13
    for side in (-1, 1):
        edge = []
        for k in range(1, 40):
            u = k / 40
            v = side * vane_w * math.sin(math.pi * min(1, u * 1.08) ** 0.8) * (1 - 0.25 * u)
            edge.append(T(-L / 2 + L * (0.12 + 0.88 * u), v + 0.02 * L * math.sin(math.pi * u)))
        c.path(smooth([shaft[2]] + edge + [shaft[-1]]), sw=MAIN, fill="#fff")
        # 羽枝
        gaps = {rng.randint(8, 30) for _ in range(2)}
        for k in range(3, 38):
            if k in gaps:
                continue
            u = k / 40
            s0 = T(-L / 2 + L * (0.1 + 0.88 * u), 0.02 * L * math.sin(math.pi * u))
            v = side * vane_w * 0.92 * math.sin(math.pi * min(1, u * 1.08) ** 0.8) * (1 - 0.25 * u)
            e = T(-L / 2 + L * (0.14 + 0.88 * u) + L * 0.04, v + 0.02 * L * math.sin(math.pi * u))
            c.path(f"M{f2(s0[0])},{f2(s0[1])} L{f2(e[0])},{f2(e[1])}", sw=HAIR)
    c.path(smooth(shaft), sw=MAIN)
    for k in range(5):
        u = rng.uniform(-0.1, 0.1)
        s0 = T(-L / 2 + L * 0.06, 0)
        e = T(-L / 2 + L * rng.uniform(0.0, 0.1), rng.choice((-1, 1)) * L * rng.uniform(0.05, 0.1))
        c.path(f"M{f2(s0[0])},{f2(s0[1])} Q{f2((s0[0] + e[0]) / 2 + 3)},{f2((s0[1] + e[1]) / 2)} {f2(e[0])},{f2(e[1])}", sw=HAIR)
    for k in range(3):
        y = h * rng.uniform(0.1, 0.35)
        x0 = w * rng.uniform(0.05, 0.25) if k % 2 else w * rng.uniform(0.6, 0.72)
        streak(c, x0, y + 2, x0 + w * rng.uniform(0.15, 0.25), y - 2, thick=0.9)
    ground = h * 0.84
    ridge_rows(c, 0, w, ground, h + 4, max(6, round((h - ground) / 3.8)), rng, amp=0.45, density=0.8, persp=1.3)
    return c.svg()


def glass_bird(w: float, h: float, seed: int = 15) -> str:
    """教学楼旁的玻璃采光室，一只鸟在里面盘旋，一次次撞向透明的墙。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    ground = h * 0.8
    building(c, w * 0.62, w + 4, h * 0.14, ground, slit=5)
    r = h * 0.14
    circle(c, w * 0.2, h * 0.24, r)
    streak(c, w * 0.02, h * 0.1, w * 0.3, h * 0.05, thick=1.1)
    # 玻璃房：正面 + 顶面 + 侧面（两点透视简化为斜投影）
    fx0, fx1 = w * 0.08, w * 0.56
    fy0, fy1 = ground - h * 0.3, ground + 2
    dx, dy = w * 0.07, -h * 0.1
    top = [(fx0, fy0), (fx0 + dx, fy0 + dy), (fx1 + dx, fy0 + dy), (fx1, fy0)]
    side = [(fx1, fy0), (fx1 + dx, fy0 + dy), (fx1 + dx, fy1 + dy), (fx1, fy1)]
    # 透过玻璃看得见的后框
    c.path(poly([(fx0 + dx, fy0 + dy), (fx0 + dx, fy1 + dy)]), sw=HAIR)
    c.path(poly([(fx0 + dx, fy1 + dy), (fx1 + dx, fy1 + dy)]), sw=HAIR)
    c.path(poly(top, closed=True), sw=MAIN)
    c.path(poly(side, closed=True), sw=MAIN)
    c.path(poly([(fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1)], closed=True), sw=MAIN)
    n = 6
    for k in range(1, n):
        x = fx0 + (fx1 - fx0) * k / n
        c.path(f"M{f2(x)},{f2(fy0)} L{f2(x)},{f2(fy1)}", sw=THIN)
        c.path(f"M{f2(x)},{f2(fy0)} L{f2(x + dx)},{f2(fy0 + dy)}", sw=HAIR)
    c.path(f"M{f2(fx1 + dx / 2)},{f2(fy0 + dy / 2)} L{f2(fx1 + dx / 2)},{f2(fy1 + dy / 2)}", sw=THIN)
    # 玻璃反光
    for k in range(n):
        x = fx0 + (fx1 - fx0) * (k + 0.3) / n
        if k % 2 == 0:
            c.path(f"M{f2(x)},{f2(fy0 + h * 0.08)} L{f2(x + 9)},{f2(fy0 + h * 0.02)} "
                   f"M{f2(x + 3)},{f2(fy0 + h * 0.12)} L{f2(x + 14)},{f2(fy0 + h * 0.045)}", sw=HAIR)
    # 鸟与它来回撞墙的轨迹
    bx, by = fx0 + (fx1 - fx0) * 0.55, fy0 + (fy1 - fy0) * 0.45
    c.path(f"M{f2(fx0 + 30)},{f2(by + 12)} C{f2(fx0 + 80)},{f2(fy0 + 4)} {f2(bx - 40)},{f2(by + 18)} {f2(bx - 8)},{f2(by + 2)}",
           sw=HAIR, extra=' stroke-dasharray="1.5 3"')
    s = 9
    c.path(f"M{f2(bx - s)},{f2(by - s * 0.8)} Q{f2(bx - s * 0.4)},{f2(by - s * 0.3)} {f2(bx)},{f2(by)} "
           f"Q{f2(bx + s * 0.5)},{f2(by - s * 0.9)} {f2(bx + s * 1.2)},{f2(by - s * 1.1)}", sw=MAIN)
    c.add(f'<ellipse cx="{f2(bx + 1)}" cy="{f2(by + 2)}" rx="3.2" ry="2" fill="#000"/>')
    ridge_rows(c, 0, w, ground + 2, h + 4, max(6, round((h - ground) / 3.8)), rng, amp=0.4, density=0.7, persp=1.3)
    return c.svg()


# ---------------------------------------------------------------- 折纸老虎

def origami_tiger(w: float, h: float, seed: int = 16) -> str:
    """纸老虎：折纸的老虎，棱角分明的折面、背上几道虎纹。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    ground = h * 0.86
    k = min((h * 0.72) / 60, (w * 0.62) / 104)
    ox = w * 0.5 - 52 * k
    oy = ground - 60 * k

    def P(x, y):
        return (ox + x * k, oy + y * k)
    outline = [(14, 20), (30, 15), (50, 17), (67, 13), (75, 10), (77, 3), (82, 10), (86, 2), (89, 10), (93, 11),
               (102, 21), (98, 29), (89, 31), (84, 38), (86, 58), (89, 60), (79, 60), (76, 41), (62, 41),
               (44, 42), (37, 43), (35, 58), (38, 60), (28, 60), (25, 45), (17, 34)]
    c.path(poly([P(*q) for q in outline], closed=True), sw=MAIN, fill="#fff")
    folds = [((30, 15), (37, 43)), ((50, 17), (44, 42)), ((50, 17), (62, 41)), ((67, 13), (76, 41)),
             ((67, 13), (84, 38)), ((75, 10), (89, 31)), ((89, 10), (89, 31)), ((93, 11), (89, 31)),
             ((17, 34), (30, 15)), ((25, 45), (30, 15)), ((76, 41), (84, 38))]
    for a, b in folds:
        pa, pb = P(*a), P(*b)
        c.path(f"M{f2(pa[0])},{f2(pa[1])} L{f2(pb[0])},{f2(pb[1])}", sw=HAIR)
    # 虎纹：背上的黑色楔形
    for x0, x1, depth in [(34, 38, 9), (41, 45, 10), (53, 57, 10), (59, 63, 9), (70, 73, 7), (20, 23, 6)]:
        ya = 15 + (x0 - 14) * 0.02
        c.path(poly([P(x0, ya + 0.8), P(x1, ya + 0.3), P((x0 + x1) / 2 + 1.5, ya + depth)], closed=True), sw=0, fill="#000")
    # 尾巴：折成锯齿的纸条
    tail = [(14, 21), (8, 16), (11, 12), (5, 7), (8, 3), (3, 0)]
    c.path(poly([P(*q) for q in tail]), sw=MAIN)
    tail2 = [(15, 24), (9, 19), (12, 15), (6, 10), (9, 6), (4, 3)]
    c.path(poly([P(*q) for q in tail2]), sw=THIN)
    # 眼、鼻、胡须
    e = P(92, 17)
    c.add(f'<circle cx="{f2(e[0])}" cy="{f2(e[1])}" r="{f2(0.9 * k)}" fill="#000"/>')
    c.path(poly([P(100, 19), P(102, 21), P(99.5, 22.5)], closed=True), sw=0, fill="#000")
    for dy in (-1.2, 0.8):
        a, b = P(98, 24 + dy), P(106, 23 + dy * 2.2)
        c.path(f"M{f2(a[0])},{f2(a[1])} L{f2(b[0])},{f2(b[1])}", sw=HAIR)
    # 地面与折痕影
    c.path(f"M{f2(P(18, 60)[0])},{f2(ground)} L{f2(P(96, 60)[0])},{f2(ground)}", sw=THIN)
    for x in frange(P(22, 60)[0], P(92, 60)[0], 7):
        c.path(f"M{f2(x)},{f2(ground + 3)} L{f2(x + 3.5)},{f2(ground + 3)}", sw=HAIR)
    for k2 in range(2):
        y = h * rng.uniform(0.08, 0.25)
        x0 = w * rng.uniform(0.05, 0.2) if k2 else w * rng.uniform(0.62, 0.75)
        streak(c, x0, y + 2, x0 + w * 0.18, y - 2, thick=0.9)
    return c.svg()


# ---------------------------------------------------------------- 宁波鼓楼

def gulou(w: float, h: float, seed: int = 17) -> str:
    """宁波鼓楼（海曙楼）：城台券门、重檐木楼，楼顶的方形钟楼。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    ground = h * 0.84
    k = min(h * 0.8 / 100, w * 0.62 / 100)
    ox = w * 0.5 - 50 * k
    oy = ground - 100 * k

    def P(x, y):
        return (ox + x * k, oy + y * k)

    def Pl(pts, closed=True, sw=MAIN, fill="#fff"):
        c.path(poly([P(*q) for q in pts], closed=closed), sw=sw, fill=fill if closed else "none")
    # 城台
    Pl([(4, 100), (9, 64), (91, 64), (96, 100)])
    y = 67
    while y < 99:
        f = (y - 64) / 36
        Pl([(9 - 5 * f, y), (91 + 5 * f, y)], closed=False, sw=HAIR)
        y += 3.2
    # 券门
    a0, a1 = P(41, 100), P(59, 100)
    r = 9 * k
    c.path(f"M{f2(a0[0])},{f2(a0[1])} L{f2(a0[0])},{f2(P(0, 85)[1])} A{f2(r)},{f2(r)} 0 0 1 {f2(a1[0])},{f2(P(0, 85)[1])} "
           f"L{f2(a1[0])},{f2(a1[1])}Z", sw=MAIN, fill="#fff")
    # 城台上的矮墙
    Pl([(8, 64), (8, 60), (92, 60), (92, 64)])
    for x in range(12, 90, 6):
        Pl([(x, 60), (x, 64)], closed=False, sw=HAIR)
    # 一层：柱廊
    Pl([(18, 60), (18, 47), (82, 47), (82, 60)])
    for x in range(24, 80, 8):
        Pl([(x, 47), (x, 60)], closed=False, sw=THIN)
    # 下檐
    c.path(smooth([P(6, 42), P(14, 47.5), P(50, 48), P(86, 47.5), P(94, 42)], t=0.9) +
           " " + " ".join(f"L{f2(P(*q)[0])},{f2(P(*q)[1])}" for q in [(76, 38), (24, 38)]) + "Z", sw=MAIN, fill="#fff")
    Pl([(14, 45.5), (86, 45.5)], closed=False, sw=HAIR)
    # 二层
    Pl([(28, 38), (28, 29), (72, 29), (72, 38)])
    for x in range(33, 70, 6):
        Pl([(x, 30.5), (x, 36.5)], closed=False, sw=HAIR)
    # 上檐（歇山）
    c.path(smooth([P(16, 24), P(24, 30.5), P(50, 31), P(76, 30.5), P(84, 24)], t=0.9) +
           " " + " ".join(f"L{f2(P(*q)[0])},{f2(P(*q)[1])}" for q in [(64, 17), (36, 17)]) + "Z", sw=MAIN, fill="#fff")
    Pl([(36, 17), (64, 17)], closed=False, sw=MAIN)
    Pl([(33, 17), (67, 17)], closed=False, sw=THIN)
    # 楼顶的方形钟楼
    Pl([(44, 17), (44, 5), (56, 5), (56, 17)])
    cc = P(50, 10.5)
    circle(c, cc[0], cc[1], 3.3 * k, sw=THIN)
    c.path(f"M{f2(cc[0])},{f2(cc[1])} L{f2(cc[0])},{f2(cc[1] - 2.2 * k)} M{f2(cc[0])},{f2(cc[1])} L{f2(cc[0] + 1.6 * k)},{f2(cc[1])}", sw=HAIR)
    Pl([(42.5, 5), (50, -1.5), (57.5, 5)])
    ridge_rows(c, 0, w, ground, h + 4, max(6, round((h - ground) / 3.6)), rng, amp=0.4, density=0.8, persp=1.3)
    for k2 in range(3):
        y = h * rng.uniform(0.08, 0.35)
        x0 = w * rng.uniform(0.02, 0.12) if k2 % 2 else w * rng.uniform(0.68, 0.78)
        streak(c, x0, y + 2, x0 + w * 0.17, y - 2, thick=0.9)
    for _ in range(4):
        bird(c, w * rng.uniform(0.66, 0.92), h * rng.uniform(0.12, 0.45), rng.uniform(3.5, 6), rng)
    return c.svg()


# ---------------------------------------------------------------- 老槐

def canopy(c: Canvas, puffs, sw=MAIN, inner=True) -> None:
    """若干圆团合成的树冠：只描外轮廓，内部加几道弧线。"""
    for i, (x, y, r) in enumerate(puffs):
        c.add(f'<circle cx="{f2(x)}" cy="{f2(y)}" r="{f2(r)}" fill="#fff" stroke="none"/>')
    for i, (x, y, r) in enumerate(puffs):
        seg = []
        for kk in range(0, 181):
            a = math.tau * kk / 180
            px, py = x + r * math.cos(a), y + r * math.sin(a)
            inside = any(j != i and (px - xj) ** 2 + (py - yj) ** 2 < (rj - 0.2) ** 2 for j, (xj, yj, rj) in enumerate(puffs))
            if inside:
                if len(seg) > 1:
                    c.path(poly(seg), sw=sw)
                seg = []
            else:
                seg.append((px, py))
        if len(seg) > 1:
            c.path(poly(seg), sw=sw)
    if inner:
        for x, y, r in puffs[::2]:
            c.path(f"M{f2(x - r * 0.55)},{f2(y + r * 0.1)} A{f2(r * 0.6)},{f2(r * 0.6)} 0 0 1 {f2(x + r * 0.5)},{f2(y - r * 0.05)}", sw=HAIR)


def limb(c: Canvas, pts, w0: float, w1: float, sw=MAIN) -> None:
    """一根由粗渐细的枝干：沿中线两侧偏移出轮廓。"""
    n = len(pts)
    left, right = [], []
    for i, (x, y) in enumerate(pts):
        xa, ya = pts[max(i - 1, 0)]
        xb, yb = pts[min(i + 1, n - 1)]
        dx, dy = xb - xa, yb - ya
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        wd = (w0 + (w1 - w0) * i / (n - 1)) / 2
        left.append((x + nx * wd, y + ny * wd))
        right.append((x - nx * wd, y - ny * wd))
    c.path(smooth(left + right[::-1], closed=True), sw=sw, fill="#fff")


def old_tree(w: float, h: float, seed: int = 18) -> str:
    """荒径旁一棵虬曲的老槐：粗粝的树干分出几道枝，团团树冠，一条小路伸向远处。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    ground = h * 0.8
    tx = w * 0.3
    H = ground - h * 0.06
    # 小路：从近处伸向远处
    vx = w * 0.72
    c.path(poly([(w * 0.46, h + 2), (vx - 3, ground), (vx + 3, ground), (w * 0.98, h + 2)], closed=True), sw=0, fill="#fff")
    rows = max(6, round((h - ground) / 3.6))
    c.defs.append(f'<clipPath id="road"><path d="M0,0 L{f2(w)},0 L{f2(w)},{f2(h)} L{f2(w * 0.98)},{f2(h + 2)} '
                  f'L{f2(vx + 3)},{f2(ground)} L{f2(vx - 3)},{f2(ground)} L{f2(w * 0.46)},{f2(h + 2)} L0,{f2(h)}Z"/></clipPath>')
    ridge_rows(c, 0, w, ground, h + 4, rows, rng, amp=0.35, density=0.7, persp=1.3, clip_poly="road")
    c.path(f"M{f2(w * 0.46)},{f2(h + 2)} L{f2(vx - 3)},{f2(ground)} M{f2(w * 0.98)},{f2(h + 2)} L{f2(vx + 3)},{f2(ground)}", sw=THIN)
    # 树干：微斜、略带 S 形，根部外张；到顶分出几道主枝，主枝再分细枝
    trunk = [(tx + 5 * math.sin(k / 10 * math.pi * 1.2) + k * 0.6, ground + 2 - k / 10 * H * 0.4) for k in range(11)]
    top = trunk[-1]
    branches = []
    for ang, L in [(-2.55, 0.34), (-2.05, 0.38), (-1.6, 0.36), (-1.15, 0.38), (-0.65, 0.33)]:
        pts, (x, y), a_ = [top], top, ang
        for s in range(6):
            a_ += rng.uniform(-0.12, 0.12)
            x += math.cos(a_) * H * L / 6
            y += math.sin(a_) * H * L / 6 * 0.8
            pts.append((x, y))
        branches.append(pts)
        mid = pts[3]
        sub, (x, y), b_ = [mid], mid, ang + rng.choice((-0.6, 0.6))
        for s in range(3):
            x += math.cos(b_) * H * L / 7
            y += math.sin(b_) * H * L / 7 * 0.8
            sub.append((x, y))
        branches.append(sub)
    puffs = []
    for br in branches:
        for (ex, ey) in br[len(br) // 2:]:
            puffs.append((ex + rng.uniform(-12, 12), ey + rng.uniform(-8, 6), rng.uniform(11, 18)))
    puffs = [p_ for p_ in puffs if p_[1] - p_[2] > h * 0.02]
    for br in branches:
        limb(c, br, 10 if len(br) > 4 else 6, 2.2)
    limb(c, trunk, 30, 11)
    for k in range(9):
        y = ground - H * 0.03 - k * H * 0.035
        x = trunk[min(k, 10)][0] + rng.uniform(-8, 6)
        c.path(f"M{f2(x)},{f2(y)} q{f2(rng.uniform(1, 3))},{f2(-4)} {f2(rng.uniform(-1, 1.5))},{f2(-9)}", sw=HAIR)
    canopy(c, puffs, sw=THIN)
    for dx in (-22, -10, 12, 24):
        c.path(f"M{f2(tx + dx * 0.3)},{f2(ground - 2)} Q{f2(tx + dx * 0.8)},{f2(ground + 1)} {f2(tx + dx * 1.5)},{f2(ground + 3)}", sw=THIN)
    for _ in range(3):
        bird(c, w * rng.uniform(0.6, 0.92), h * rng.uniform(0.08, 0.35), rng.uniform(4, 6.5), rng)
    streak(c, w * 0.55, h * 0.45, w * 0.9, h * 0.4, thick=1.0)
    return c.svg()


# ---------------------------------------------------------------- 窗外

def window_view(w: float, h: float, seed: int = 19) -> str:
    """砖墙上一扇推开的窗：窗外是城市天际线、海平线、飞鸟与飘进来的银杏叶。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    brick_wall(c, -2, -2, w + 2, h + 2, course=6.2)
    ww, wh = min(w * 0.56, h * 0.72), h * 0.74
    x0, y0 = w / 2 - ww / 2, h * 0.08
    x1, y1 = x0 + ww, y0 + wh
    c.path(poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], closed=True), sw=MAIN, fill="#fff")
    # 窗外：天际线、海、太阳、飞鸟
    hy = y0 + wh * 0.62
    sub = Canvas(w, h)
    r = ww * 0.1
    circle(sub, x0 + ww * 0.7, hy - wh * 0.28, r)
    streak(sub, x0 + ww * 0.08, y0 + wh * 0.16, x0 + ww * 0.5, y0 + wh * 0.1, thick=1.0)
    x = x0 - 2
    while x < x1:
        bw = rng.uniform(10, 26)
        bh = rng.uniform(8, 40) * (1.4 if abs(x - (x0 + ww * 0.35)) < 30 else 1)
        sub.path(poly([(x, hy), (x, hy - bh), (x + bw, hy - bh), (x + bw, hy)], closed=True), sw=THIN, fill="#fff")
        yy = hy - bh + 4
        while yy < hy - 3:
            sub.path(f"M{f2(x + 3)},{f2(yy)} L{f2(x + bw - 3)},{f2(yy)}", sw=HAIR)
            yy += 5
        x += bw + rng.uniform(1, 6)
    sub.path(f"M{f2(x0)},{f2(hy)} L{f2(x1)},{f2(hy)}", sw=THIN)
    for i in range(1, 12):
        tt = i / 11
        y = hy + (y1 - hy) * tt ** 1.4
        ph = rng.uniform(0, math.tau)
        sub.path(poly([(xx, y + (0.4 + 1.6 * tt) * math.sin(xx / (12 + 25 * tt) + ph)) for xx in frange(x0, x1, 2)]),
                 sw=HAIR + (THIN - HAIR) * tt)
    for _ in range(5):
        bird(sub, x0 + ww * rng.uniform(0.15, 0.85), y0 + wh * rng.uniform(0.15, 0.45), rng.uniform(3.5, 6.5), rng)
    c.defs.append(f'<clipPath id="win"><rect x="{f2(x0)}" y="{f2(y0)}" width="{f2(ww)}" height="{f2(wh)}"/></clipPath>')
    c.add(f'<g clip-path="url(#win)">{"".join(sub.parts)}</g>')
    # 窗框、中梃、向外推开的上悬窗扇
    fr = 7
    c.path(poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], closed=True), sw=MAIN)
    c.path(poly([(x0 + fr, y0 + fr), (x1 - fr, y0 + fr), (x1 - fr, y1 - fr), (x0 + fr, y1 - fr)], closed=True), sw=THIN)
    # 两扇向外推开的窗扇：正面看成两侧斜出的平行四边形
    sw_ = ww * 0.2
    for side in (-1, 1):
        ex = x0 if side < 0 else x1
        ox_ = ex + side * sw_
        leaf = [(ex, y0 + 2), (ox_, y0 + wh * 0.06), (ox_, y1 - wh * 0.06), (ex, y1 - 2)]
        c.path(poly(leaf, closed=True), sw=MAIN, fill="#fff")
        inn = [(ex + side * 5, y0 + 9), (ox_ - side * 5, y0 + wh * 0.06 + 6), (ox_ - side * 5, y1 - wh * 0.06 - 6), (ex + side * 5, y1 - 9)]
        c.path(poly(inn, closed=True), sw=HAIR)
        for k in range(3):
            yy = y0 + wh * (0.25 + 0.2 * k)
            c.path(f"M{f2(ex + side * 9)},{f2(yy)} L{f2(ex + side * sw_ * 0.55)},{f2(yy - 10)}", sw=HAIR)
    # 窗台
    c.path(poly([(x0 - 12, y1), (x1 + 12, y1), (x1 + 16, y1 + 9), (x0 - 16, y1 + 9)], closed=True), sw=MAIN, fill="#fff")
    for k in range(4):
        lx = x0 + ww * (0.15 + 0.22 * k) + rng.uniform(-8, 8)
        ly = y0 + wh * (0.2 + 0.08 * k) + rng.uniform(-6, 6)
        ginkgo_leaf(c, lx, ly, rng.uniform(10, 15), rng.uniform(-2.4, 2.4))
    streak(c, x0 + ww * 0.05, y0 + wh * 0.32, x0 + ww * 0.42, y0 + wh * 0.26, thick=0.8)
    return c.svg()


# ---------------------------------------------------------------- 起跑线与旗

def startline(w: float, h: float, seed: int = 20, sun: bool = True) -> str:
    """黄昏的空跑道：脚下是起跑线，远处落日，旗杆上半展的绸旗，风从跑道上吹过。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    hy = h * 0.34
    vx = w * 0.46
    r = min(w * 0.08, h * 0.15)
    if sun:
        circle(c, w * 0.28, hy - r * 0.2, r)
    c.path(f"M0,{f2(hy)} L{f2(w)},{f2(hy)}", sw=THIN)
    bl, br = -w * 0.25, w * 1.1
    tl, trr = vx - w * 0.03, vx + w * 0.03
    c.defs.append(f'<clipPath id="side2"><path d="M0,0 L{f2(w)},0 L{f2(w)},{f2(h)} L{f2(br)},{f2(h + 1)} '
                  f'L{f2(trr)},{f2(hy)} L{f2(tl)},{f2(hy)} L{f2(bl)},{f2(h + 1)} L0,{f2(h)}Z"/></clipPath>')
    ridge_rows(c, 0, w, hy, h + 6, max(12, round((h - hy) / 4.5)), rng, amp=0.6, persp=1.7, clip_poly="side2",
               avoid=(tl - 20, trr + 20))
    c.path(poly([(bl, h + 1), (tl, hy), (trr, hy), (br, h + 1)], closed=True), sw=0, fill="#fff")
    lanes = 8
    for k in range(lanes + 1):
        u = k / lanes
        c.path(f"M{f2(bl + (br - bl) * u)},{f2(h + 1)} L{f2(tl + (trr - tl) * u)},{f2(hy)}",
               sw=MAIN if k in (0, lanes) else THIN)
    y = h - (h - hy) * 0.2
    f = (y - hy) / (h - hy)
    c.path(f"M{f2(tl + (bl - tl) * f)},{f2(y)} L{f2(trr + (br - trr) * f)},{f2(y)}", sw=MAIN * 1.6)
    # 旗杆与绸旗
    fx = w * 0.86
    c.path(f"M{f2(fx)},{f2(hy + 6)} L{f2(fx)},{f2(h * 0.06)}", sw=MAIN)
    c.add(f'<circle cx="{f2(fx)}" cy="{f2(h * 0.06 - 1.5)}" r="1.8" fill="#000"/>')
    fy = h * 0.07
    fl = [(fx, fy), (fx - w * 0.04, fy + 4), (fx - w * 0.08, fy + 1), (fx - w * 0.11, fy + 7)]
    fl2 = [(fx - w * 0.1, fy + h * 0.1), (fx - w * 0.07, fy + h * 0.095), (fx - w * 0.035, fy + h * 0.1), (fx, fy + h * 0.085)]
    c.path(smooth(fl) + " L" + smooth(fl2)[1:] + "Z", sw=MAIN, fill="#fff")
    for k in range(4):
        y = h * rng.uniform(0.08, 0.3)
        x0 = w * rng.uniform(0.02, 0.5)
        streak(c, x0, y + 3, x0 + w * rng.uniform(0.2, 0.35), y - 4, thick=rng.uniform(0.8, 1.4))
    return c.svg()


def framed_landscape(w: float, h: float, seed: int = 22) -> str:
    """卧游：挂在墙上的一幅山水，画里群山、瀑布与小亭；画外是床榻的一角。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    fw, fh = min(w * 0.7, h * 1.0), h * 0.84
    x0, y0 = w / 2 - fw / 2, h * 0.1
    inner = Canvas(w, h)
    sub = mountains(fw - 20, fh - 20, seed=seed, horizon=0.35, mist=True, birds_n=2)
    # 直接嵌入子 SVG
    c.add(f'<rect x="{f2(x0)}" y="{f2(y0)}" width="{f2(fw)}" height="{f2(fh)}" fill="#fff" stroke="#000" stroke-width="{MAIN}"/>')
    c.add(f'<rect x="{f2(x0 + 6)}" y="{f2(y0 + 6)}" width="{f2(fw - 12)}" height="{f2(fh - 12)}" fill="none" stroke="#000" stroke-width="{HAIR}"/>')
    body = sub[sub.index(">") + 1: sub.rindex("</svg>")]
    c.add(f'<svg x="{f2(x0 + 10)}" y="{f2(y0 + 10)}" width="{f2(fw - 20)}" height="{f2(fh - 20)}" '
          f'viewBox="0 0 {f2(fw - 20)} {f2(fh - 20)}">{body}</svg>')
    c.add(f'<rect x="{f2(x0 + 10)}" y="{f2(y0 + 10)}" width="{f2(fw - 20)}" height="{f2(fh - 20)}" fill="none" stroke="#000" stroke-width="{THIN}"/>')
    # 挂绳
    c.path(f"M{f2(w / 2 - 22)},{f2(y0)} L{f2(w / 2)},{f2(y0 - h * 0.05)} L{f2(w / 2 + 22)},{f2(y0)}", sw=THIN)
    c.add(f'<circle cx="{f2(w / 2)}" cy="{f2(y0 - h * 0.05)}" r="1.6" fill="#000"/>')
    return c.svg()


def shuttle(w: float, h: float, seed: int = 23) -> str:
    """羽毛球拍与飞行中的羽毛球，几片银杏叶随风。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    # 球拍：椭圆拍框、拍线、拍杆、握把
    ry = h * 0.2
    rx = ry * 0.78
    cx, cy = w * 0.2, h * 0.3
    ang = -32
    g = f'<g transform="rotate({ang} {f2(cx)} {f2(cy)})">'
    c.add(g)
    c.add(f'<ellipse cx="{f2(cx)}" cy="{f2(cy)}" rx="{f2(rx)}" ry="{f2(ry)}" fill="#fff" stroke="#000" stroke-width="{MAIN * 1.4}"/>')
    c.defs.append(f'<clipPath id="strings"><ellipse cx="{f2(cx)}" cy="{f2(cy)}" rx="{f2(rx - 1.5)}" ry="{f2(ry - 1.5)}"/></clipPath>')
    lines = []
    for x in frange(cx - rx, cx + rx, 5.2):
        lines.append(f'<path d="M{f2(x)},{f2(cy - ry)} L{f2(x)},{f2(cy + ry)}" stroke="#000" stroke-width="{HAIR}"/>')
    for y in frange(cy - ry, cy + ry, 5.2):
        lines.append(f'<path d="M{f2(cx - rx)},{f2(y)} L{f2(cx + rx)},{f2(y)}" stroke="#000" stroke-width="{HAIR}"/>')
    c.add(f'<g clip-path="url(#strings)">{"".join(lines)}</g>')
    c.path(f"M{f2(cx)},{f2(cy + ry)} L{f2(cx)},{f2(cy + ry + h * 0.24)}", sw=MAIN * 1.2)
    c.path(f"M{f2(cx - 4)},{f2(cy + ry)} Q{f2(cx)},{f2(cy + ry + 10)} {f2(cx + 4)},{f2(cy + ry)}", sw=THIN)
    gy = cy + ry + h * 0.24
    c.add(f'<rect x="{f2(cx - 4)}" y="{f2(gy)}" width="8" height="{f2(h * 0.15)}" rx="2.5" fill="#fff" stroke="#000" stroke-width="{MAIN}"/>')
    for k in range(1, 6):
        yy = gy + h * 0.15 * k / 6
        c.path(f"M{f2(cx - 4)},{f2(yy + 2)} L{f2(cx + 4)},{f2(yy - 2)}", sw=HAIR)
    c.add("</g>")
    # 羽毛球：球头 + 羽毛裙，朝右上飞
    sx, sy = w * 0.62, h * 0.3
    a = math.radians(-18)
    ca, sa = math.cos(a), math.sin(a)

    def T(u, v):
        return (sx + u * ca - v * sa, sy + u * sa + v * ca)
    L = min(h * 0.24, 44)
    skirt = [T(0, -L * 0.14), T(-L, -L * 0.42), T(-L, L * 0.42), T(0, L * 0.14)]
    c.path(poly(skirt, closed=True), sw=MAIN, fill="#fff")
    for k in range(-3, 4):
        p0, p1 = T(0, k * L * 0.04), T(-L, k * L * 0.12)
        c.path(f"M{f2(p0[0])},{f2(p0[1])} L{f2(p1[0])},{f2(p1[1])}", sw=HAIR)
    for u in (0.35, 0.62):
        q0, q1 = T(-L * u, -L * (0.14 + 0.28 * u)), T(-L * u, L * (0.14 + 0.28 * u))
        c.path(f"M{f2(q0[0])},{f2(q0[1])} L{f2(q1[0])},{f2(q1[1])}", sw=HAIR)
    hc = T(L * 0.12, 0)
    c.add(f'<circle cx="{f2(hc[0])}" cy="{f2(hc[1])}" r="{f2(L * 0.16)}" fill="#fff" stroke="#000" stroke-width="{MAIN}"/>')
    for k in range(3):
        o = T(-L * (1.3 + 0.35 * k), -L * 0.3 + k * L * 0.3)
        e = T(-L * (2.4 + 0.5 * k), -L * 0.3 + k * L * 0.3)
        c.path(f"M{f2(o[0])},{f2(o[1])} L{f2(e[0])},{f2(e[1])}", sw=HAIR)
    for _ in range(5):
        ginkgo_leaf(c, w * rng.uniform(0.45, 0.95), h * rng.uniform(0.45, 0.9), rng.uniform(9, 16), rng.uniform(-2.4, 2.4))
    streak(c, w * 0.5, h * 0.62, w * 0.9, h * 0.55, thick=1.0)
    return c.svg()


def book_leaf(w: float, h: float, seed: int = 24) -> str:
    """摊开的单词书，书页上夹着一片银杏叶，斜斜的日光照进来。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    bw, bh = min(w * 0.5, h * 2.2), h * 0.78
    cx, top = w * 0.5, h * 0.1
    bot = top + bh
    for side in (-1, 1):
        outer = cx + side * bw / 2
        pts = [(cx, top + 6), (outer, top), (outer + side * 4, bot), (cx, bot + 5)]
        c.path(f"M{f2(cx)},{f2(top + 6)} Q{f2((cx + outer) / 2)},{f2(top - 4)} {f2(outer)},{f2(top)} "
               f"L{f2(outer + side * 4)},{f2(bot)} Q{f2((cx + outer) / 2)},{f2(bot - 6)} {f2(cx)},{f2(bot + 5)}Z",
               sw=MAIN, fill="#fff")
        for k in range(1, 9):
            y = top + bh * k / 9.5
            x0 = cx + side * 10
            x1 = outer - side * 10 + side * 3 * k / 9
            words = []
            x = x0
            while (x1 - x) * side > 6:
                L = rng.uniform(8, 24)
                x2 = x + side * L
                if (x1 - x2) * side < 0:
                    x2 = x1
                words.append(f"M{f2(x)},{f2(y)} L{f2(x2)},{f2(y)}")
                x = x2 + side * rng.uniform(3, 6)
            c.path(" ".join(words), sw=HAIR * 1.2)
    c.path(f"M{f2(cx)},{f2(top + 6)} L{f2(cx)},{f2(bot + 5)}", sw=THIN)
    ginkgo_leaf(c, cx + bw * 0.18, top + bh * 0.72, min(bh * 0.36, 30), -0.5)
    for k in range(5):
        x0 = w * (0.06 + 0.07 * k)
        c.path(f"M{f2(x0)},{f2(0)} L{f2(x0 + h * 0.5)},{f2(h * 0.6)}", sw=HAIR, extra=' stroke-dasharray="1 4"')
    return c.svg()


def letter(w: float, h: float, seed: int = 25) -> str:
    """写给古人的信：信封、抽出一半的信笺、一支毛笔和一方印。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    ew, eh = min(w * 0.36, h * 1.5), h * 0.62
    ex, ey = w * 0.32 - ew / 2, h * 0.3
    # 信笺（竖排行格）
    lx, ly, lw, lh = ex + ew * 0.18, ey - h * 0.22, ew * 0.64, eh * 0.9
    c.path(poly([(lx, ly), (lx + lw, ly), (lx + lw, ly + lh), (lx, ly + lh)], closed=True), sw=MAIN, fill="#fff")
    for k in range(1, 8):
        x = lx + lw * k / 8
        c.path(f"M{f2(x)},{f2(ly + 4)} L{f2(x)},{f2(ly + lh)}", sw=HAIR)
    for k in range(1, 7):
        x = lx + lw * k / 8 - lw / 16
        y = ly + 8
        y1 = ly + rng.uniform(0.3, 0.7) * lh
        pts = []
        while y < y1:
            pts.append((x + rng.uniform(-1.2, 1.2), y))
            y += rng.uniform(2.5, 4)
        c.path(poly(pts), sw=HAIR * 1.4)
    # 信封
    c.path(poly([(ex, ey), (ex + ew, ey), (ex + ew, ey + eh), (ex, ey + eh)], closed=True), sw=MAIN, fill="#fff")
    c.path(poly([(ex, ey), (ex + ew / 2, ey + eh * 0.5), (ex + ew, ey)]), sw=THIN)
    c.path(poly([(ex, ey + eh), (ex + ew * 0.42, ey + eh * 0.42)]), sw=HAIR)
    c.path(poly([(ex + ew, ey + eh), (ex + ew * 0.58, ey + eh * 0.42)]), sw=HAIR)
    sx, sy, ss = ex + ew * 0.72, ey + eh * 0.62, min(eh * 0.2, 16)
    c.path(poly([(sx, sy), (sx + ss, sy), (sx + ss, sy + ss), (sx, sy + ss)], closed=True), sw=0, fill="#000")
    m = ss * 0.16
    c.path(poly([(sx + m, sy + m), (sx + ss - m, sy + m), (sx + ss - m, sy + ss - m), (sx + m, sy + ss - m)], closed=True),
           sw=0.8, stroke="#fff")
    c.path(f"M{f2(sx + ss / 2)},{f2(sy + m)} L{f2(sx + ss / 2)},{f2(sy + ss - m)}", sw=0.8, stroke="#fff")
    # 毛笔
    a = math.radians(-18)
    ca, sa = math.cos(a), math.sin(a)
    bx, by = w * 0.56, h * 0.78
    L = min(w * 0.38, 170)

    def T(u, v):
        return (bx + u * ca - v * sa, by + u * sa + v * ca)
    c.path(poly([T(0, -2.8), T(L * 0.8, -2.8), T(L * 0.8, 2.8), T(0, 2.8)], closed=True), sw=MAIN, fill="#fff")
    c.path(poly([T(L * 0.8, -3.6), T(L * 0.86, -3.6), T(L * 0.86, 3.6), T(L * 0.8, 3.6)], closed=True), sw=MAIN, fill="#fff")
    tip = [T(L * 0.86, -3.4), T(L * 0.93, -3), T(L, 0), T(L * 0.93, 3), T(L * 0.86, 3.4)]
    c.path(smooth(tip) + "Z", sw=MAIN, fill="#000")
    c.path(poly([T(0, 0), T(-10, -4)]), sw=THIN)
    return c.svg()


# ---------------------------------------------------------------- 第二期新图

@lru_cache(maxsize=4)
def _font(name: str):
    from fontTools.ttLib import TTFont
    return TTFont(str(HERE.parent / "fonts" / name))


def glyph_path(ch: str, size: float, x: float, y: float, font: str = "YZSong-700.ttf") -> str:
    """把一个字转成 SVG 路径（SVG 以图片嵌入时读不到页面字体）。(x, y) 为字面框左上角，size 为字号。"""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    f = _font(font)
    upm = f["head"].unitsPerEm
    gs = f.getGlyphSet()
    name = f.getBestCmap()[ord(ch)]
    k = size / upm
    asc = f["hhea"].ascent
    desc = -f["hhea"].descent
    top = y + (size - (asc + desc) * k) / 2          # 字身在 size 高的方框里垂直居中
    pen = SVGPathPen(gs)
    gs[name].draw(TransformPen(pen, (k, 0, 0, -k, x, top + asc * k)))
    return pen.getCommands()


def lighthouse(w: float, h: float, seed: int = 30) -> str:
    """变声期：雨夜里的灯塔，光柱划开雨幕；礁石、近处浪线。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    sea = h * 0.8
    for _ in range(int(w * h / 700)):                      # 斜雨
        x, y, L = rng.uniform(-20, w + 10), rng.uniform(-5, sea + 5), rng.uniform(5, 12)
        c.path(f"M{f2(x)},{f2(y)} L{f2(x - L * 0.28)},{f2(y + L)}", sw=HAIR)
    cx = w * 0.72
    base = sea - h * 0.02
    body_h = h * 0.56
    top = base - body_h
    bw, tw = h * 0.1, h * 0.068                            # 塔身底宽、顶宽的一半
    lamp_y = top - h * 0.075
    # 光柱：白色楔形盖住雨线，像光把雨幕切开
    for d, L, sp in ((-1, w * 0.75, 0.085), (1, w * 0.3, 0.07)):
        a0 = math.pi if d < 0 else 0.0
        p1 = (cx + L * math.cos(a0 - sp * d), lamp_y + L * math.sin(-sp) * d * d)
        p2 = (cx + L * math.cos(a0 + sp * d), lamp_y + L * math.sin(sp))
        c.path(poly([(cx, lamp_y), p1, p2], closed=True), sw=0, fill="#fff")
        c.path(f"M{f2(cx)},{f2(lamp_y)} L{f2(p1[0])},{f2(p1[1])} M{f2(cx)},{f2(lamp_y)} L{f2(p2[0])},{f2(p2[1])}",
               sw=HAIR, extra=' stroke-dasharray="4 3"')
    # 礁石
    rock = [(cx - w * 0.2, h + 4), (cx - w * 0.15, sea + h * 0.02), (cx - w * 0.07, sea - h * 0.04),
            (cx - bw * 1.2, base), (cx + bw * 1.3, base - h * 0.01), (cx + w * 0.09, sea - h * 0.03),
            (cx + w * 0.17, sea + h * 0.03), (cx + w * 0.24, h + 4)]
    c.path(smooth(rock, t=0.8), sw=MAIN, fill="#fff")
    for _ in range(9):
        x = cx + rng.uniform(-w * 0.14, w * 0.15)
        y = rng.uniform(sea, h * 0.97)
        c.path(f"M{f2(x)},{f2(y)} l{f2(rng.uniform(4, 9))},{f2(rng.uniform(-1.5, 1.5))}", sw=HAIR)
    # 塔身、两道黑环、门窗
    body = [(cx - bw, base), (cx - tw, top), (cx + tw, top), (cx + bw, base)]
    c.path(poly(body, closed=True), sw=MAIN, fill="#fff")
    for f0, f1 in ((0.22, 0.34), (0.58, 0.7)):
        ya, yb = base - body_h * f0, base - body_h * f1
        wa, wb = bw + (tw - bw) * f0, bw + (tw - bw) * f1
        c.path(poly([(cx - wa, ya), (cx - wb, yb), (cx + wb, yb), (cx + wa, ya)], closed=True), sw=0, fill="#000")
    c.path(f"M{f2(cx - bw * 0.22)},{f2(base)} L{f2(cx - bw * 0.22)},{f2(base - h * 0.07)} "
           f"A{f2(bw * 0.22)},{f2(bw * 0.22)} 0 0 1 {f2(cx + bw * 0.22)},{f2(base - h * 0.07)} L{f2(cx + bw * 0.22)},{f2(base)}",
           sw=THIN, fill="#fff")
    for f in (0.46, 0.8):                                  # 小窗：一道竖缝
        y = base - body_h * f
        c.path(f"M{f2(cx)},{f2(y - 4)} L{f2(cx)},{f2(y + 4)}", sw=1.6)
    # 回廊、灯室、穹顶
    gw = tw * 1.45
    c.path(poly([(cx - gw, top), (cx + gw, top), (cx + gw, top - 3), (cx - gw, top - 3)], closed=True), sw=MAIN, fill="#fff")
    for k in range(9):
        x = cx - gw + 2 * gw * k / 8
        c.path(f"M{f2(x)},{f2(top - 3)} L{f2(x)},{f2(top - 9)}", sw=HAIR)
    c.path(f"M{f2(cx - gw)},{f2(top - 9)} L{f2(cx + gw)},{f2(top - 9)}", sw=THIN)
    lw, lh = tw * 0.85, h * 0.085
    ly0 = top - 3
    c.path(poly([(cx - lw, ly0), (cx - lw, ly0 - lh), (cx + lw, ly0 - lh), (cx + lw, ly0)], closed=True), sw=MAIN, fill="#fff")
    for k in (1, 2):
        x = cx - lw + 2 * lw * k / 3
        c.path(f"M{f2(x)},{f2(ly0)} L{f2(x)},{f2(ly0 - lh)}", sw=HAIR)
    for k in range(10):                                   # 灯光的细芒
        a = math.tau * k / 10 + 0.3
        r0, r1 = lw * 1.25, lw * 1.9
        c.path(f"M{f2(cx + r0 * math.cos(a))},{f2(lamp_y + r0 * math.sin(a))} "
               f"L{f2(cx + r1 * math.cos(a))},{f2(lamp_y + r1 * math.sin(a))}", sw=HAIR)
    c.path(f"M{f2(cx - lw * 1.05)},{f2(ly0 - lh)} A{f2(lw * 1.05)},{f2(lw * 0.9)} 0 0 1 {f2(cx + lw * 1.05)},{f2(ly0 - lh)}Z",
           sw=MAIN, fill="#000")
    c.path(f"M{f2(cx)},{f2(ly0 - lh - lw * 0.9)} L{f2(cx)},{f2(ly0 - lh - lw * 0.9 - 7)}", sw=THIN)
    # 近处浪线
    for r in range(7):
        y = sea + (h - sea) * (r + 0.5) / 7
        step = 9 + r * 3.5
        x = -rng.uniform(0, step)
        while x < w:
            if not (cx - w * 0.19 < x < cx + w * 0.23 and y > sea + h * 0.01):
                c.path(f"M{f2(x)},{f2(y)} q{f2(step * 0.25)},{f2(-1.5 - r * 0.35)} {f2(step * 0.5)},0", sw=HAIR + r * 0.05)
            x += step * rng.uniform(0.9, 1.4)
    return c.svg()


def pool(w: float, h: float, seed: int = 31) -> str:
    """最后五十米：俯视的泳道；分道线的浮子近池壁处涂黑，池底黑线到池壁前成 T 字；一道水花冲向终点。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    lanes = max(3, round(h / 30))
    ys = [h * (0.04 + 0.92 * k / lanes) for k in range(lanes + 1)]
    wall = w - 4
    c.path(f"M{f2(wall)},{f2(-2)} L{f2(wall)},{f2(h + 2)} M{f2(wall + 2.5)},{f2(-2)} L{f2(wall + 2.5)},{f2(h + 2)}", sw=THIN)
    for i in range(lanes):                                # 池底黑线与 T
        y = (ys[i] + ys[i + 1]) / 2
        x1 = wall - w * 0.05
        c.path(f"M{f2(w * 0.02)},{f2(y)} L{f2(x1)},{f2(y)}", sw=2.4)
        c.path(f"M{f2(x1)},{f2(y - (ys[1] - ys[0]) * 0.18)} L{f2(x1)},{f2(y + (ys[1] - ys[0]) * 0.18)}", sw=2.4)
    for y in ys:                                          # 分道线：一串浮子
        x, k = 3.0, 0
        while x < wall - 3:
            near = x > wall - w * 0.12 or x < w * 0.08
            r = 2.3 if k % 6 else 2.9
            c.add(f'<ellipse cx="{f2(x)}" cy="{f2(y)}" rx="{f2(r)}" ry="{f2(r * 0.8)}" '
                  f'fill="{"#000" if near else "#fff"}" stroke="#000" stroke-width="{HAIR}"/>')
            x += 5.6
            k += 1
    # 水面细纹
    for _ in range(int(w * h / 1100)):
        x, y = rng.uniform(10, wall - 20), rng.uniform(4, h - 4)
        if min(abs(y - yy) for yy in ys) < 4:
            continue
        s = rng.uniform(3, 6)
        c.path(f"M{f2(x)},{f2(y)} q{f2(s * 0.5)},-1.2 {f2(s)},0 q{f2(s * 0.5)},1.2 {f2(s)},0", sw=HAIR)
    # 冲刺的泳者：头、划水的手臂、身后的尾浪
    lane = lanes // 2
    y = (ys[lane] + ys[lane + 1]) / 2
    lh = ys[1] - ys[0]
    hx = wall - w * 0.16
    for k in range(6):                                     # 尾浪
        dx = 7 + k * 9
        c.path(f"M{f2(hx - dx)},{f2(y - lh * (0.1 + 0.05 * k))} q{f2(-4)},{f2(lh * (0.1 + 0.05 * k))} 0,{f2(lh * (0.2 + 0.1 * k))}",
               sw=HAIR if k > 2 else THIN)
    c.path(f"M{f2(hx - 3)},{f2(y - lh * 0.05)} C{f2(hx + 6)},{f2(y - lh * 0.42)} {f2(hx + 18)},{f2(y - lh * 0.36)} "
           f"{f2(hx + 22)},{f2(y - lh * 0.08)}", sw=MAIN)
    circle(c, hx, y + lh * 0.04, lh * 0.13)
    for _ in range(7):
        a = rng.uniform(-1.3, 1.3)
        r = rng.uniform(lh * 0.22, lh * 0.36)
        c.add(f'<circle cx="{f2(hx + 22 + r * math.cos(a) * 0.6)}" cy="{f2(y - lh * 0.08 + r * math.sin(a))}" r="0.7" fill="#000"/>')
    return c.svg()


def sakura_flower(c: Canvas, x: float, y: float, r: float, rot: float) -> None:
    for k in range(5):
        a = rot + math.tau * k / 5
        tip = (x + r * math.cos(a), y + r * math.sin(a))
        nx, ny = -math.sin(a) * r * 0.42, math.cos(a) * r * 0.42
        mx, my = x + r * 0.55 * math.cos(a), y + r * 0.55 * math.sin(a)
        notch = (x + r * 0.84 * math.cos(a), y + r * 0.84 * math.sin(a))
        c.path(f"M{f2(x)},{f2(y)} Q{f2(mx + nx)},{f2(my + ny)} {f2(tip[0] + nx * 0.4)},{f2(tip[1] + ny * 0.4)} "
               f"L{f2(notch[0])},{f2(notch[1])} L{f2(tip[0] - nx * 0.4)},{f2(tip[1] - ny * 0.4)} "
               f"Q{f2(mx - nx)},{f2(my - ny)} {f2(x)},{f2(y)}Z", sw=HAIR, fill="#fff")
    c.add(f'<circle cx="{f2(x)}" cy="{f2(y)}" r="{f2(r * 0.14)}" fill="#000"/>')


def cat_sakura(w: float, h: float, seed: int = 32) -> str:
    """寻猫记：春雨里的樱花枝，花瓣飘落；树篱前一只猫妈妈带着三只小猫，旁边一只小食盆。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    gy = h * 0.9
    for _ in range(int(w * h / 950)):                      # 雨
        x, y, L = rng.uniform(0, w), rng.uniform(-5, gy), rng.uniform(4, 9)
        c.path(f"M{f2(x)},{f2(y)} l{f2(-L * 0.12)},{f2(L)}", sw=HAIR)
    # 树篱：一丛圆团，底边被地面截平
    hx0, hx1 = w * 0.46, w * 1.04
    puffs = [(hx0 + (hx1 - hx0) * (k + 0.5) / 6, gy - h * rng.uniform(0.12, 0.2), h * rng.uniform(0.17, 0.22))
             for k in range(6)]
    puffs += [(hx0 + (hx1 - hx0) * rng.uniform(0.15, 0.85), gy - h * rng.uniform(0.3, 0.36), h * rng.uniform(0.1, 0.13))
              for _ in range(3)]
    c.defs.append(f'<clipPath id="hedge"><rect x="0" y="0" width="{f2(w)}" height="{f2(gy)}"/></clipPath>')
    c.add('<g clip-path="url(#hedge)">')
    canopy(c, puffs, sw=THIN, inner=False)
    c.add("</g>")
    for _ in range(45):                                    # 树篱叶子
        x, y = rng.uniform(hx0 + 6, hx1), rng.uniform(gy - h * 0.4, gy - h * 0.04)
        if any((x - px) ** 2 + (y - py) ** 2 < (r - 3) ** 2 for px, py, r in puffs):
            c.path(f"M{f2(x)},{f2(y)} q2,-2.5 4.5,-0.6", sw=HAIR)
    # 地面、猫、食盆
    c.path(f"M0,{f2(gy)} L{f2(w)},{f2(gy)}", sw=THIN)
    s = h * 0.34
    cat_back(c, w * 0.66, gy, s)
    for k, (dx, ss) in enumerate(((-0.16, 0.5), (0.1, 0.46), (0.19, 0.4))):
        cat_back(c, w * 0.66 + dx * w * 0.45, gy, s * ss)
    bx = w * 0.53
    c.add(f'<ellipse cx="{f2(bx)}" cy="{f2(gy - 5)}" rx="{f2(h * 0.06)}" ry="1.8" fill="#fff" stroke="#000" stroke-width="{THIN}"/>')
    c.path(f"M{f2(bx - h * 0.06)},{f2(gy - 5)} Q{f2(bx - h * 0.05)},{f2(gy)} {f2(bx)},{f2(gy)} "
           f"Q{f2(bx + h * 0.05)},{f2(gy)} {f2(bx + h * 0.06)},{f2(gy - 5)}", sw=THIN, fill="#fff")
    # 樱花枝：从左上角伸进来
    main = [(-8, h * 0.08), (w * 0.12, h * 0.15), (w * 0.26, h * 0.2), (w * 0.4, h * 0.29), (w * 0.5, h * 0.33)]
    limb(c, main, h * 0.034, h * 0.006, sw=THIN)
    sub = [(w * 0.19, h * 0.18), (w * 0.26, h * 0.1), (w * 0.34, h * 0.05)]
    limb(c, sub, h * 0.012, h * 0.004, sw=THIN)
    sub2 = [(w * 0.33, h * 0.25), (w * 0.37, h * 0.37), (w * 0.36, h * 0.46)]
    limb(c, sub2, h * 0.011, h * 0.004, sw=THIN)
    for pts in (main, sub, sub2):
        for (x0, y0), (x1, y1) in zip(pts[1:], pts[2:] + [pts[-1]]):
            for _ in range(3):
                t = rng.random()
                x, y = x0 + (x1 - x0) * t + rng.uniform(-8, 8), y0 + (y1 - y0) * t + rng.uniform(-9, 7)
                sakura_flower(c, x, y, rng.uniform(4.2, 6.2), rng.uniform(0, 1.3))
    for _ in range(14):                                    # 飘落的花瓣
        x, y = rng.uniform(w * 0.05, w * 0.6), rng.uniform(h * 0.35, gy - 6)
        a, r = rng.uniform(0, math.tau), rng.uniform(2.5, 3.6)
        c.path(f"M{f2(x)},{f2(y)} q{f2(r * math.cos(a + 0.8))},{f2(r * math.sin(a + 0.8))} {f2(r * 2 * math.cos(a))},{f2(r * 2 * math.sin(a))} "
               f"q{f2(-r * math.cos(a - 0.8))},{f2(-r * math.sin(a - 0.8))} {f2(-r * 2 * math.cos(a))},{f2(-r * 2 * math.sin(a))}Z",
               sw=HAIR, fill="#fff")
    return c.svg()


def desk_lamp(w: float, h: float, seed: int = 33) -> str:
    """十八而立：深夜的书桌，台灯照着写满红批的试卷；墙上日历圈着生日，窗外零星几盏灯。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    desk = h * 0.7
    # 窗：远处楼群涂黑，亮着的窗是白点
    wx0, wx1, wy0, wy1 = w * 0.5, w * 0.95, h * 0.05, desk - h * 0.14
    c.path(poly([(wx0, wy0), (wx1, wy0), (wx1, wy1), (wx0, wy1)], closed=True), sw=MAIN, fill="#fff")
    bx = wx0
    while bx < wx1 - 2:
        bw = rng.uniform(0.07, 0.14) * (wx1 - wx0)
        bh = rng.uniform(0.2, 0.55) * (wy1 - wy0)
        x1 = min(bx + bw, wx1)
        c.path(poly([(bx, wy1), (bx, wy1 - bh), (x1, wy1 - bh), (x1, wy1)], closed=True), sw=0, fill="#000")
        for _ in range(int(bh / 9)):
            if rng.random() < 0.35:
                x, y = rng.uniform(bx + 2, x1 - 4), rng.uniform(wy1 - bh + 3, wy1 - 5)
                c.path(poly([(x, y), (x + 2.2, y), (x + 2.2, y + 3), (x, y + 3)], closed=True), sw=0, fill="#fff")
        bx = x1 + rng.uniform(0, 5)
    mx, my, mr = wx0 + (wx1 - wx0) * 0.78, wy0 + (wy1 - wy0) * 0.22, (wy1 - wy0) * 0.08
    c.path(f"M{f2(mx)},{f2(my - mr)} A{f2(mr)},{f2(mr)} 0 1 0 {f2(mx)},{f2(my + mr)} "
           f"A{f2(mr * 0.75)},{f2(mr)} 0 1 1 {f2(mx)},{f2(my - mr)}Z", sw=THIN, fill="#fff")
    for x in ((wx0 + wx1) / 2,):
        c.path(f"M{f2(x)},{f2(wy0)} L{f2(x)},{f2(wy1)}", sw=MAIN)
    c.path(f"M{f2(wx0)},{f2(wy0 + (wy1 - wy0) * 0.42)} L{f2(wx1)},{f2(wy0 + (wy1 - wy0) * 0.42)}", sw=THIN)
    c.path(f"M{f2(wx0 - 4)},{f2(wy1)} L{f2(wx1 + 4)},{f2(wy1)} L{f2(wx1 + 4)},{f2(wy1 + 3)} L{f2(wx0 - 4)},{f2(wy1 + 3)}Z",
           sw=THIN, fill="#fff")
    # 日历：圈出生日
    cx0, cy0, cw, ch = w * 0.08, h * 0.08, w * 0.25, h * 0.36
    c.path(f"M{f2(cx0 + cw / 2)},{f2(cy0 - 7)} L{f2(cx0 + cw * 0.3)},{f2(cy0)} M{f2(cx0 + cw / 2)},{f2(cy0 - 7)} "
           f"L{f2(cx0 + cw * 0.7)},{f2(cy0)}", sw=HAIR)
    c.path(poly([(cx0, cy0), (cx0 + cw, cy0), (cx0 + cw, cy0 + ch), (cx0, cy0 + ch)], closed=True), sw=MAIN, fill="#fff")
    c.path(poly([(cx0, cy0), (cx0 + cw, cy0), (cx0 + cw, cy0 + ch * 0.18), (cx0, cy0 + ch * 0.18)], closed=True), sw=0, fill="#000")
    gx0, gy0 = cx0 + cw * 0.06, cy0 + ch * 0.26
    cs, rs = cw * 0.88 / 7, ch * 0.68 / 5
    for r in range(5):
        for k in range(7):
            x, y = gx0 + k * cs, gy0 + r * rs
            if r == 0 and k < 2 or r == 4 and k > 3:
                continue
            c.path(f"M{f2(x + cs * 0.3)},{f2(y + rs * 0.45)} l{f2(cs * 0.35)},0", sw=HAIR * 1.6)
    ox, oy = gx0 + 4 * cs + cs * 0.47, gy0 + 3 * rs + rs * 0.45
    c.path(f"M{f2(ox + cs * 0.55)},{f2(oy - rs * 0.1)} C{f2(ox + cs * 0.6)},{f2(oy - rs * 0.6)} {f2(ox - cs * 0.6)},{f2(oy - rs * 0.6)} "
           f"{f2(ox - cs * 0.62)},{f2(oy)} C{f2(ox - cs * 0.6)},{f2(oy + rs * 0.55)} {f2(ox + cs * 0.6)},{f2(oy + rs * 0.5)} "
           f"{f2(ox + cs * 0.5)},{f2(oy - rs * 0.3)}", sw=THIN)
    # 书桌
    c.path(f"M0,{f2(desk)} L{f2(w)},{f2(desk)}", sw=MAIN)
    c.path(f"M0,{f2(desk + 5)} L{f2(w)},{f2(desk + 5)}", sw=THIN)
    # 试卷两张，红批画成勾叉
    for (px, py, pw, ph, rot) in ((w * 0.42, desk + h * 0.1, w * 0.3, h * 0.16, -4), (w * 0.52, desk + h * 0.07, w * 0.28, h * 0.17, 5)):
        c.add(f'<g transform="rotate({rot} {f2(px + pw / 2)} {f2(py + ph / 2)})">')
        c.path(poly([(px, py), (px + pw, py), (px + pw, py + ph), (px, py + ph)], closed=True), sw=THIN, fill="#fff")
        for k in range(1, 7):
            y = py + ph * k / 7.5
            c.path(f"M{f2(px + pw * 0.08)},{f2(y)} L{f2(px + pw * rng.uniform(0.6, 0.92))},{f2(y)}", sw=HAIR)
        for k in range(3):
            x, y = px + pw * rng.uniform(0.15, 0.8), py + ph * rng.uniform(0.2, 0.8)
            if rng.random() < 0.5:
                c.path(f"M{f2(x)},{f2(y)} l3,3 l6,-7", sw=THIN)
            else:
                c.path(f"M{f2(x)},{f2(y)} l5,5 M{f2(x + 5)},{f2(y)} l-5,5", sw=THIN)
        c.add("</g>")
    # 台灯：底座、两节灯臂、灯罩、光
    lx, ly = w * 0.2, desk + h * 0.04
    j1 = (lx + w * 0.07, desk - h * 0.3)
    j2 = (lx + w * 0.2, desk - h * 0.4)
    sx, sy = j2[0] + w * 0.08, j2[1] + h * 0.04
    hit = (w * 0.56, desk + h * 0.16)
    for k in range(7):
        t = k / 6
        ex = hit[0] - w * 0.19 + w * 0.36 * t
        ey = hit[1] + h * 0.03 - h * 0.05 * t
        c.path(f"M{f2(sx + 6)},{f2(sy + 10)} L{f2(ex)},{f2(ey)}", sw=HAIR, extra=' stroke-dasharray="1.5 3.5"')
    c.add(f'<ellipse cx="{f2(lx)}" cy="{f2(ly)}" rx="{f2(w * 0.07)}" ry="{f2(h * 0.02)}" fill="#fff" stroke="#000" stroke-width="{MAIN}"/>')
    for a, b in (((lx, ly - 2), j1), (j1, j2), (j2, (sx, sy))):
        c.path(f"M{f2(a[0])},{f2(a[1])} L{f2(b[0])},{f2(b[1])}", sw=2.2)
        c.path(f"M{f2(a[0])},{f2(a[1])} L{f2(b[0])},{f2(b[1])}", sw=0.9, stroke="#fff")
    for p in (j1, j2):
        circle(c, p[0], p[1], 3.2)
    shade = [(sx - 6, sy - 9), (sx + 8, sy - 12), (sx + 22, sy + 14), (sx - 4, sy + 22)]
    c.path(poly(shade, closed=True), sw=MAIN, fill="#fff")
    c.path(f"M{f2(sx - 4)},{f2(sy + 22)} Q{f2(sx + 10)},{f2(sy + 24)} {f2(sx + 22)},{f2(sy + 14)}", sw=MAIN, fill="#000")
    # 笔
    c.path(f"M{f2(w * 0.78)},{f2(desk + h * 0.22)} L{f2(w * 0.9)},{f2(desk + h * 0.15)}", sw=2.4)
    c.path(f"M{f2(w * 0.78)},{f2(desk + h * 0.22)} L{f2(w * 0.9)},{f2(desk + h * 0.15)}", sw=1.0, stroke="#fff")
    return c.svg()


def scroll(w: float, h: float, seed: int = 34, text: str = "天下为公") -> str:
    """相逢传赤心：墙上一幅「天下为公」的立轴，挂绳、天杆、绫边、朱印、轴头。"""
    c = Canvas(w, h)
    H = h * 0.9
    W = min(w * 0.26, H * 0.36)
    x0, y0 = w / 2 - W / 2, h * 0.07
    # 挂绳与钉
    c.path(f"M{f2(w / 2 - W * 0.32)},{f2(y0)} L{f2(w / 2)},{f2(y0 - h * 0.055)} L{f2(w / 2 + W * 0.32)},{f2(y0)}", sw=THIN)
    circle(c, w / 2, y0 - h * 0.055, 1.6)
    # 天杆
    c.path(poly([(x0 - 3, y0 - 2.5), (x0 + W + 3, y0 - 2.5), (x0 + W + 3, y0 + 2.5), (x0 - 3, y0 + 2.5)], closed=True),
           sw=MAIN, fill="#000")
    # 绫边与画心
    c.path(poly([(x0, y0 + 2.5), (x0 + W, y0 + 2.5), (x0 + W, y0 + H), (x0, y0 + H)], closed=True), sw=MAIN, fill="#fff")
    m = W * 0.13
    py0, py1 = y0 + H * 0.17, y0 + H * 0.86
    c.path(poly([(x0 + m, py0), (x0 + W - m, py0), (x0 + W - m, py1), (x0 + m, py1)], closed=True), sw=THIN, fill="#fff")
    for yy in (y0 + H * 0.09, y0 + H * 0.105):              # 天头上的两道「惊燕」线
        c.path(f"M{f2(x0 + W * 0.3)},{f2(yy)} L{f2(x0 + W * 0.3)},{f2(yy + H * 0.05)}", sw=HAIR)
        c.path(f"M{f2(x0 + W * 0.7)},{f2(yy)} L{f2(x0 + W * 0.7)},{f2(yy + H * 0.05)}", sw=HAIR)
    # 四个字竖排
    size = min((W - 2 * m) * 0.7, (py1 - py0) * 0.8 / len(text))
    ty = py0 + (py1 - py0 - size * len(text) * 1.08) / 2 - size * 0.2
    for k, ch in enumerate(text):
        c.path(glyph_path(ch, size, w / 2 - size / 2, ty + k * size * 1.08), sw=0, fill="#000")
    # 印章：黑底白框
    ss = size * 0.34
    sx, sy = x0 + W - m - ss - size * 0.12, ty + len(text) * size * 1.08 + size * 0.1
    c.path(poly([(sx, sy), (sx + ss, sy), (sx + ss, sy + ss), (sx, sy + ss)], closed=True), sw=0, fill="#000")
    c.path(poly([(sx + ss * 0.16, sy + ss * 0.16), (sx + ss * 0.84, sy + ss * 0.16), (sx + ss * 0.84, sy + ss * 0.84),
                 (sx + ss * 0.16, sy + ss * 0.84)], closed=True), sw=0.6, stroke="#fff")
    # 地杆与轴头
    yb = y0 + H
    c.path(poly([(x0 - 2, yb), (x0 + W + 2, yb), (x0 + W + 2, yb + 5), (x0 - 2, yb + 5)], closed=True), sw=MAIN, fill="#fff")
    for x in (x0 - 2, x0 + W + 2):
        c.add(f'<ellipse cx="{f2(x + (-4 if x < w / 2 else 4))}" cy="{f2(yb + 2.5)}" rx="4.5" ry="4" fill="#000"/>')
    return c.svg()


def chain_links(c: Canvas, pts, link: float = 3.4, sw: float = HAIR) -> None:
    """沿一条线画一串铁链：扁环与侧环交替。"""
    acc, k = 0.0, 0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        while acc < seg:
            t = acc / seg
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            ry = link * (0.42 if k % 2 == 0 else 0.14)
            c.add(f'<ellipse cx="{f2(x)}" cy="{f2(y)}" rx="{f2(link * 0.62)}" ry="{f2(ry)}" transform="rotate({ang:.1f} {f2(x)} {f2(y)})" '
                  f'fill="none" stroke="#000" stroke-width="{sw}"/>')
            acc += link
            k += 1
        acc -= seg


def chain_bridge(w: float, h: float, seed: int = 35) -> str:
    """赓续长征：泸定桥——两岸桥头堡之间十三根铁索，桥板残缺，脚下大渡河奔涌。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    ax, bx = w * 0.1, w * 0.9
    deck = h * 0.44
    sag = h * 0.1

    def cat(y, s):
        return [(x, y + s * (1 - ((x - (ax + bx) / 2) / ((bx - ax) / 2)) ** 2)) for x in frange(ax, bx, 3)]
    # 河水
    for _ in range(int(w / 7)):
        y = rng.uniform(h * 0.72, h * 0.98)
        x = rng.uniform(-20, w)
        streak(c, x, y, x + rng.uniform(25, 60), y + rng.uniform(-1.5, 1.5), thick=rng.uniform(0.35, 0.9))
    for _ in range(int(w / 12)):
        x, y = rng.uniform(0, w), rng.uniform(h * 0.7, h)
        c.path(f"M{f2(x)},{f2(y)} q3,-2.2 6,0", sw=HAIR)
    # 两岸崖壁
    for side in (-1, 1):
        x_edge = ax if side < 0 else bx
        pts = [(x_edge - side * w * 0.02, deck + h * 0.06), (x_edge + side * w * 0.01, h * 0.62),
               (x_edge + side * w * 0.035, h * 0.8), (x_edge + side * w * 0.02, h + 4)]
        outer = side * w * 0.2                             # 崖体朝画外延伸
        c.path(smooth(pts, t=0.8) + f" L{f2(x_edge + outer)},{f2(h + 4)} L{f2(x_edge + outer)},{f2(deck + h * 0.06)}Z",
               sw=THIN, fill="#fff")
        for _ in range(14):
            x = x_edge - side * rng.uniform(w * 0.005, w * 0.1)
            y = rng.uniform(deck + h * 0.1, h)
            c.path(f"M{f2(x)},{f2(y)} l{f2(side * rng.uniform(-1, 1))},{f2(rng.uniform(6, 14))}", sw=HAIR)
    # 桥板（中段缺了一截）
    for x in frange(ax + 4, bx - 4, 4.2):
        if w * 0.36 < x < w * 0.52:
            continue
        y = deck + sag * (1 - ((x - (ax + bx) / 2) / ((bx - ax) / 2)) ** 2)
        c.path(f"M{f2(x)},{f2(y - 1.8)} L{f2(x + 1.2)},{f2(y + 2.6)}", sw=HAIR * 1.6)
    # 铁索：底索成束，两侧扶手索各两根
    for k in range(4):
        chain_links(c, cat(deck - 1.5 + k * 1.3, sag), link=3.2)
    for k, dy in enumerate((h * 0.13, h * 0.16)):
        chain_links(c, cat(deck - dy, sag * 0.8), link=3.2)
    # 桥头堡
    for x in (ax, bx):
        tw, th = w * 0.05, h * 0.36
        c.path(poly([(x - tw, deck + h * 0.06), (x - tw, deck - th * 0.55), (x + tw, deck - th * 0.55), (x + tw, deck + h * 0.06)], closed=True),
               sw=MAIN, fill="#fff")
        for r in range(1, 6):
            y = deck + h * 0.06 - r * th * 0.1
            c.path(f"M{f2(x - tw)},{f2(y)} L{f2(x + tw)},{f2(y)}", sw=HAIR)
        c.path(f"M{f2(x - tw * 0.35)},{f2(deck + h * 0.06)} L{f2(x - tw * 0.35)},{f2(deck - th * 0.2)} "
               f"A{f2(tw * 0.35)},{f2(tw * 0.35)} 0 0 1 {f2(x + tw * 0.35)},{f2(deck - th * 0.2)} L{f2(x + tw * 0.35)},{f2(deck + h * 0.06)}",
               sw=THIN, fill="#000")
        ry = deck - th * 0.55
        c.path(f"M{f2(x - tw * 1.55)},{f2(ry - 1)} Q{f2(x - tw * 0.8)},{f2(ry - 3)} {f2(x - tw * 0.4)},{f2(ry - th * 0.28)} "
               f"L{f2(x + tw * 0.4)},{f2(ry - th * 0.28)} Q{f2(x + tw * 0.8)},{f2(ry - 3)} {f2(x + tw * 1.55)},{f2(ry - 1)}Z",
               sw=MAIN, fill="#000")
    for k in range(3):
        y = h * rng.uniform(0.05, 0.25)
        x0 = w * rng.uniform(0.2, 0.6)
        streak(c, x0, y + 2, x0 + w * rng.uniform(0.12, 0.2), y - 2, thick=rng.uniform(0.7, 1.1))
    return c.svg()


def cloud(c: Canvas, x: float, base: float, width: float, rng: random.Random, idx: int) -> None:
    """积云：顶部几团圆鼓起，底边平直。"""
    n = max(3, round(width / 26))
    puffs = []
    for k in range(n):
        t = (k + 0.5) / n
        r = width / n * rng.uniform(0.75, 1.05) * (0.8 + 0.55 * math.sin(math.pi * t))
        puffs.append((x + width * t, base - r * rng.uniform(0.35, 0.7), r))
    top = min(y - r for _, y, r in puffs)
    for k in range(2):
        i = rng.randrange(1, n - 1)
        _, y, r = puffs[i]
        puffs.append((x + width * rng.uniform(0.3, 0.7), y - r * 0.6, r * 0.8))
    cid = f"cl{idx}"
    c.defs.append(f'<clipPath id="{cid}"><rect x="{f2(x - width)}" y="{f2(top - width)}" width="{f2(width * 3)}" '
                  f'height="{f2(base - top + width)}"/></clipPath>')
    c.add(f'<g clip-path="url(#{cid})">')
    canopy(c, puffs, sw=THIN, inner=True)
    c.add("</g>")
    c.path(f"M{f2(x + width * 0.08)},{f2(base)} L{f2(x + width * 0.92)},{f2(base)}", sw=THIN)
    for k in range(2):
        yy = base + 3 + k * 3
        c.path(f"M{f2(x + width * (0.2 + 0.1 * k))},{f2(yy)} L{f2(x + width * (0.7 - 0.08 * k))},{f2(yy)}", sw=HAIR)


def sky_birds(w: float, h: float, seed: int = 36) -> str:
    """无题：「如果你发现你还是更喜欢飞鸟和云」——几朵积云，一群飞鸟朝右上方飞去。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    for _ in range(4):                                     # 风线先画，云压在上面
        y, x0 = h * rng.uniform(0.35, 0.95), w * rng.uniform(0, 0.6)
        streak(c, x0, y, x0 + w * rng.uniform(0.15, 0.3), y - rng.uniform(1, 4), thick=rng.uniform(0.6, 1.0))
    specs = [(0.05, 0.3, 0.42), (0.55, 0.22, 0.38), (0.3, 0.62, 0.5), (0.68, 0.8, 0.28)]
    for i, (fx, fy, fw) in enumerate(specs):
        if fy * h < 30:
            continue
        cloud(c, w * fx, h * fy, w * fw, rng, i)
    n = 11
    for k in range(n):
        t = k / (n - 1)
        x = w * (0.38 + 0.5 * t) + rng.uniform(-14, 14)
        y = h * (0.52 - 0.42 * t) + rng.uniform(-10, 10)
        bird(c, x, y, rng.uniform(4, 8) * (1.25 - 0.5 * t), rng, sw=THIN)
    return c.svg()


def ma_tou_wall(c: Canvas, x0: float, x1: float, base: float, top: float, steps: int = 2) -> None:
    """一面马头墙（山墙正面）：白墙，顶部从屋脊向两侧跌落成宽而矮的台阶，
    每级压一道挑出的黑瓦，外端上翘成「马头」。top 为最高一级的高度。"""
    mid = (x0 + x1) / 2
    tread = (x1 - x0) / (2 * steps + 1.4)
    riser = tread * 0.42
    # 左半边轮廓：从墙脚往上，逐级向内升高，到屋脊中点
    left = [(x0, base)]
    for k in range(steps, -1, -1):
        y = top + k * riser
        xa = mid - (0.7 + k) * tread
        xb = mid - (0.7 + k - 1) * tread if k else mid
        left += [(xa, y), (xb, y)]
    right = [(2 * mid - x, y) for x, y in reversed(left)]
    c.path(poly(left + right, closed=True), sw=MAIN, fill="#fff")
    # 瓦顶：每级一道黑色压顶，外端挑出、上翘
    for k in range(steps + 1):
        y = top + k * riser
        xo = (0.7 + k) * tread                           # 这一级外端到中线的距离
        xi = (0.7 + k - 1) * tread if k else 0.0
        for s in (-1, 1):
            xa, xb = mid + s * xi, mid + s * xo
            lo, hi = min(xa, xb), max(xa, xb)
            c.path(poly([(lo - 1.5, y), (hi + 1.5, y), (hi + 1, y - 3.4), (lo - 1, y - 3.4)], closed=True), sw=0, fill="#000")
            c.path(f"M{f2(xb + s * 1.5)},{f2(y - 1.2)} q{f2(s * 2.6)},-0.4 {f2(s * 3.4)},-4.6", sw=MAIN)


def jiangnan_moon(w: float, h: float, seed: int = 37) -> str:
    """浙里皮影：月光下的江南——马头墙、石拱桥、河水，窗里一盏灯；月影碎在水面。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    water = h * 0.74
    r = min(w, h) * 0.13
    mx, my = w * 0.74, h * 0.2
    circle(c, mx, my, r)
    for k in range(2):
        y, x0 = my + r * (0.2 + 0.55 * k), mx - r * (1.6 - k)
        streak(c, x0, y, x0 + r * 2.6, y - 2, thick=0.9)
    # 屋群：远处的矮、近处的高，左右错开；远的先画，被近的挡住
    ww = min(w * 0.2, h * 0.3)
    houses = [(0.5, 0.56, 0.9), (0.84, 0.54, 0.85), (0.36, 0.6, 1.0), (0.68, 0.5, 1.15), (0.98, 0.58, 1.05)]
    for fx, ftop, sc in houses:
        x0, x1 = w * fx - ww * sc / 2, w * fx + ww * sc / 2
        top = h * ftop
        ma_tou_wall(c, x0, x1, water, top, steps=2)
        eave = top + 2 * (ww * sc / 5.4) * 0.42 + 4
        for k in range(rng.randint(1, 2)):                 # 小窗
            wx = x0 + (x1 - x0) * rng.uniform(0.28, 0.62)
            wy = eave + (water - eave) * rng.uniform(0.18, 0.42)
            c.path(poly([(wx, wy), (wx + 6, wy), (wx + 6, wy + 8), (wx, wy + 8)], closed=True), sw=THIN, fill="#000")
    # 亮着灯的窗、门口灯笼
    lx, ly = w * 0.64, water - h * 0.12
    c.path(poly([(lx, ly), (lx + 10, ly), (lx + 10, ly + 12), (lx, ly + 12)], closed=True), sw=THIN, fill="#fff")
    c.path(f"M{f2(lx + 5)},{f2(ly)} L{f2(lx + 5)},{f2(ly + 12)} M{f2(lx)},{f2(ly + 6)} L{f2(lx + 10)},{f2(ly + 6)}", sw=HAIR)
    for k in range(8):
        a = math.tau * k / 8
        c.path(f"M{f2(lx + 5 + 9 * math.cos(a))},{f2(ly + 6 + 9 * math.sin(a))} "
               f"L{f2(lx + 5 + 13 * math.cos(a))},{f2(ly + 6 + 13 * math.sin(a))}", sw=HAIR)
    # 石拱桥：半圆桥洞，桥面拱起，栏板一道
    bx, br = w * 0.15, min(h * 0.075, w * 0.075)
    top_y = water - br * 1.45
    hump = [(bx - br * 2.7, water), (bx - br * 1.6, water - br * 0.95), (bx, top_y), (bx + br * 1.6, water - br * 0.95),
            (bx + br * 2.7, water)]
    c.path(smooth(hump, t=0.9) + f" L{f2(bx + br)},{f2(water)} A{f2(br)},{f2(br)} 0 0 0 {f2(bx - br)},{f2(water)}Z",
           sw=MAIN, fill="#fff")
    rail = [(x, y - 5) for x, y in hump[1:-1]]
    c.path(smooth([(hump[0][0] + br * 0.4, water - br * 0.3 - 5)] + rail + [(hump[-1][0] - br * 0.4, water - br * 0.3 - 5)], t=0.9),
           sw=THIN)
    for k in range(-4, 5):                                 # 栏板立柱
        x = bx + k * br * 0.5
        t = 1 - (abs(x - bx) / (br * 2.7)) ** 2
        y = water - br * 0.3 - (top_y - water + br * 0.3) * -t
        c.path(f"M{f2(x)},{f2(y - 5)} l0,4", sw=HAIR)
    c.path(f"M{f2(bx - br)},{f2(water)} A{f2(br)},{f2(br)} 0 0 0 {f2(bx + br)},{f2(water)}", sw=HAIR,
           extra=' stroke-dasharray="3 3"')                  # 桥洞倒影
    # 河水：横纹，月影碎成短线
    c.path(f"M0,{f2(water)} L{f2(w)},{f2(water)}", sw=THIN)
    for k in range(9):
        y = water + (h - water) * (k + 0.6) / 9
        x = rng.uniform(0, 30)
        while x < w:
            L = rng.uniform(12, 36)
            if abs(x - mx) < r * 1.2:
                L = rng.uniform(4, 10)
            c.path(f"M{f2(x)},{f2(y)} l{f2(L)},0", sw=HAIR if abs(x - mx) > r * 1.2 else THIN)
            x += L + rng.uniform(8, 22)
    return c.svg()


def bench(w: float, h: float, seed: int = 38) -> str:
    """余温如常：银杏树下一张空长椅，椅上一杯饮料还冒着一缕热气，落叶几片。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    gy = h * 0.86
    c.path(f"M0,{f2(gy)} L{f2(w)},{f2(gy)}", sw=THIN)
    for k in range(3):
        y = gy + (h - gy) * (k + 1) / 4
        c.path(f"M{f2(w * (0.05 + 0.1 * k))},{f2(y)} L{f2(w * (0.95 - 0.1 * k))},{f2(y)}", sw=HAIR)
    # 左上角探进来的一枝银杏，叶子垂着
    br = [(-8, h * 0.04), (w * 0.16, h * 0.1), (w * 0.34, h * 0.13), (w * 0.52, h * 0.12)]
    limb(c, br, h * 0.022, h * 0.005, sw=THIN)
    tw = [(w * 0.22, h * 0.115), (w * 0.28, h * 0.19), (w * 0.3, h * 0.25)]
    limb(c, tw, h * 0.008, h * 0.003, sw=THIN)
    for pts in (br, tw):
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            for _ in range(4):
                t = rng.random()
                ginkgo_leaf(c, xa + (xb - xa) * t, ya + (yb - ya) * t + 1, rng.uniform(7, 11),
                            math.pi + rng.uniform(-0.6, 0.6), sw=HAIR)
    # 长椅
    x0, x1 = w * 0.3, w * 0.84
    seat = gy - min(h * 0.16, (x1 - x0) * 0.3)             # 椅面高约为椅长的三成
    back0, back1 = seat - min(h * 0.14, (x1 - x0) * 0.26), seat - h * 0.035
    for x in (x0 + 8, x1 - 8):                             # 椅背立柱
        c.path(f"M{f2(x)},{f2(back0 - 3)} L{f2(x)},{f2(seat)}", sw=MAIN)
    for k in range(3):                                     # 椅背横条
        y = back0 + (back1 - back0) * k / 2
        c.path(poly([(x0, y), (x1, y), (x1, y + 5), (x0, y + 5)], closed=True), sw=THIN, fill="#fff")
    for k in range(3):                                     # 椅面横条（略有透视）
        y = seat + k * 4.4
        c.path(poly([(x0 - k * 3, y), (x1 + k * 3, y), (x1 + k * 3, y + 3.2), (x0 - k * 3, y + 3.2)], closed=True),
               sw=THIN, fill="#fff")
    for x, d in ((x0 - 2, -1), (x1 + 2, 1)):              # 扶手与椅腿
        arm = seat - (seat - back0) * 0.5
        c.path(f"M{f2(x - d * 4)},{f2(arm)} L{f2(x + d * 10)},{f2(arm)} q{f2(d * 5)},0 {f2(d * 4)},6", sw=MAIN)
        c.path(f"M{f2(x)},{f2(arm)} L{f2(x)},{f2(seat + 13)}", sw=MAIN)
        c.path(f"M{f2(x)},{f2(seat + 13)} L{f2(x - d * 3)},{f2(gy)} M{f2(x)},{f2(seat + 13)} L{f2(x + d * 7)},{f2(gy)}", sw=MAIN)
    # 纸杯与热气
    cx, cy = x0 + (x1 - x0) * 0.68, seat
    c.path(poly([(cx - 6, cy - 16), (cx + 6, cy - 16), (cx + 4.5, cy), (cx - 4.5, cy)], closed=True), sw=THIN, fill="#fff")
    c.path(poly([(cx - 6.8, cy - 18.5), (cx + 6.8, cy - 18.5), (cx + 6.4, cy - 16), (cx - 6.4, cy - 16)], closed=True), sw=THIN, fill="#000")
    c.path(f"M{f2(cx - 5.4)},{f2(cy - 10)} L{f2(cx + 5.4)},{f2(cy - 10)} M{f2(cx - 5.1)},{f2(cy - 6)} L{f2(cx + 5.1)},{f2(cy - 6)}", sw=HAIR)
    for k, dx in enumerate((-2.5, 2.5)):
        y0 = cy - 21
        c.path(f"M{f2(cx + dx)},{f2(y0)} c{f2(-4 + k * 2)},-5 {f2(4 - k)},-8 0,-13 c{f2(-3.5)},-4 {f2(2.5)},-7 0,-11", sw=HAIR * 1.2)
    # 银杏落叶
    for _ in range(9):
        x, y = rng.uniform(w * 0.25, w * 0.95), rng.uniform(h * 0.15, gy - 4)
        ginkgo_leaf(c, x, y, rng.uniform(6, 10), rng.uniform(-2.4, 2.4), sw=HAIR)
    for _ in range(5):
        x = rng.uniform(w * 0.3, w * 0.95)
        ginkgo_leaf(c, x, gy - 1, rng.uniform(5, 8), rng.uniform(1.2, 1.9), sw=HAIR)
    return c.svg()


def ivy_leaf(c: Canvas, x: float, y: float, s: float, ang: float) -> None:
    """藤叶：心形小叶，(x, y) 为叶柄处。"""
    ca, sa = math.cos(ang), math.sin(ang)

    def T(px, py):
        return f"{f2(x + px * ca - py * sa)},{f2(y + px * sa + py * ca)}"
    c.path(f"M{T(0, 0)} C{T(-s * 0.9, -s * 0.2)} {T(-s * 0.7, -s * 1.1)} {T(0, -s * 1.25)} "
           f"C{T(s * 0.7, -s * 1.1)} {T(s * 0.9, -s * 0.2)} {T(0, 0)}Z", sw=HAIR, fill="#fff")
    c.path(f"M{T(0, 0)} L{T(0, -s)}", sw=HAIR)


def brick_ivy(w: float, h: float, seed: int = 40) -> str:
    """青春颂：「红砖覆上幽香」「丘原白鸟入楼」——鄞中的红砖墙与花格砖窗，藤蔓爬上墙，几只白鸟飞过。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    y0 = h * 0.22
    brick_wall(c, -2, y0, w + 2, h + 2, course=max(4.6, h / 40))
    # 花格砖窗：菱形镂空排成方阵
    px0, px1, py0, py1 = w * 0.48, w * 0.8, y0 + h * 0.12, h * 0.9
    c.path(poly([(px0, py0), (px1, py0), (px1, py1), (px0, py1)], closed=True), sw=MAIN, fill="#fff")
    cell = (py1 - py0) / max(4, round((py1 - py0) / 16))
    y = py0 + cell / 2
    while y < py1 - cell * 0.3:
        x = px0 + cell / 2
        while x < px1 - cell * 0.3:
            d = cell * 0.36
            c.path(poly([(x, y - d), (x + d, y), (x, y + d), (x - d, y)], closed=True), sw=0, fill="#000")
            x += cell
        y += cell
    c.path(poly([(px0 - 3, py1), (px1 + 3, py1), (px1 + 3, py1 + 3.5), (px0 - 3, py1 + 3.5)], closed=True), sw=THIN, fill="#fff")
    # 藤蔓：从左下角爬上墙头
    vine = [(-4, h * 0.98), (w * 0.08, h * 0.72), (w * 0.05, h * 0.5), (w * 0.14, h * 0.36), (w * 0.24, y0 + 2), (w * 0.36, y0 - 4)]
    c.path(smooth(vine), sw=THIN)
    for (xa, ya), (xb, yb) in zip(vine, vine[1:]):
        for _ in range(5):
            t = rng.random()
            x, y = xa + (xb - xa) * t, ya + (yb - ya) * t
            ivy_leaf(c, x, y, rng.uniform(4.5, 7), rng.uniform(-2.2, 2.2))
    # 白鸟
    for k in range(4):
        bird(c, w * (0.6 + 0.09 * k) + rng.uniform(-6, 6), y0 * (0.75 - 0.12 * k) + rng.uniform(-3, 3),
             rng.uniform(5, 8), rng, sw=THIN)
    return c.svg()


def plane_leaf(c: Canvas, x: float, y: float, s: float, ang: float, sw: float = THIN) -> None:
    """悬铃木（梧桐）叶：五个尖裂片，叶脉从叶基放射，叶柄朝下；(x, y) 为叶基，ang 为整片的转角。"""
    ca, sa = math.cos(ang), math.sin(ang)

    def T(px, py):
        return (x + px * ca - py * sa, y + px * sa + py * ca)
    lobes = [(-90, 1.0), (-35, 0.82), (15, 0.5), (165, 0.5), (215, 0.82)]
    pts = []
    for k, (a, L) in enumerate(lobes):
        an = lobes[(k + 1) % len(lobes)][0] + (360 if k == len(lobes) - 1 else 0)
        ra = math.radians(a)
        tip = (s * L * math.cos(ra), s * L * math.sin(ra))
        for da, rr in ((-19, 0.74), (-8, 0.8), (0, 1.0), (8, 0.8), (19, 0.74)):   # 宽裂片，两肩带齿
            r2 = math.radians(a + da)
            pts.append((s * L * rr * math.cos(r2), s * L * rr * math.sin(r2)) if rr < 1 else tip)
        mid = math.radians((a + an) / 2)
        depth = 0.3 if k == 2 else 0.48                    # 缺口浅，叶基处更浅
        pts.append((s * depth * math.cos(mid), s * depth * math.sin(mid)))
    c.path(poly([T(*p) for p in pts], closed=True), sw=sw, fill="#fff")
    for a, L in lobes:
        ra = math.radians(a)
        p0, p1 = T(0, 0), T(s * L * 0.9 * math.cos(ra), s * L * 0.9 * math.sin(ra))
        c.path(f"M{f2(p0[0])},{f2(p0[1])} L{f2(p1[0])},{f2(p1[1])}", sw=HAIR)
    st = [T(0, 0), T(s * 0.05, s * 0.25), T(-s * 0.02, s * 0.45)]
    c.path(smooth(st), sw=THIN)


def falling_leaf(w: float, h: float, seed: int = 39) -> str:
    """落叶知秋：「见一叶落而知岁之将暮」——一片梧桐叶打着旋落下，虚线是它飘过的路。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    for _ in range(3):
        y, x0 = h * rng.uniform(0.15, 0.7), w * rng.uniform(0.05, 0.5)
        streak(c, x0, y, x0 + w * rng.uniform(0.15, 0.25), y + rng.uniform(1, 5), thick=rng.uniform(0.6, 0.9))
    s = min(h * 0.3, w * 0.11)
    lx, ly = w * 0.66, h * 0.52
    path = [(w * 0.18, -4), (w * 0.3, h * 0.2), (w * 0.44, h * 0.14), (w * 0.52, h * 0.34), (lx - s * 0.6, ly - s * 0.1)]
    c.path(smooth(path), sw=HAIR, extra=' stroke-dasharray="2 3"')
    plane_leaf(c, lx, ly, s, math.radians(28))
    plane_leaf(c, w * 0.86, h * 0.84, s * 0.45, math.radians(-50), sw=HAIR * 1.4)
    return c.svg()


# ---------------------------------------------------------------- 墨勾山脊

def brush_stroke(c: Canvas, pts, th: float, rng: random.Random, fill: str = "#000") -> None:
    """两头尖、中间粗的毛笔笔触：沿中心线向两侧各偏一半粗细，合成填充形。"""
    n = len(pts)
    up, dn = [], []
    for i, (x, y) in enumerate(pts):
        t = i / (n - 1)
        k = th * math.sin(math.pi * t) ** 0.55 * (0.75 + 0.25 * math.sin(t * 9 + x * 0.05))
        (xa, ya), (xb, yb) = pts[max(i - 1, 0)], pts[min(i + 1, n - 1)]
        L = math.hypot(xb - xa, yb - ya) or 1
        nx, ny = -(yb - ya) / L, (xb - xa) / L
        up.append((x + nx * k * 0.35, y + ny * k * 0.35))
        dn.append((x - nx * k * 0.65, y - ny * k * 0.65))
    c.path(smooth(up) + " L" + smooth(dn[::-1])[1:] + "Z", sw=0, fill=fill)


def ink_ridges(w: float, h: float, seed: int = 27, rows: int = 5) -> str:
    """山下的云与山脊：「深一道浅一道，像谁用墨在宣纸上随意勾了几笔，剩下的都交给了留白」。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    for r in range(rows):
        z = r / (rows - 1)                      # 0 远 → 1 近
        base = h * (0.28 + 0.62 * z)
        amp = h * (0.08 + 0.2 * z)
        peaks = [(rng.uniform(-0.1, 1.1) * w, rng.uniform(0.35, 1.0) * amp, rng.uniform(0.06, 0.16) * w)
                 for _ in range(3 + r)]
        # 每道山脊断成两三笔，笔间留出飞白
        x = w * rng.uniform(-0.05, 0.25) if r < rows - 1 else -8
        while x < w:
            seg = w * rng.uniform(0.25, 0.55) * (0.7 + 0.5 * z)
            xs = list(frange(x, min(x + seg, w + 8), 3))
            if len(xs) > 4:
                pts = [(px, base - sum(a * math.exp(-((px - cx) / s) ** 2) for cx, a, s in peaks)
                        + 0.8 * math.sin(px / 11 + r)) for px in xs]
                brush_stroke(c, pts, 0.7 + 3.2 * z ** 1.3, rng, fill="#000" if z > 0.3 else "#555")
            x += seg + w * rng.uniform(0.03, 0.12)
    return c.svg()


# ---------------------------------------------------------------- 风中垂柳

def willow_leaf(c: Canvas, x: float, y: float, L: float, ang: float, wid: float = 0.2) -> None:
    """柳叶：两道弧合成的细长叶片。"""
    dx, dy = math.cos(ang), math.sin(ang)
    nx, ny = -dy, dx
    x1, y1 = x + dx * L, y + dy * L
    mx, my = x + dx * L * 0.42, y + dy * L * 0.42
    k = L * wid
    c.path(f"M{f2(x)},{f2(y)} Q{f2(mx + nx * k)},{f2(my + ny * k)} {f2(x1)},{f2(y1)} "
           f"Q{f2(mx - nx * k)},{f2(my - ny * k)} {f2(x)},{f2(y)}Z", sw=HAIR, fill="#fff")


def willow(w: float, h: float, seed: int = 26, wind: float = 0.55) -> str:
    """风乎舞雩：画外的柳树只露出左上角一段枝干，柳条自上沿垂下，被风吹向右边；右侧几片飞叶、几道风线。"""
    rng = random.Random(seed)
    c = Canvas(w, h)
    for _ in range(3):
        y = h * rng.uniform(0.35, 0.85)
        x0 = w * rng.uniform(0.62, 0.8)
        streak(c, x0, y + 2, x0 + w * rng.uniform(0.1, 0.16), y - 3, thick=rng.uniform(0.8, 1.1))
    # 左上角的一段枝干，弯出上沿
    br = [(-6, h * 0.34), (w * 0.05, h * 0.18), (w * 0.12, h * 0.07), (w * 0.2, -4)]
    c.path(smooth(br), sw=MAIN * 1.8)
    c.path(smooth([(w * 0.05, h * 0.18), (w * 0.09, h * 0.2), (w * 0.14, h * 0.17)]), sw=MAIN)
    # 柳条：根部沿上沿和枝干分布，左密右疏；越往下被风吹得越偏
    roots = [(w * 0.03 + w * 0.6 * rng.random() ** 1.4, -2.0) for _ in range(20)]
    roots += [(w * rng.uniform(0.02, 0.13), h * rng.uniform(0.1, 0.25)) for _ in range(3)]
    roots.sort()
    for x, y in roots:
        L = (h - y) * rng.uniform(0.6, 1.08)
        sway = wind * rng.uniform(0.7, 1.15)
        ph = rng.uniform(0, 6)
        tw = [(x + sway * L * t ** 2 + 1.2 * math.sin(t * 5 + ph), y + L * t * (1 - 0.22 * sway * t))
              for t in (i / 29 for i in range(30))]
        c.path(smooth(tw), sw=HAIR * 1.2)
        # 柳叶：约每 5 pt 一片，左右交替，顺着柳条斜向下
        acc, side = 0.0, 1
        for (ax, ay), (bx, by) in zip(tw[3:], tw[4:]):
            acc += math.hypot(bx - ax, by - ay)
            if acc < 5:
                continue
            acc = 0.0
            side = -side
            ang = math.atan2(by - ay, bx - ax)
            willow_leaf(c, ax, ay, rng.uniform(5, 6.8), ang + side * rng.uniform(0.3, 0.55), wid=0.24)
    # 被风带走的叶子
    for _ in range(7):
        willow_leaf(c, w * rng.uniform(0.66, 0.97), h * rng.uniform(0.2, 0.9), rng.uniform(5, 6.5),
                    rng.uniform(-1.2, 0.4), wid=0.26)
    return c.svg()


PATTERNS = {
    "cloudsea": cloudsea,
    "seawaves": seawaves,
    "ginkgo": ginkgo,
    "track": track,
    "tower": tower,
    "mountains": mountains,
    "moon_bamboo": moon_bamboo,
    "moon_lake": moon_lake,
    "oval_track": oval_track,
    "paper_doodle": paper_doodle,
    "pingpong": pingpong,
    "feather": feather,
    "glass_bird": glass_bird,
    "origami_tiger": origami_tiger,
    "gulou": gulou,
    "old_tree": old_tree,
    "window_view": window_view,
    "startline": startline,
    "shuttle": shuttle,
    "book_leaf": book_leaf,
    "letter": letter,
    "willow": willow,
    "ink_ridges": ink_ridges,
    "lighthouse": lighthouse,
    "pool": pool,
    "cat_sakura": cat_sakura,
    "desk_lamp": desk_lamp,
    "scroll": scroll,
    "chain_bridge": chain_bridge,
    "sky_birds": sky_birds,
    "jiangnan_moon": jiangnan_moon,
    "bench": bench,
    "falling_leaf": falling_leaf,
    "brick_ivy": brick_ivy,
}


def make(kind: str, w: float, h: float, **kw) -> str:
    return PATTERNS[kind](w, h, **kw)


if __name__ == "__main__":
    import sys
    out = HERE / "images" / "art"
    out.mkdir(parents=True, exist_ok=True)
    for kind in (sys.argv[1:] or PATTERNS):
        (out / f"preview-{kind}.svg").write_text(make(kind, 441, 260), encoding="utf-8")
        print("wrote", kind)
