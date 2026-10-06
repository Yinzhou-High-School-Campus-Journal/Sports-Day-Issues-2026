#!/usr/bin/env python3
"""校运会特刊第二期《骋风逐曜》 — cover and title page (扉页), A4, black and white.

Issue 1 looked at a sunrise over a sea of clouds; issue 2 turns to the campus
at night, after 《有风吹过》 ("回忆的风掠过桥与梧桐道……蓝青河中央的树上总能见到
夜鹭的羽影") and 《游天妃湖赏月有感》 ("玉轮……徘徊于疏霭之间……芦苇飘萧……清辉洒湖"):
a moon in thin cloud over the 蓝青河, the footbridge, the finned hall and the
clock tower on the far bank, a night heron on a snag, reeds in the wind. Four
stepping stones carry the four sections in reading order into the moonlight.

  mode=cover  full bleed, no page margins (bleed=3 adds 3 mm per side)
  mode=title  title page: the same scene, simplified, in a round vignette

All text is at least 10.5 pt; everything is pure black line work. Units: mm.
"""
import os, sys, html, math, random

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.expanduser('~/Library/Fonts')
OPT = dict(a.split('=', 1) for a in sys.argv[1:] if '=' in a)
MODE = OPT.get('mode', 'cover')
if MODE == 'title':
    for k, v in dict(mx='70', my='106', mr='16', sx='140', sy='242', stop='192', hs='1.15').items():
        OPT.setdefault(k, v)
LOCAL = OPT.get('fontdir', os.path.join(HERE, 'fonts'))
def opt(k, d):
    v = OPT.get(k)
    return type(d)(v) if v is not None else d

NAME = '骋风逐曜'                                       # this issue's name
EVENT = '鄞州中学第四十四届暨鄞州蓝青高级中学第二十九届运动会校刊'
ISSUE, YEAR, CREDIT = '第二期', '2026', '媒体部主编'
SECTIONS = ['红砖絮语', '赛道秋声', '青衿问道', '思接千载']   # printed section names, reading order
QUOTE = ['时流向前，', '万物缤纷争度，', '唯风记得来时路。']      # 《有风吹过》
CITE = '——《有风吹过》'

PW, PH = 210.0, 297.0
BLEED = opt('bleed', 0.0) if MODE == 'cover' else 0.0
SIMPLE = MODE == 'title'
SWM = opt('swm', 1.0 if MODE == 'cover' else 1.5)
XL, XR = -BLEED - 1.0, PW + BLEED + 1.0
YBOT = PH + BLEED + 1.0
rng = random.Random(opt('seed', 7))

svg, divs, defs = [], [], []

def esc(s):
    return html.escape(s, quote=False)

def P(x, y):
    return f'{x:.2f},{y:.2f}'

def sw(w):
    return f'{w * SWM:.3f}'

def line(x1, y1, x2, y2, w=0.3, cap='butt'):
    svg.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#000" stroke-width="{sw(w)}" stroke-linecap="{cap}"/>')

def rect(x, y, w, h, s=0.3, fill='#fff'):
    svg.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}" stroke="#000" stroke-width="{sw(s)}"/>')

def poly(pts, fill='#000', stroke='none', s=0.0):
    svg.append(f'<polygon points="{" ".join(P(*q) for q in pts)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw(s)}" stroke-linejoin="round"/>')

def taper(pts, w0, w1, fill='#000'):
    """Filled stroke along a polyline, width going from w0 to w1."""
    left, right = [], []
    n = len(pts)
    for i, (x, y) in enumerate(pts):
        a = pts[max(i - 1, 0)]; b = pts[min(i + 1, n - 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / L, tx / L
        w = (w0 + (w1 - w0) * i / (n - 1)) * SWM / 2
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    poly(left + right[::-1], fill=fill)

def quad(p0, p1, p2, n=24):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]) for t in (i / n for i in range(n + 1))]

# ------------------------------------------------------------------ layout constants (trim coordinates)
BANK = opt('bank', 150.0)            # far bank / water line
MOON = (opt('mx', 60.0), opt('my', 70.0), opt('mr', 27.0))
TOWER = dict(x=opt('tx', 116.0), top=opt('ttop', 96.0), wf=7.6, ws=2.7)

WISPS = [(12, 76, 100, 69.5, -1.6, 0.85), (28, 82.5, 88, 80.2, -0.8, 0.46), (36, 58.5, 96, 54.0, -1.2, 0.5)]
FLYERS = [(44.0, 86.0, 1.55, 0.0), (14.0, 44.0, 0.85, 1.2)]
LEAVES = [(104.0, 104.0, 5.4, -30.0), (96.0, 124.0, 4.2, 35.0), (14.0, 118.0, 4.6, -60.0)]
STONES = [(40, 276, 22, 6.4, 2.4, 16.0), (73, 250, 17.5, 5.0, 1.9, 14.0),
          (55, 229, 14.5, 4.1, 1.5, 12.5), (67, 212, 12.0, 3.3, 1.2, 11.0)]

if MODE == 'title':
    WISPS = [(40, 108.5, 104, 103.5, -1.2, 0.8), (52, 114.0, 92, 112.4, -0.6, 0.45)]
    FLYERS = [(58.0, 112.5, 1.2, 0.0)]
    STONES = [(50, 240, 15, 4.4, 1.7, 0), (70, 220, 11.5, 3.4, 1.3, 0)]

# ------------------------------------------------------------------ sky
def moon():
    cx, cy, r = MOON
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#fff" stroke="#000" stroke-width="{sw(0.6)}"/>')

def wisp(x0, y0, x1, y1, bend, wmax):
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    cx, cy = mx - dy / L * bend, my + dx / L * bend
    pts = quad((x0, y0), (cx, cy), (x1, y1), 40)
    top, bot = [], []
    for i, (x, y) in enumerate(pts):
        u = i / (len(pts) - 1)
        a = pts[max(i - 1, 0)]; b = pts[min(i + 1, len(pts) - 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]; tl = math.hypot(tx, ty) or 1
        px, py = -ty / tl, tx / tl
        w = wmax * math.sin(math.pi * u) ** 0.9 * (1 - 0.35 * u) * SWM
        top.append((x + px * w / 2, y + py * w / 2)); bot.append((x - px * w / 2, y - py * w / 2))
    poly(top + bot[::-1])

def ginkgo(cx, cy, R, rot_deg, veins=13):
    rot = math.radians(rot_deg)
    def T(x, y):
        return cx + x * math.cos(rot) + y * math.sin(rot), cy - (-x * math.sin(rot) + y * math.cos(rot))
    half = math.radians(68)
    def rim(t):
        th = math.pi / 2 + half - 2 * half * t
        r = R * (1 - 0.2 * max(0.0, 1 - abs(t - 0.5) / 0.09) + 0.025 * math.sin(t * math.pi * 7))
        return r * math.cos(th), r * math.sin(th)
    pts = []
    x0, y0 = rim(0)
    for i in range(1, 9):
        f = i / 9
        pts.append((x0 * f - 0.08 * R * math.sin(f * math.pi), y0 * f * (0.92 + 0.08 * f)))
    pts += [rim(i / 60) for i in range(61)]
    x1, y1 = rim(1)
    for i in range(8, 0, -1):
        f = i / 9
        pts.append((x1 * f + 0.08 * R * math.sin(f * math.pi), y1 * f * (0.92 + 0.08 * f)))
    poly([T(0, 0)] + [T(*q) for q in pts], fill='#fff', stroke='#000', s=0.3)
    for k in range(1, veins):
        t = k / veins
        ex, ey = rim(t)
        a0 = 0.12 + 0.1 * abs(t - 0.5)
        sx, sy = T(ex * a0, ey * a0); tx, ty = T(ex * 0.93, ey * 0.93)
        line(sx, sy, tx, ty, 0.12)
    s0 = T(0, 0); s2 = T(0.02 * R, -0.46 * R)
    taper(quad(s0, T(0.06 * R, -0.22 * R), s2, 10), 0.34, 0.2)

# ------------------------------------------------------------------ far bank: campus (after the Wikimedia photos)
def teaching_block(x0, x1, top, base, nrows=3, pitch=1.75):
    rect(x0, top, x1 - x0, base - top, 0.3)
    line(x0, top + 1.1, x1, top + 1.1, 0.18)
    for r in range(nrows):
        y0 = top + 2.4 + r * 3.1
        if y0 + 1.9 > base - 0.5:
            break
        x = x0 + 1.2
        while x < x1 - 1.0:
            line(x, y0, x, y0 + 1.9, 0.3)
            x += pitch

def finned_hall(x0, x1, top, base, pitch=0.95):
    rect(x0, top, x1 - x0, base - top, 0.3)
    line(x0, top + 1.6, x1, top + 1.6, 0.25)
    for i in range(5):                                         # serrated roof, as in the photo
        a = x0 + 2 + i * (x1 - x0 - 4) / 5
        poly([(a, top), (a + 1.6, top - 1.2), (a + 3.2, top)], fill='#fff', stroke='#000', s=0.22)
    x = x0 + 0.9
    while x < x1 - 0.6:
        line(x, top + 3.0, x, base, 0.2)
        x += pitch

def clock_tower(x0, top, base, wf, ws):
    xs = x0 + wf
    poly([(xs, top + 0.7), (xs + ws, top + 0.7), (xs + ws, base), (xs, base)], fill='#fff', stroke='#000', s=0.3)
    y = top + 1.3
    while y < base:
        line(xs, y, xs + ws, y, 0.15)
        y += 0.62
    svg.append(f'<rect x="{xs + ws * 0.24:.2f}" y="{top + wf * 0.45:.2f}" width="{ws * 0.52:.2f}" height="{wf * 0.95:.2f}" fill="#000"/>')
    n0, n1 = x0 + wf * 0.44, x0 + wf * 0.53
    poly([(x0, base), (x0, top), (n0, top), (n0, top + 0.8), (n1, top + 0.8), (n1, top), (xs, top), (xs, base)],
         fill='#fff', stroke='#000', s=0.32)
    e = wf * 0.5
    ex, ey = x0 + (wf - e) / 2, top + wf * 0.3
    rect(ex, ey, e, e, 0.24)
    svg.append(f'<circle cx="{ex + e / 2:.2f}" cy="{ey + e / 2:.2f}" r="{e * 0.34:.2f}" fill="none" stroke="#000" stroke-width="{sw(0.22)}"/>')
    y = ey + e + 2.4
    hs = 0.55
    while y < base - 1.5:
        for fx in (0.2, 0.31, 0.69, 0.8):
            svg.append(f'<rect x="{x0 + wf * fx - hs / 2:.2f}" y="{y:.2f}" width="{hs}" height="{hs}" fill="#000"/>')
        y += 2.5

def far_bank():
    base = BANK + 0.2
    teaching_block(XL, 62.0, 136.0, base)
    finned_hall(62.0, 104.0, 128.5, base)
    teaching_block(104.0, TOWER['x'] + 0.5, 140.5, base, nrows=2)
    clock_tower(TOWER['x'], TOWER['top'], base, TOWER['wf'], TOWER['ws'])
    teaching_block(TOWER['x'] + TOWER['wf'] + TOWER['ws'] - 0.3, 152.0, 141.5, base, nrows=2)
    line(XL, BANK, XR, BANK, 0.45)

def bridge(ax, ay, bx, by, arch=5.0, h0=4.2, h1=1.5):
    """The footbridge (after the south-east campus photo): a long arched deck with a
    solid parapet, crossing the river diagonally from the near left to the far bank."""
    cx, cy = (ax + bx) / 2, min(ay, by) - arch
    cen = quad((ax, ay), (cx, cy), (bx, by), 60)
    top, bot, mid = [], [], []
    for i, (x, y) in enumerate(cen):
        u = i / (len(cen) - 1)
        h = h0 + (h1 - h0) * u
        top.append((x, y - h * 0.55)); bot.append((x, y + h * 0.45)); mid.append((x, y + h * 0.05))
    # piers down to the water, then the deck over them
    for u in (0.12, 0.34, 0.56, 0.78):
        i = int(u * (len(cen) - 1))
        x, y = bot[i]
        ph = 9.5 * (1 - 0.75 * u)
        pw = 1.8 * (1 - 0.55 * u)
        rect(x - pw / 2, y, pw, ph, 0.26)
        reflection_band(x - pw / 2, x + pw / 2, y + ph + 0.6, y + ph + ph * 0.8, 0.8)
    poly(top + bot[::-1], fill='#fff', stroke='#000', s=0.36)
    svg.append(f'<polyline points="{" ".join(P(*q) for q in mid)}" fill="none" stroke="#000" stroke-width="{sw(0.2)}"/>')

# ------------------------------------------------------------------ water
def moon_path_halfwidth(y):
    return 3.5 + (y - BANK) * opt('pathspread', 0.13)

def water(avoid):
    """Engraved ripples: dashed rows, denser toward the far bank; the moon's
    path stays open except for short glints; `avoid` = [(x0, x1, y0, y1)]."""
    rows = []
    y = BANK + 1.2
    while y < YBOT:
        rows.append(y)
        y += max(opt('wminstep', 1.05 if not SIMPLE else 2.2), (y - BANK + 6) * opt('wstep', 0.05 if not SIMPLE else 0.1))
    mx = MOON[0]
    for y in rows:
        d = (y - BANK) / (YBOT - BANK)                 # 0 far .. 1 near
        w = 0.2 + 0.28 * d
        half = moon_path_halfwidth(y)
        x = XL + rng.uniform(-6, 0)
        segs = []
        while x < XR:
            L = rng.uniform(3.0, 16.0) * (0.45 + 1.3 * d)
            g = rng.uniform(1.2, 6.0) * (0.45 + 1.1 * d)
            segs.append((x, min(x + L, XR)))
            x += L + g
        for (a, b) in segs:
            # carve out the moon path and anything listed in `avoid`
            pieces = [(a, b)]
            cuts = [(mx - half, mx + half)] + [(x0, x1) for (x0, x1, y0, y1) in avoid if y0 <= y <= y1]
            for (c0, c1) in cuts:
                nxt = []
                for (p0, p1) in pieces:
                    if p1 <= c0 or p0 >= c1:
                        nxt.append((p0, p1))
                    else:
                        if p0 < c0: nxt.append((p0, c0))
                        if p1 > c1: nxt.append((c1, p1))
                pieces = nxt
            for (p0, p1) in pieces:
                if p1 - p0 > 0.8:
                    wy = y + 0.25 * math.sin(p0 * 0.7 + y)
                    line(p0, wy, p1, wy, w, 'round')
        # glints inside the moon's path
        if rng.random() < 0.85:
            for _ in range(rng.randint(1, 3)):
                gx = mx + rng.uniform(-half * 0.8, half * 0.8)
                gl = rng.uniform(0.8, 2.6) * (0.5 + d)
                line(gx - gl / 2, y, gx + gl / 2, y, w * 1.4, 'round')
    return rows

def reflection_band(x0, x1, y0, y1, density=0.55):
    """Short stacked dashes: the broken reflection of something on the bank."""
    y = y0
    while y < y1:
        x = x0 + rng.uniform(0, 1.2)
        while x < x1:
            L = rng.uniform(1.0, 3.2)
            if rng.random() < density:
                line(x, y, min(x + L, x1), y, 0.34, 'round')
            x += L + rng.uniform(0.4, 1.6)
        y += rng.uniform(0.9, 1.4)

# ------------------------------------------------------------------ foreground
def stone(cx, cy, rx, ry, t, label=None, size=12.0, seed=0):
    rs = random.Random(seed + 11)
    ph = [rs.uniform(0, 6.3) for _ in range(3)]
    def outline(dy, grow=0.0):
        pts = []
        for i in range(72):
            a = 2 * math.pi * i / 72
            r = 1 + 0.07 * math.sin(2 * a + ph[0]) + 0.05 * math.sin(3 * a + ph[1]) + 0.03 * math.sin(5 * a + ph[2])
            pts.append((cx + (rx + grow) * r * math.cos(a), cy + dy + (ry + grow * 0.3) * r * math.sin(a)))
        return pts
    for (g, w) in [(3.8, 0.26), (7.6, 0.17)]:          # ripple rings, the near half only
        ring = [q for q in outline(t * 0.8, g) if q[1] >= cy + t * 0.8]
        ring.sort(key=lambda q: q[0])
        svg.append(f'<polyline points="{" ".join(P(*q) for q in ring)}" fill="none" stroke="#000" stroke-width="{sw(w)}"/>')
    side = outline(t)
    poly(side, fill='#fff', stroke='#000', s=0.4)
    top = outline(0)
    poly(top, fill='#fff', stroke='#000', s=0.45)
    # a couple of weathering marks on the rim
    for k in range(2):
        a = rs.uniform(0.15, 0.85) * math.pi
        x0 = cx + rx * 0.95 * math.cos(a); y0 = cy + ry * 0.95 * math.sin(a)
        line(x0, y0 + 0.4, x0 + rs.uniform(-1.2, 1.2), y0 + t * 0.8, 0.22, 'round')
    if label and not SIMPLE:
        divs.append(f'<div class="abs c stonelabel" style="left:{cx:.2f}mm;top:{cy - 0.2:.2f}mm;font-size:{size}pt;">{esc(label)}</div>')

HERON = ('M0,7.2 L7.0,4.9 Q8.0,3.3 11.5,2.7 Q13.4,2.5 14.4,3.4 Q16.2,4.6 20.5,5.4 '
         'Q26.0,6.6 29.6,10.2 L30.8,12.1 L27.8,13.1 Q22.6,15.9 16.0,16.4 Q12.0,16.2 10.2,13.6 '
         'Q8.8,11.4 8.4,9.9 Q8.0,8.9 7.2,8.2 Z')

def heron(x, y, s=1.2):
    """Black-crowned night heron (夜鹭) perched, hunched, facing left; (x, y) = feet.
    Heavy dagger bill, flat crown, no visible neck, white nape plumes down the back."""
    ox, oy = x - 17.6 * s, y - 20.0 * s
    k = SWM / s
    svg.append(f'<g transform="translate({ox:.2f},{oy:.2f}) scale({s})">'
               f'<path d="{HERON}" fill="#000"/>'
               f'<path d="M14.2,3.9 Q19.8,4.6 24.6,8.4" fill="none" stroke="#fff" stroke-width="{0.3 * k:.3f}" stroke-linecap="round"/>'
               f'<path d="M14.6,4.4 Q19.2,5.6 22.4,9.0" fill="none" stroke="#fff" stroke-width="{0.22 * k:.3f}" stroke-linecap="round"/>'
               f'<path d="M14.6,10.2 Q22.0,9.9 28.6,11.9" fill="none" stroke="#fff" stroke-width="{0.3 * k:.3f}" stroke-linecap="round"/>'
               f'<path d="M16.2,16.3 L15.8,20.0 M19.4,16.1 L20.0,20.0 M15.8,20.0 L13.9,20.6 M20.0,20.0 L18.1,20.6" '
               f'fill="none" stroke="#000" stroke-width="{0.72 * k:.3f}" stroke-linecap="round"/>'
               f'<circle cx="10.9" cy="5.0" r="0.62" fill="#fff"/></g>')

def flying_heron(x, y, s=1.0, flap=0.0):
    """Night heron in flight, facing left: broad rounded wings, neck tucked, legs trailing."""
    f = flap
    svg.append(f'<g transform="translate({x:.2f},{y:.2f}) scale({s})">'
               # far wing (raised)
               f'<path d="M5.6,2.4 Q6.8,{-2.4 - f:.2f} 10.2,{-3.6 - f:.2f} Q12.2,{-4.0 - f:.2f} 11.6,{-2.4 - f:.2f} '
               f'Q10.4,0.4 8.6,2.8 Z" fill="#000"/>'
               # body and head, bill forward
               f'<path d="M-2.4,3.1 L0.9,2.5 Q1.7,1.3 3.1,1.5 Q5.8,1.7 9.0,2.5 Q11.8,3.2 12.8,4.1 '
               f'Q9.6,5.1 6.2,5.0 Q3.0,4.9 1.2,3.5 Z" fill="#000"/>'
               # near wing (broad, rounded tip, trailing edge back to the body)
               f'<path d="M3.8,2.8 Q4.6,{-3.2 - f * 1.4:.2f} 9.4,{-6.4 - f * 1.6:.2f} Q12.4,{-7.4 - f * 1.6:.2f} 12.6,{-5.4 - f * 1.4:.2f} '
               f'Q12.0,-1.6 9.4,1.8 Q8.4,3.2 7.2,3.4 Z" fill="#000"/>'
               f'<path d="M12.2,4.1 L17.0,5.0 M12.0,4.4 L16.6,5.6" fill="none" stroke="#000" stroke-width="{0.42 * SWM / s:.3f}" stroke-linecap="round"/>'
               f'<circle cx="1.9" cy="2.4" r="0.32" fill="#fff"/>'
               f'</g>')

def snag(bx, by, top):
    """A dead tree standing in the river (夜鹭 roost), leaning, with a broken top."""
    trunk = quad((bx, by), (bx + 4.0, (by + top) / 2 + 6), (bx - 1.6, top), 30)
    taper(trunk, 5.2, 1.9)
    tx, ty = trunk[-1]
    poly([(tx - 1.2, ty + 0.6), (tx - 0.4, ty - 2.6), (tx + 0.3, ty - 0.8), (tx + 0.9, ty - 3.4), (tx + 1.3, ty + 0.8)])
    hl = [(x - 0.9, y) for (x, y) in trunk[4:26]]                    # a pale streak along the bark
    svg.append(f'<polyline points="{" ".join(P(*q) for q in hl)}" fill="none" stroke="#fff" stroke-width="{sw(0.28)}"/>')
    bx0, by0 = trunk[20]
    br = quad((bx0, by0), (bx0 - 9, by0 - 4.5), (bx0 - 20, by0 - 1.8), 18)
    taper(br, 2.1, 0.6)
    ex, ey = br[-1]
    taper(quad((ex + 2, ey + 0.2), (ex - 1.5, ey - 3.8), (ex - 1.0, ey - 7.5), 8), 0.7, 0.18)
    sx, sy = trunk[10]
    taper(quad((sx + 1.2, sy), (sx + 6, sy - 3.5), (sx + 10.5, sy - 8.5), 10), 1.5, 0.35)
    kx, ky = trunk[25]
    taper(quad((kx + 0.4, ky), (kx + 3.5, ky - 2.5), (kx + 5.5, ky - 6.0), 8), 0.9, 0.22)
    return br[len(br) * 3 // 5]

def reeds(x0, x1, base, rs):
    for i in range(opt('nreeds', 11)):
        bx = rs.uniform(x0, x1)
        h = rs.uniform(50, 96)
        lean = rs.uniform(-24, -9)                       # bent by the wind, toward the moon
        p0 = (bx, base); p2 = (bx + lean, base - h); p1 = (bx + lean * 0.1, base - h * 0.55)
        stem = quad(p0, p1, p2, 32)
        taper(stem, 0.95, 0.3)
        # plume: fine drooping strokes streaming away from the upper stem
        for j in range(10):
            sx, sy = stem[-1 - rs.randint(0, 5)]
            L = rs.uniform(5.0, 10.5)
            ex, ey = sx - L * rs.uniform(0.7, 1.0), sy + L * rs.uniform(0.25, 0.55)
            cx, cy = (sx + ex) / 2 - 0.5, (sy + ey) / 2 - L * 0.22
            taper(quad((sx, sy), (cx, cy), (ex, ey), 10), 0.36, 0.04)
        # a long blade leaf curling off the stem
        k = rs.uniform(0.3, 0.6)
        lx, ly = stem[int(32 * k)]
        d = rs.choice((-1, 1))
        taper(quad((lx, ly), (lx + d * rs.uniform(5, 9), ly - rs.uniform(9, 14)),
                   (lx + d * rs.uniform(10, 18) - 6, ly - rs.uniform(14, 24)), 16), 1.0, 0.08)

# ------------------------------------------------------------------ compose the scene
def fin_reflection(x0, x1, y0, y1):
    """Broken vertical ticks: the finned hall mirrored in the water."""
    y = y0
    while y < y1:
        x = x0 + 0.5
        while x < x1:
            if rng.random() < 0.55:
                line(x, y, x, y + rng.uniform(0.5, 1.1), 0.2)
            x += 1.9
        y += rng.uniform(1.1, 1.7)

def scene():
    moon()
    for (x0, y0, x1, y1, b, w) in WISPS:
        wisp(x0, y0, x1, y1, b, w)
    for (x, y, sc, fl) in FLYERS:
        flying_heron(x, y, sc, fl)
    far_bank()
    stones = STONES
    avoid = [(cx - rx * 1.15 - 1, cx + rx * 1.15 + 1, cy - ry * 1.2 - 0.8, cy + t + ry * 1.2 + 1)
             for (cx, cy, rx, ry, t, _) in stones]
    tx0 = TOWER['x']; tx1 = tx0 + TOWER['wf'] + TOWER['ws']
    avoid.append((tx0 - 0.5, tx1 + 0.5, BANK, BANK + 34))
    avoid.append((62.0, 104.0, BANK, BANK + 18))
    water(avoid)
    reflection_band(tx0, tx1, BANK + 1.4, BANK + 32)
    if not SIMPLE:
        fin_reflection(62.0, 104.0, BANK + 1.2, BANK + 17)
    bridge(XL, BANK + 24.0, 97.0, BANK + 1.2)
    if not SIMPLE:
        for (x, y, R, a) in LEAVES:
            ginkgo(x, y, R, a)
    for (i, (cx, cy, rx, ry, t, size)) in enumerate(stones):
        stone(cx, cy, rx, ry, t, SECTIONS[i], size, seed=i)
    perch = snag(opt('sx', 156.0), opt('sy', 262.0), opt('stop', 196.0))
    reflection_band(151.5, 160.5, 262.5, 276, 0.6)
    heron(perch[0] + 1.2, perch[1] - 0.4, opt('hs', 1.25))
    if not SIMPLE:
        reeds(164.0, 214.0, YBOT + 2, random.Random(opt('rseed', 4)))

# ------------------------------------------------------------------ type
def mast_vertical(cx, top, size, gap):
    for i, ch in enumerate(NAME):
        divs.append(f'<div class="abs mast" style="left:{cx - size / 2:.2f}mm;top:{top + i * (size + gap):.2f}mm;'
                    f'width:{size}mm;height:{size}mm;font-size:{size}mm;line-height:{size}mm;">{ch}</div>')

def mast_horizontal(cx, top, size, gap):
    w = 4 * size + 3 * gap
    for i, ch in enumerate(NAME):
        divs.append(f'<div class="abs mast" style="left:{cx - w / 2 + i * (size + gap):.2f}mm;top:{top:.2f}mm;'
                    f'width:{size}mm;height:{size}mm;font-size:{size}mm;line-height:{size}mm;">{ch}</div>')

if MODE == 'cover':
    scene()
    divs.append(f'<div class="abs c top" style="left:{PW / 2}mm;top:{opt("topy", 13.2)}mm;">{EVENT}</div>')
    MS = opt('ms', 30.0)
    mast_vertical(opt('mcx', 178.0), opt('mtop', 22.0), MS, opt('mg', 2.2))
    divs.append(f'<div class="abs vt issue" style="left:{opt("icx", 153.5):.2f}mm;top:{opt("itop", 23.0)}mm;">{ISSUE}<span class="yr">{YEAR}</span></div>')
    # inscription: quote columns, source, then the editor's signature and seal
    qx, qtop, step = opt('qx', 140.0), opt('qtop', 25.0), opt('qstep', 7.6)
    for i, col in enumerate(QUOTE):
        divs.append(f'<div class="abs vt quote" style="left:{qx - i * step:.2f}mm;top:{qtop:.2f}mm;">{esc(col)}</div>')
    cx_cite = qx - len(QUOTE) * step
    divs.append(f'<div class="abs vt cite" style="left:{cx_cite:.2f}mm;top:{qtop + 9:.2f}mm;">{esc(CITE)}</div>')
    cx_sig = cx_cite - step
    divs.append(f'<div class="abs vt sig" style="left:{cx_sig:.2f}mm;top:{qtop + 16:.2f}mm;">{CREDIT}</div>')
    seal_w, seal_h = 7.4, 14.6
    seal_y = qtop + 16 + 5 * 5.62 + 2.6
    svg.append(f'<rect x="{cx_sig - seal_w / 2:.2f}" y="{seal_y:.2f}" width="{seal_w}" height="{seal_h}" fill="#000"/>')
    divs.append(f'<div class="abs vt seal" style="left:{cx_sig:.2f}mm;top:{seal_y + 1.4:.2f}mm;">鄞中</div>')
    page_w, page_h = PW + 2 * BLEED, PH + 2 * BLEED
    view = f'{-BLEED} {-BLEED} {page_w} {page_h}'
    body_svg = '\n'.join(svg)
    title = f'{NAME} {ISSUE} 封面'
else:
    XL, XR, YBOT = 0.0, PW, PH
    scene()
    VC, VR = (opt('vcx', 88.0), opt('vcy', 172.0)), opt('vr', 90.0)
    PC, PR = (opt('pcx', 84.0), opt('pcy', 152.0)), opt('pr', 56.0)
    s = PR / VR
    defs.append(f'<clipPath id="vig" clipPathUnits="userSpaceOnUse"><circle cx="{VC[0]}" cy="{VC[1]}" r="{VR}"/></clipPath>')
    body_svg = (f'<g transform="translate({PC[0] - VC[0] * s:.3f},{PC[1] - VC[1] * s:.3f}) scale({s:.5f})">'
                f'<g clip-path="url(#vig)">{chr(10).join(svg)}</g></g>'
                f'<circle cx="{PC[0]}" cy="{PC[1]}" r="{PR}" fill="none" stroke="#000" stroke-width="0.5"/>'
                f'<circle cx="{PC[0]}" cy="{PC[1]}" r="{PR + 2.2:.2f}" fill="none" stroke="#000" stroke-width="0.2"/>')
    divs = []
    divs.append(f'<div class="abs c top" style="left:{PW / 2}mm;top:{opt("ttopy", 64.0)}mm;">{EVENT}</div>')
    mcx = opt('tmcx', 164.0)
    TMS = opt('tms', 24.0)
    mast_vertical(mcx, opt('tmtop', 95.0), TMS, opt('tmg', 2.0))
    divs.append(f'<div class="abs vt issue tv" style="left:{mcx:.2f}mm;top:{opt("titop", 204.0)}mm;">{ISSUE}<span class="yr">{YEAR}</span></div>')
    divs.append(f'<div class="abs c credit" style="left:{PW / 2}mm;top:{opt("tcredy", 262.0)}mm;">{CREDIT}</div>')
    page_w, page_h = PW, PH
    view = f'0 0 {PW} {PH}'
    title = f'{NAME} {ISSUE} 扉页'

# ------------------------------------------------------------------ fonts / css
def face(fam, path, extra=''):
    return f"@font-face{{font-family:'{fam}';src:url('file://{path}');{extra}}}"

faces = [face('Mast', os.path.join(FONTS, 'FW筑紫E老明朝.TTF')),
         face('FZHFS', os.path.join(FONTS, 'FZHengFSJF-M.TTF'), 'font-weight:500;'),
         face('ZQFS', os.path.join(FONTS, 'ZhuqueFangsong-Regular.ttf')),
         face('Seal', os.path.join(FONTS, '金陵刻经W.ttf'))]
if os.path.isdir(LOCAL) and OPT.get('fonts', 'local') == 'local':
    for w in (600, 700, 900):
        faces.append(face('SHS', f'{LOCAL}/CoverSong-{w}.ttf', f'font-weight:{w};'))
    for wd, wt in [(100, 500), (100, 700)]:
        faces.append(face('NSerif', f'{LOCAL}/CoverLatin-w{wd:g}-{wt}.ttf', f'font-weight:{wt};font-stretch:{wd:g}%;'))
else:
    for w, fn in [(600, 'SemiBold'), (700, 'Bold'), (900, 'Heavy')]:
        faces.append(face('SHS', os.path.join(FONTS, f'SourceHanSerifSC-{fn}.otf'), f'font-weight:{w};'))
    faces.append(face('NSerif', os.path.join(FONTS, 'NotoSerif[wdth,wght].ttf'), 'font-weight:100 900;font-stretch:62.5% 100%;'))

CSS = '\n'.join(faces) + f"""
@page {{ size: {page_w}mm {page_h}mm; margin: 0; }}
html, body {{ margin: 0; padding: 0; background: #fff; }}
.page {{ position: relative; width: {page_w}mm; height: {page_h}mm; overflow: hidden; background: #fff; color: #000; }}
svg.art {{ position: absolute; left: 0; top: 0; width: {page_w}mm; height: {page_h}mm; }}
.trim {{ position: absolute; left: {BLEED}mm; top: {BLEED}mm; width: {PW}mm; height: {PH}mm; }}
.abs {{ position: absolute; white-space: nowrap; }}
.c {{ transform: translate(-50%, -50%); text-align: center; }}
.vt {{ writing-mode: vertical-rl; transform: translateX(-50%); line-height: 1; }}
.mast {{ font-family: 'Mast'; text-align: center; }}
.top {{ font-family: 'FZHFS', 'ZQFS'; font-weight: 500; font-size: 12pt; letter-spacing: .16em; }}
.issue {{ font-family: 'SHS'; font-weight: 900; font-size: 17pt; letter-spacing: .4em; }}
.issue .yr {{ font-family: 'NSerif'; font-weight: 700; font-size: 20pt; letter-spacing: .06em; margin-top: .2em; }}
.issue.tv {{ font-size: 14pt; }}
.issue.tv .yr {{ font-size: 16.5pt; }}
.quote {{ font-family: 'FZHFS', 'ZQFS'; font-weight: 500; font-size: 13pt; letter-spacing: .18em; }}
.cite {{ font-family: 'FZHFS', 'ZQFS'; font-weight: 500; font-size: 12pt; letter-spacing: .12em; }}
.sig {{ font-family: 'FZHFS', 'ZQFS'; font-weight: 500; font-size: 12.5pt; letter-spacing: .22em; }}
.seal {{ font-family: 'Seal'; font-size: 16pt; letter-spacing: .02em; color: #fff; }}
.credit {{ font-family: 'FZHFS', 'ZQFS'; font-weight: 500; font-size: 13pt; letter-spacing: .35em; padding-left: .35em; }}
.stonelabel {{ font-family: 'SHS'; font-weight: 900; letter-spacing: .14em; padding-left: .14em; }}
"""

out = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{title}</title>
<style>{CSS}</style></head>
<body><div class="page">
<svg class="art" viewBox="{view}" xmlns="http://www.w3.org/2000/svg">
<defs>{''.join(defs)}</defs>
{body_svg}
</svg>
<div class="trim">
{chr(10).join(divs)}
</div>
</div></body></html>
"""
dst = OPT.get('out', os.path.join(HERE, f'issue2_{MODE}.html'))
open(dst, 'w', encoding='utf-8').write(out)
print('wrote', dst, f'mode={MODE}')
