#!/bin/zsh
# Rebuild the covers and title pages (扉页) of both issues into the parent folder:
#   第N期封面.pdf / .png     A4, full bleed (no page margins), PNG at 300 dpi
#   第N期封面-出血3mm.pdf    216 x 303 mm with 3 mm bleed, for print shops that trim
#   第N期扉页.pdf / .png     A4 title page
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
for i in 1 2; do for m in cover title; do
  python3 make_pages.py issue=$i mode=$m out="$TMP/$i-$m.html" fontdir="$TMP/fonts" >/dev/null
done; done
cat "$TMP"/*.html > "$TMP/alltext.txt"
uv run --no-project --with fonttools python fontprep.py "$TMP/alltext.txt" "$TMP/fonts" >/dev/null
OUT="$PWD/.."
typeset -A CN; CN=(1 一 2 二)
for i in 1 2; do
  N="第${CN[$i]}期"
  python3 make_pages.py issue=$i mode=cover out="$TMP/$i-cover.html" fontdir="$TMP/fonts" >/dev/null
  python3 make_pages.py issue=$i mode=cover bleed=3 out="$TMP/$i-bleed.html" fontdir="$TMP/fonts" >/dev/null
  python3 make_pages.py issue=$i mode=title out="$TMP/$i-title.html" fontdir="$TMP/fonts" >/dev/null
  pdf "$TMP/$i-cover.html" "$OUT/${N}封面.pdf";  png "$TMP/$i-cover.html" "$OUT/${N}封面.png"
  pdf "$TMP/$i-bleed.html" "$OUT/${N}封面-出血3mm.pdf"
  pdf "$TMP/$i-title.html" "$OUT/${N}扉页.pdf";  png "$TMP/$i-title.html" "$OUT/${N}扉页.png"
done
rm -rf "$TMP"
ls -la "$OUT"/第*期*
