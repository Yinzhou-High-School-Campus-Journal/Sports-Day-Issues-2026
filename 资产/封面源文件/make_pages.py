#!/usr/bin/env python3
"""《云图试骏》 issue 1 — front cover and title page (扉页), A4, black and white.

Scene: a five-lane track runs in one-point perspective into a sea of clouds
toward a rising sun (after 《山顶的云海日出》: 云海 "像千军万马正赴一场盛大的朝觐").
Lanes, left to right = the five sections in publication order. The campus
rises out of the cloud bank on the horizon, drawn from photographs of the real
school: the brick clock tower (emblem panel, paired openings) crossed by the
gate beam, the teaching blocks and the finned hall. Ginkgo leaves drift by.

  mode=cover  full-bleed cover (no page margins); bleed=3 adds 3 mm per side
  mode=title  title page: the same scene, simplified, in a round vignette

All text is at least 10.5 pt; everything is pure black line work. Units: mm.
Issue 1 (《云图试骏》) only; issue 2 (《骋风逐曜》) has its own design in make_issue2.py.
Rebuild everything with ./build.sh
"""
import os, sys, html, math, random

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.expanduser('~/Library/Fonts')
OPT = dict(a.split('=', 1) for a in sys.argv[1:] if '=' in a)
MODE = OPT.get('mode', 'cover')
if MODE == 'title':          # the simplified scene for the vignette
    for k, v in dict(nfar='7', nnear='2', nlow='1', ncorner='0', minstep='2.3', step='0.075', minoff='2.2',
                     fin='0', rightblock='0', leaves='0', wisps='0', names='0', swell='1.6',
                     towx='64', towtop='104', tb0='24', tb1='82', tbtop='127', gate='0',
                     hw0='15', hw1='24', hlo='0.6', hhi='1.8', zend='13').items():
        OPT.setdefault(k, v)
LOCAL = OPT.get('fontdir', os.path.join(HERE, 'fonts'))   # static TrueType subsets from fontprep.py
def opt(k, d):
    v = OPT.get(k)
    return type(d)(v) if v is not None else d

SECTIONS = ['校运风采', '少年心语', '校园绘卷', '社会观察', '古韵风雅']   # lanes left to right = publication order
EVENT = '鄞州中学第四十四届暨鄞州蓝青高级中学第二十九届运动会校刊'
YEAR, CREDIT = '2026', '媒体部主编'
# Each issue: its number, a quote from one of its articles, and how far the sun
# has climbed (issue 1: sunrise before the races; issue 2: the sun is up).
ISSUES = {
    '1': dict(name='第一期', quote=['翻涌着、奔流着，往天边涌去，', '像千军万马正赴一场盛大的朝觐。'],
              cite='——《山顶的云海日出》', sunrise=6.0, sunr=22.0,
              wisps=[(81, 133.2, 142, 129.5, -1.3, 0.85), (86, 137.2, 124, 135.4, -0.6, 0.45), (124, 106, 170, 101, -1.6, 0.62)],
              leaves=[(150.0, 121.0, 6.4, -32.0), (166.0, 128.0, 4.6, 24.0), (24.0, 110.0, 4.2, -58.0)]),
}
ISS = ISSUES[OPT.get('issue', '1')]
ISSUE, QUOTE, CITE = ISS['name'], ISS['quote'], ISS['cite']

PW, PH = 210.0, 297.0
BLEED = opt('bleed', 0.0) if MODE == 'cover' else 0.0
SWM = opt('swm', 1.0 if MODE == 'cover' else 1.45)      # stroke multiplier (vignette is drawn scaled)
CXV = PW / 2
YH = opt('yh', 152.0)            # horizon
HC = opt('hc', 131.0)            # screen offset of the ground at depth z = 1
YBOT = PH + BLEED + 2.0          # the scene runs past the bottom edge (full bleed)
XL, XR = -BLEED - 1.0, PW + BLEED + 1.0
TRACK_HALF = opt('th', 70.0)     # half track width at z = 1 (screen mm)
Z_END = opt('zend', 5.2)         # the track vanishes into cloud here
random.seed(opt('seed', 23))

svg, divs, defs = [], [], []

def esc(s):
    return html.escape(s, quote=False)

def P(x, y):
    return f'{x:.2f},{y:.2f}'

def sw(w):
    return f'{w * SWM:.3f}'

def line(x1, y1, x2, y2, w=0.3):
    svg.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="#000" stroke-width="{sw(w)}"/>')

def rect(x, y, w, h, s=0.3, fill='#fff'):
    svg.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" fill="{fill}" stroke="#000" stroke-width="{sw(s)}"/>')

def screen(xw, hw, z):
    return CXV + xw / z, YH + (HC - hw) / z

# rows: generous spacing in front, tightening toward the horizon
rows = []
off = YBOT - YH
while off > opt('minoff', 1.2):
    rows.append(HC / off)                            # depth z of this row
    off -= max(opt('minstep', 1.0), off * opt('step', 0.034))
rows.sort(reverse=True)                              # back to front

# ------------------------------------------------------------------ cloud field
# Cumulus billows: clusters of small hemispherical puffs (scalloped tops),
# higher toward each cluster's centre, on a gently swelling cloud floor.
puffs = []   # (x, z, rx, rz, h)
def cluster(xc, zc, Rx, Rz, H, m):
    for _ in range(m):
        while True:
            u, v = random.uniform(-1, 1), random.uniform(-1, 1)
            if u * u + v * v <= 1:
                break
        d2 = u * u + v * v
        r = max(Rx * random.uniform(0.22, 0.5), opt('minpuff', 3.4) * zc)   # no tiny spiky puffs
        puffs.append((xc + u * Rx * 0.85, zc + v * Rz * 0.85, r, Rz * r / Rx * random.uniform(0.8, 1.3),
                      H * (1 - 0.65 * d2) * random.uniform(0.75, 1.0)))

for _ in range(opt('nfar', 22)):
    z = random.uniform(Z_END - 0.3, 15.0)
    cluster(random.uniform(-560, 560) * (z / 6), z, random.uniform(60, 150) * (z / 5) ** 0.5,
            random.uniform(0.5, 1.6) * (z / 6), random.uniform(20, 48) * (z / 6) ** 0.55, random.randint(7, 13))
for side in (-1, 1):
    for _ in range(opt('nnear', 11)):
        z = random.uniform(1.1, Z_END + 0.6)
        cluster(side * random.uniform(TRACK_HALF + opt('nearmin', 20), TRACK_HALF + opt('nearmax', 150)) * (0.75 + 0.25 * z), z,
                random.uniform(38, 85), random.uniform(0.22, 0.5) * z, random.uniform(14, 34), random.randint(7, 12))
    for _ in range(opt('nlow', 3)):                 # low billows hugging the track
        z = random.uniform(1.15, 2.6)
        cluster(side * random.uniform(TRACK_HALF + 32, TRACK_HALF + 70) * z ** 0.3, z,
                random.uniform(26, 48), random.uniform(0.16, 0.3) * z, random.uniform(8, 18), random.randint(6, 10))
# big foreground billows in the bottom corners (the cover now runs to the edges)
crng = random.Random(opt('cseed', 5))
for side in (-1, 1):
    for _ in range(opt('ncorner', 3)):
        z = crng.uniform(0.9, 1.25)
        cluster(side * crng.uniform(TRACK_HALF + 30, TRACK_HALF + 55) * z, z, crng.uniform(30, 55),
                crng.uniform(0.12, 0.22), crng.uniform(16, 30), crng.randint(6, 9))

# horizon billows in front of the campus skyline, so the far rows swallow the building bases
if opt('campus', 1) and opt('hmist', 1):
    hm = random.Random(opt('hmseed', 8))
    spans = [(opt('tb0', 17.0) - 2, opt('tb1', 79.0) + 2)]
    if opt('fin', 1):
        spans.append((opt('fh0', 136.0) - 2, opt('tc1', 196.5) + 2))
    for (sx0, sx1) in spans:
        x = sx0
        while x < sx1:
            cand_z = [rz_ for rz_ in rows if opt('hz0', 40.0) <= rz_ <= opt('hz1', 115.0)] or rows[:3]
            z = hm.choice(cand_z)
            w = hm.uniform(opt('hw0', 10.0), opt('hw1', 18.0))          # screen width of the billow
            lift = hm.uniform(opt('hlo', 1.4), opt('hhi', 3.8))       # mm above the horizon
            puffs.append(((x + w / 2 - CXV) * z, z, w / 2 * z, z * opt('hrz', 0.18), HC + lift * z))
            for side in (-1, 1):                                       # shoulders: scalloped cumulus top
                if hm.random() < 0.75:
                    w2 = w * hm.uniform(0.4, 0.62)
                    puffs.append(((x + w / 2 + side * w * hm.uniform(0.3, 0.45) - CXV) * z, z, w2 / 2 * z,
                                  z * opt('hrz', 0.18), HC + lift * hm.uniform(0.5, 0.85) * z))
            x += w * hm.uniform(0.5, 0.8)
PUFF_Z = [(pz - rz, pz + rz, px, pz, rx, rz, ph) for (px, pz, rx, rz, ph) in puffs]
SWELL = opt('swell', 3.2)
PH1, PH2 = random.uniform(0, 6.3), random.uniform(0, 6.3)
PROF = opt('prof', 0.6)

def cloud_h(xw, z, cand=None):
    h = SWELL * (0.5 + 0.5 * math.sin(xw / 23.0 + z * 2.1 + PH1)) * (0.5 + 0.5 * math.sin(xw / 61.0 - z * 1.3 + PH2))
    for (z0, z1, px, pz, rx, rz, ph) in (cand if cand is not None else PUFF_Z):
        dx = (xw - px) / rx
        if -1 < dx < 1:
            dz = (z - pz) / rz
            q = 1 - dx * dx - dz * dz
            if q > 0:
                v = ph * q ** PROF
                if v > h:
                    h = v
    if z < Z_END:                                   # clear corridor for the track
        edge = abs(xw) - TRACK_HALF
        k = min(1.0, max(0.0, edge / 30.0))
        h *= k * k * (3 - 2 * k)
    return h

# ------------------------------------------------------------------ sky
SUN_R = opt('sunr', ISS['sunr'])
SUN_Y = YH - opt('sunrise', ISS['sunrise'])
svg.append(f'<circle cx="{CXV}" cy="{SUN_Y:.2f}" r="{SUN_R}" fill="#fff" stroke="#000" stroke-width="{sw(0.6)}"/>')

def wisp(x0, y0, x1, y1, bend, wmax):
    """Thin tapered cirrus streak along a gentle arc."""
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    nx, ny = -dy / L, dx / L
    cx, cy = mx + nx * bend, my + ny * bend
    top, bot = [], []
    n = 48
    for i in range(n + 1):
        u = i / n
        x = (1 - u) ** 2 * x0 + 2 * (1 - u) * u * cx + u * u * x1
        y = (1 - u) ** 2 * y0 + 2 * (1 - u) * u * cy + u * u * y1
        tx = 2 * (1 - u) * (cx - x0) + 2 * u * (x1 - cx)
        ty = 2 * (1 - u) * (cy - y0) + 2 * u * (y1 - cy)
        tl = math.hypot(tx, ty)
        px, py = -ty / tl, tx / tl
        w = wmax * math.sin(math.pi * u) ** 0.9 * (1 - 0.35 * u)      # heavier head, fine tail
        top.append((x + px * w / 2, y + py * w / 2))
        bot.append((x - px * w / 2, y - py * w / 2))
    svg.append(f'<polygon points="{" ".join(P(*q) for q in top + bot[::-1])}" fill="#000"/>')

if opt('wisps', 1):
    for (x0, y0, x1, y1, b, w) in ISS['wisps']:
        wisp(x0, y0, x1, y1, b, w)

# ------------------------------------------------------------------ campus skyline
# Line drawings after photographs of the real campus (Wikimedia Commons:
# "Gate of the Ningbo Yinzhou High School", "... seen from the southeast").
def teaching_block(x0, x1, top, base, nrows=3, pitch=1.75):
    rect(x0, top, x1 - x0, base - top, 0.3)
    line(x0, top + 1.1, x1, top + 1.1, 0.18)                      # parapet course
    for r in range(nrows):
        y0 = top + 2.4 + r * 3.1
        x = x0 + 1.2
        while x < x1 - 1.0:
            line(x, y0, x, y0 + 1.9, 0.3)
            x += pitch

def finned_hall(x0, x1, top, base, pitch=0.95):
    rect(x0, top, x1 - x0, base - top, 0.3)
    line(x0, top + 1.6, x1, top + 1.6, 0.25)                      # roof band
    x = x0 + 0.9
    while x < x1 - 0.6:
        line(x, top + 3.0, x, base, 0.2)
        x += pitch

def clock_tower(x0, top, base, wf=11.0, ws=3.8):
    """Front face lit (white), side face in shade (horizontal brick hatching)."""
    xs = x0 + wf
    svg.append(f'<polygon points="{P(xs, top + 0.9)} {P(xs + ws, top + 0.9)} {P(xs + ws, base)} {P(xs, base)}" fill="#fff" stroke="#000" stroke-width="{sw(0.3)}"/>')
    y = top + 1.6
    while y < base:
        line(xs, y, xs + ws, y, 0.17)
        y += opt('hatch', 0.72)
    svg.append(f'<rect x="{xs + ws * 0.24:.2f}" y="{top + 5.2:.2f}" width="{ws * 0.52:.2f}" height="10.5" fill="#000"/>')
    n0, n1 = x0 + wf * 0.44, x0 + wf * 0.53
    svg.append(f'<polygon points="{P(x0, base)} {P(x0, top)} {P(n0, top)} {P(n0, top + 1.1)} {P(n1, top + 1.1)} {P(n1, top)} {P(xs, top)} {P(xs, base)}" '
               f'fill="#fff" stroke="#000" stroke-width="{sw(0.35)}" stroke-linejoin="miter"/>')
    e = wf * 0.5
    ex, ey = x0 + (wf - e) / 2, top + 3.4
    rect(ex, ey, e, e, 0.28)
    svg.append(f'<circle cx="{ex + e / 2:.2f}" cy="{ey + e / 2:.2f}" r="{e * 0.36:.2f}" fill="none" stroke="#000" stroke-width="{sw(0.28)}"/>')
    svg.append(f'<circle cx="{ex + e / 2:.2f}" cy="{ey + e / 2:.2f}" r="{e * 0.27:.2f}" fill="none" stroke="#000" stroke-width="{sw(0.14)}"/>')
    y = ey + e + 3.2
    hs = 0.72
    while y < base - 2:
        for fx in (0.2, 0.31, 0.69, 0.8):
            svg.append(f'<rect x="{x0 + wf * fx - hs / 2:.2f}" y="{y:.2f}" width="{hs}" height="{hs}" fill="#000"/>')
        y += opt('holepitch', 3.3)

def gate(x0, x1, y, base, depth=2.6):
    """The long flat gate beam that crosses in front of the tower, on slim columns."""
    for cx in [x0 + 8.0, (x0 + x1) / 2 - 6.0]:
        rect(cx - 0.6, y + depth, 1.2, base - y - depth, 0.28)
    px = x1 - 5.5                                                  # the name pillar
    rect(px, y, 4.2, base - y, 0.32)
    rect(px + 1.35, y + depth + 1.6, 1.5, 9.0, 0.2)
    rect(x0, y, x1 - x0, depth, 0.36)
    line(x0, y + depth - 0.7, px, y + depth - 0.7, 0.18)          # soffit edge

if opt('campus', 1):
    base = YH + 8.0                           # hidden under the far cloud rows
    teaching_block(opt('tb0', XL), opt('tb1', 78.0), opt('tbtop', 128.5), base, nrows=opt('tbrows', 5))
    clock_tower(opt('towx', 40.0), opt('towtop', 100.0), base)
    if opt('gate', 1):
        gate(opt('g0', XL), opt('g1', 77.0), opt('gy', 132.0), base)
    if opt('fin', 1):
        finned_hall(opt('fh0', 136.0), opt('fh1', 176.0), opt('fhtop', 136.0), base)
    if opt('rightblock', 1):
        teaching_block(opt('tc0', 176.0), opt('tc1', XR), opt('tctop', 139.5), base, nrows=2)

def ginkgo(cx, cy, R, rot_deg, veins=13):
    """Line-drawn ginkgo leaf: fan blade with a notched rim, radiating veins, stem."""
    rot = math.radians(rot_deg)
    def T(x, y):
        xr = x * math.cos(rot) + y * math.sin(rot)
        yr = -x * math.sin(rot) + y * math.cos(rot)
        return cx + xr, cy - yr
    half = math.radians(68)
    def rim(t):
        th = math.pi / 2 + half - 2 * half * t
        notch = 0.2 * max(0.0, 1 - abs(t - 0.5) / 0.09)
        wave = 0.025 * math.sin(t * math.pi * 7)
        r = R * (1 - notch + wave)
        return r * math.cos(th), r * math.sin(th)
    pts = []
    x0, y0 = rim(0)
    for i in range(1, 9):
        f = i / 9
        pts.append((x0 * f - 0.08 * R * math.sin(f * math.pi), y0 * f * (0.92 + 0.08 * f)))
    for i in range(61):
        pts.append(rim(i / 60))
    x1, y1 = rim(1)
    for i in range(8, 0, -1):
        f = i / 9
        pts.append((x1 * f + 0.08 * R * math.sin(f * math.pi), y1 * f * (0.92 + 0.08 * f)))
    page = [T(0, 0)] + [T(*q) for q in pts]
    svg.append(f'<polygon points="{" ".join(P(*q) for q in page)}" fill="#fff" stroke="#000" stroke-width="{sw(0.3)}" stroke-linejoin="round"/>')
    for k in range(1, veins):
        t = k / veins
        ex, ey = rim(t)
        a0 = 0.12 + 0.1 * abs(t - 0.5)
        sx, sy = T(ex * a0, ey * a0)
        tx, ty = T(ex * 0.93, ey * 0.93)
        svg.append(f'<line x1="{sx:.2f}" y1="{sy:.2f}" x2="{tx:.2f}" y2="{ty:.2f}" stroke="#000" stroke-width="{sw(0.12)}"/>')
    s0 = T(0, 0); s1 = T(0.06 * R, -0.22 * R); s2 = T(0.02 * R, -0.46 * R)
    svg.append(f'<path d="M{P(*s0)} Q{P(*s1)} {P(*s2)}" fill="none" stroke="#000" stroke-width="{sw(0.32)}" stroke-linecap="round"/>')

if opt('leaves', 1):
    for (lx, ly, lr, la) in ISS['leaves']:
        ginkgo(lx, ly, lr, la)

# ------------------------------------------------------------------ clouds and track
def track_x(y, sign):
    z = HC / (y - YH)
    return CXV + sign * TRACK_HALF / z
y_te = YH + HC / Z_END
trap = [(track_x(YBOT, -1), YBOT), (track_x(y_te, -1), y_te), (track_x(y_te, 1), y_te), (track_x(YBOT, 1), YBOT)]
E = BLEED + 6
defs.append('<clipPath id="sides" clipPathUnits="userSpaceOnUse"><path clip-rule="evenodd" d="'
            f'M{-E},{-E} H{PW + E} V{PH + E} H{-E} Z M{P(*trap[0])} L{P(*trap[1])} L{P(*trap[2])} L{P(*trap[3])} Z"/></clipPath>')

def row_path(z):
    pts = []
    n = opt('samples', 340)
    cand = [p for p in PUFF_Z if p[0] < z < p[1]]
    for i in range(n + 1):
        x = XL + (XR - XL) * i / n
        xw = (x - CXV) * z
        pts.append((x, YH + (HC - cloud_h(xw, z, cand)) / z))
    return pts, YH + HC / z

far_rows = [z for z in rows if z >= Z_END]
near_rows = [z for z in rows if z < Z_END]

def emit_rows(zs, clip=None):
    out = []
    for z in zs:
        pts, base = row_path(z)
        w = max(0.2, min(0.45, 0.42 / z ** 0.35))
        fill_pts = pts + [(pts[-1][0], base + 8), (pts[0][0], base + 8)]
        out.append(f'<polygon points="{" ".join(P(*p) for p in fill_pts)}" fill="#fff"/>')
        out.append(f'<polyline points="{" ".join(P(*p) for p in pts)}" fill="none" stroke="#000" stroke-width="{sw(w)}" stroke-linejoin="round"/>')
    svg.append((f'<g clip-path="url(#{clip})">' if clip else '<g>') + ''.join(out) + '</g>')

emit_rows(far_rows)
svg.append(f'<polygon points="{" ".join(P(*p) for p in trap)}" fill="#fff"/>')
z_front = HC / (YBOT - YH)
for k in range(6):
    xw = -TRACK_HALF + k * (2 * TRACK_HALF / 5)
    xb, yb = screen(xw, 0, z_front)
    xe, ye = screen(xw, 0, Z_END)
    wb, we = opt('lanew', 1.1) / SWM ** 0.5, 0.18
    svg.append(f'<polygon points="{P(xb - wb / 2, yb)} {P(xe - we / 2, ye)} {P(xe + we / 2, ye)} {P(xb + wb / 2, yb)}" fill="#000"/>')
emit_rows(near_rows, 'sides')

if opt('startline', 1):
    zs = opt('startz', 0.985)
    xa, ya = screen(-TRACK_HALF, 0, zs)
    xb2, _ = screen(TRACK_HALF, 0, zs)
    svg.append(f'<line x1="{xa:.2f}" y1="{ya:.2f}" x2="{xb2:.2f}" y2="{ya:.2f}" stroke="#000" stroke-width="{sw(opt("startw", 1.0))}"/>')
if opt('names', 1):
    name_z = opt('namez', 1.04)
    for k, name in enumerate(SECTIONS):
        xw = -TRACK_HALF + (k + 0.5) * (2 * TRACK_HALF / 5)
        x, y = screen(xw, 0, name_z)
        divs.append(f'<div class="abs c lanename" style="left:{x:.2f}mm;top:{y:.2f}mm;">{esc(name)}</div>')

# ------------------------------------------------------------------ type
def mast(cx, top, size, gap):
    w = 4 * size + 3 * gap
    for i, ch in enumerate('云图试骏'):
        divs.append(f'<div class="abs mast" style="left:{cx - w / 2 + i * (size + gap):.2f}mm;top:{top:.2f}mm;'
                    f'width:{size}mm;height:{size}mm;font-size:{size}mm;line-height:{size}mm;">{ch}</div>')

if MODE == 'cover':
    MS, MG, my = opt('ms', 44.0), opt('mg', 3.0), opt('my', 20.5)
    divs.append(f'<div class="abs c top" style="left:{CXV}mm;top:{opt("topy", 13.2)}mm;">{EVENT}</div>')
    mast(CXV, my, MS, MG)
    divs.append(f'<div class="abs c issue" style="left:{CXV}mm;top:{my + MS + opt("issuegap", 7.6):.2f}mm;">{ISSUE}<span class="yr">{YEAR}</span></div>')
    qy = opt('qy', 88.5)
    divs.append(f'<div class="abs c quote" style="left:{CXV}mm;top:{qy}mm;">{"<br>".join(QUOTE)}</div>')
    divs.append(f'<div class="abs c cite" style="left:{CXV}mm;top:{qy + opt("citegap", 12.4):.2f}mm;">{CITE}</div>')
    # signature column with a seal, as on a painting
    sx, sy = opt('sigx', 190.0), opt('sigy', 80.0)
    divs.append(f'<div class="abs sig" style="left:{sx:.2f}mm;top:{sy:.2f}mm;">{CREDIT}</div>')
    seal_w, seal_h = 7.4, 14.6
    seal_y = sy + opt('sealgap', 27.0)
    svg.append(f'<rect x="{sx - seal_w / 2:.2f}" y="{seal_y:.2f}" width="{seal_w}" height="{seal_h}" fill="#000"/>')
    divs.append(f'<div class="abs seal" style="left:{sx:.2f}mm;top:{seal_y + 1.4:.2f}mm;">鄞中</div>')
    page_w, page_h = PW + 2 * BLEED, PH + 2 * BLEED
    view = f'{-BLEED} {-BLEED} {page_w} {page_h}'
    body_svg = '\n'.join(svg)
    title = f'云图试骏 {ISSUE} 封面'
else:
    # title page: margins as the interior (about 27 mm at the sides)
    VC, VR = (105.0, opt('vcy', 170.0)), opt('vr', 82.0)        # vignette window in scene coordinates
    PC, PR = (105.0, opt('pcy', 170.0)), opt('pr', 50.0)        # where it sits on the page
    s = PR / VR
    defs.append(f'<clipPath id="vig" clipPathUnits="userSpaceOnUse"><circle cx="{VC[0]}" cy="{VC[1]}" r="{VR}"/></clipPath>')
    scene = '\n'.join(svg)
    body_svg = (f'<g transform="translate({PC[0] - VC[0] * s:.3f},{PC[1] - VC[1] * s:.3f}) scale({s:.5f})">'
                f'<g clip-path="url(#vig)">{scene}</g></g>'
                f'<circle cx="{PC[0]}" cy="{PC[1]}" r="{PR}" fill="none" stroke="#000" stroke-width="0.5"/>'
                f'<circle cx="{PC[0]}" cy="{PC[1]}" r="{PR + 2.2:.2f}" fill="none" stroke="#000" stroke-width="0.2"/>')
    divs = []
    divs.append(f'<div class="abs c top" style="left:{CXV}mm;top:{opt("ttopy", 47.0)}mm;">{EVENT}</div>')
    mast(CXV, opt('tmy', 58.0), opt('tms', 30.0), opt('tmg', 2.4))
    divs.append(f'<div class="abs c issue t" style="left:{CXV}mm;top:{opt("tissuey", 100.5)}mm;">{ISSUE}<span class="yr">{YEAR}</span></div>')
    divs.append(f'<div class="abs c credit" style="left:{CXV}mm;top:{opt("tcredy", 256.0)}mm;">{CREDIT}</div>')
    page_w, page_h = PW, PH
    view = f'0 0 {PW} {PH}'
    title = f'云图试骏 {ISSUE} 扉页'

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
.mast {{ font-family: 'Mast'; text-align: center; }}
.top {{ font-family: 'FZHFS', 'ZQFS'; font-weight: 500; font-size: 12pt; letter-spacing: .16em; }}
.issue {{ font-family: 'SHS'; font-weight: 900; font-size: 17pt; letter-spacing: .4em; padding-left: .4em; }}
.issue .yr {{ font-family: 'NSerif'; font-weight: 700; font-size: 20pt; letter-spacing: .06em; margin-left: .2em; }}
.issue.t {{ font-size: 14pt; }}
.issue.t .yr {{ font-size: 16.5pt; }}
.quote {{ font-family: 'FZHFS', 'ZQFS'; font-weight: 500; font-size: 12.5pt; line-height: 1.75; letter-spacing: .1em; }}
.cite {{ font-family: 'FZHFS', 'ZQFS'; font-weight: 500; font-size: 12pt; letter-spacing: .05em; }}
.sig {{ font-family: 'FZHFS', 'ZQFS'; font-weight: 500; font-size: 12.5pt; letter-spacing: .22em; line-height: 1;
  writing-mode: vertical-rl; text-orientation: upright; transform: translateX(-50%); }}
.seal {{ font-family: 'Seal'; font-size: 16pt; line-height: 1; letter-spacing: .02em; color: #fff;
  writing-mode: vertical-rl; text-orientation: upright; transform: translateX(-50%); }}
.credit {{ font-family: 'FZHFS', 'ZQFS'; font-weight: 500; font-size: 13pt; letter-spacing: .35em; padding-left: .35em; }}
.lanename {{ font-family: 'SHS'; font-weight: 900; font-size: 13pt; letter-spacing: .16em; padding-left: .16em; }}
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
dst = OPT.get('out', os.path.join(HERE, f'{MODE}.html'))
open(dst, 'w', encoding='utf-8').write(out)
print('wrote', dst, f'mode={MODE} bleed={BLEED} rows={len(rows)} far={len(far_rows)} near={len(near_rows)}')
