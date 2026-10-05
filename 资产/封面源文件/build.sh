#!/bin/zsh
# Rebuild the editorial covers and title pages (扉页) into the parent folder (资产/):
#   第一期《云图试骏》 make_pages.py   封面.pdf / .png (A4, full bleed), 封面-出血3mm.pdf, 扉页.pdf / .png
#   第二期《骋风逐曜》 make_issue2.py  封面.pdf / .png (A4, full bleed), 扉页.pdf / .png
# Needs Google Chrome; fontprep.py also needs uv (fetches fonttools) so the PDFs
# embed plain TrueType fonts instead of Type 3.
set -e
cd "$(dirname "$0")"
TMP=$(mktemp -d)
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
pdf() { "$CH" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files \
          --no-pdf-header-footer --print-to-pdf="$2" "file://$1" 2>/dev/null; }
png() { "$CH" --headless=new --disable-gpu --hide-scrollbars --allow-file-access-from-files \
          --force-device-scale-factor=3.125 --window-size=794,1123 --screenshot="$2" "file://$1" 2>/dev/null; }
pages() {   # $1 = font dir
  python3 make_pages.py issue=1 mode=cover out="$TMP/1-cover.html" fontdir="$1" >/dev/null
  python3 make_pages.py issue=1 mode=cover bleed=3 out="$TMP/1-bleed.html" fontdir="$1" >/dev/null
  python3 make_pages.py issue=1 mode=title out="$TMP/1-title.html" fontdir="$1" >/dev/null
  python3 make_issue2.py mode=cover out="$TMP/2-cover.html" fontdir="$1" >/dev/null
  python3 make_issue2.py mode=title out="$TMP/2-title.html" fontdir="$1" >/dev/null
}
pages "$TMP/fonts"
cat "$TMP"/*.html > "$TMP/alltext.txt"
uv run --no-project --with fonttools python fontprep.py "$TMP/alltext.txt" "$TMP/fonts" >/dev/null
pages "$TMP/fonts"
OUT="${OUT:-$PWD/..}"
pdf "$TMP/1-cover.html" "$OUT/第一期封面.pdf";  png "$TMP/1-cover.html" "$OUT/第一期封面.png"
pdf "$TMP/1-bleed.html" "$OUT/第一期封面-出血3mm.pdf"
pdf "$TMP/1-title.html" "$OUT/第一期扉页.pdf";  png "$TMP/1-title.html" "$OUT/第一期扉页.png"
pdf "$TMP/2-cover.html" "$OUT/第二期封面.pdf";  png "$TMP/2-cover.html" "$OUT/第二期封面.png"
pdf "$TMP/2-title.html" "$OUT/第二期扉页.pdf";  png "$TMP/2-title.html" "$OUT/第二期扉页.png"
rm -rf "$TMP"
ls -la "$OUT"/第*期*
