"""Make print-safe static TrueType subsets of the cover's CFF / variable fonts.

Chrome embeds CFF-flavoured OTFs and variable fonts as Type 3 fonts in PDFs.
Converting the glyphs we actually use to static glyf-based TTFs lets every
font embed as an ordinary CIDFontType2. Run with:
    uv run --no-project --with fonttools python fontprep.py <cover.html> <outdir>
"""
import os, re, sys, html
from fontTools.ttLib import TTFont, newTable
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools import subset
from fontTools.varLib import instancer

FONTS = os.path.expanduser('~/Library/Fonts')
src_html, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)

body = open(src_html, encoding='utf-8').read()
body = body.split('<body>', 1)[1]
text = html.unescape(re.sub(r'<[^>]+>', '', body))
chars = set(text) | set(chr(c) for c in range(0x20, 0x7F)) | set('，。：；、「」《》——…·〇')
chars = ''.join(sorted(ch for ch in chars if not ch.isspace() or ch == ' '))


def do_subset(font):
    opts = subset.Options()
    opts.layout_features = ['*']
    opts.name_IDs = ['*']
    opts.notdef_outline = True
    opts.glyph_names = False
    opts.hinting = False
    s = subset.Subsetter(opts)
    s.populate(text=chars)
    s.subset(font)


def cff_to_glyf(font):
    glyph_order = font.getGlyphOrder()
    gs = font.getGlyphSet()
    quad = {}
    for name in glyph_order:
        tt_pen = TTGlyphPen(gs)
        gs[name].draw(Cu2QuPen(tt_pen, 1.0, reverse_direction=True))
        quad[name] = tt_pen.glyph()
    font['loca'] = newTable('loca')
    font['glyf'] = glyf = newTable('glyf')
    glyf.glyphOrder = glyph_order
    glyf.glyphs = quad
    del font['CFF ']
    if 'VORG' in font:
        del font['VORG']
    glyf.compile(font)
    hmtx = font['hmtx']
    for name, g in glyf.glyphs.items():
        if hasattr(g, 'xMin'):
            hmtx[name] = (hmtx[name][0], g.xMin)
    maxp = font['maxp'] = newTable('maxp')
    maxp.tableVersion = 0x00010000
    for attr in ('maxZones', 'maxTwilightPoints', 'maxStorage', 'maxFunctionDefs',
                 'maxInstructionDefs', 'maxStackElements', 'maxSizeOfInstructions',
                 'maxComponentElements'):
        setattr(maxp, attr, 1 if attr == 'maxZones' else 0)
    maxp.compile(font)
    post = font['post']
    post.formatType = 3.0
    font.sfntVersion = '\x00\x01\x00\x00'


def rename(font, family):
    # new family name so the subset never claims a reserved font name
    for rec in font['name'].names:
        if rec.nameID in (1, 3, 4, 6, 16, 17, 21, 22):
            val = family if rec.nameID in (1, 16, 21) else f'{family} Regular'
            if rec.nameID == 6:
                val = family.replace(' ', '') + '-Regular'
            rec.string = val


jobs = []
for w, fn in [(600, 'SourceHanSerifSC-SemiBold.otf'), (700, 'SourceHanSerifSC-Bold.otf'),
              (900, 'SourceHanSerifSC-Heavy.otf')]:
    f = TTFont(os.path.join(FONTS, fn))
    do_subset(f)
    cff_to_glyf(f)
    rename(f, f'CoverSong {w}')
    out = os.path.join(outdir, f'CoverSong-{w}.ttf')
    f.save(out)
    jobs.append(out)

for wd, wt in [(100, 500), (100, 700)]:
    f = TTFont(os.path.join(FONTS, 'NotoSerif[wdth,wght].ttf'))
    f = instancer.instantiateVariableFont(f, {'wdth': wd, 'wght': wt})
    do_subset(f)
    rename(f, f'CoverLatin {wd:g} {wt}')
    out = os.path.join(outdir, f'CoverLatin-w{wd:g}-{wt}.ttf')
    f.save(out)
    jobs.append(out)

for j in jobs:
    print(os.path.basename(j), os.path.getsize(j))
print('chars:', len(chars))
