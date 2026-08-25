#!/usr/bin/env bash
# Rebuild demo reel — strip the deck's show(0) JS from per-slide HTML so the
# forced .active class sticks; then encode 3s/slide.
set -euo pipefail
cd ~/cryptobot-train/slides
OUT=/home/surge/cryptobot-train/demo-reel.mp4
TMP=$(mktemp -d /tmp/reel.XXXX)
trap 'rm -rf "$TMP"' EXIT

python3 - "$TMP" <<'PY'
import re, sys, pathlib
tmp = pathlib.Path(sys.argv[1])
src = pathlib.Path("index.html").read_text()
# Remove the script block entirely (show(0) on load would override our forced active)
src_nojs = re.sub(r'<script>.*?</script>', '', src, flags=re.S)
for n in range(1, 11):
    doc = re.sub(r'class="slide active"', 'class="slide"', src_nojs)
    parts = doc.split('class="slide"')
    out = parts[0]
    for i, p in enumerate(parts[1:], start=1):
        cls = 'slide active' if i == n else 'slide'
        out += f'class="{cls}"' + p
    (tmp / f"slide-{n:02d}.html").write_text(out)
print("wrote", len(list(tmp.glob('slide-*.html'))), "slide pages (no JS)")
PY

for i in $(seq 1 10); do
  f=$(printf "slide-%02d.html" "$i")
  google-chrome --headless=new --disable-gpu --no-sandbox \
    --hide-scrollbars --window-size=1280,720 \
    --screenshot="$TMP/slide-$i.png" "file://$TMP/$f" >/dev/null 2>&1
done
echo "captured: $(ls "$TMP"/slide-*.png | wc -l) pngs"
echo "--- capture hashes (must be 10 distinct):"
md5sum "$TMP"/slide-*.png | awk '{print $1}'

ffmpeg -y -framerate 1/3 -i "$TMP/slide-%d.png" -vf "scale=1280:720,fps=30,format=yuv420p" \
  -c:v libx264 -crf 20 -preset medium -an "$OUT" >/dev/null 2>&1
echo "duration: $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")s"
echo "size: $(ls -la "$OUT" | awk '{print $5}') bytes"

V=/tmp/reelver.$$
mkdir -p "$V"
for t in 45 315 585 855; do
  ffmpeg -y -i "$OUT" -vf "select='eq(n\,$t)'" -vframes 1 "$V/f$t.png" >/dev/null 2>&1
done
echo "--- frame hashes (must differ):"
md5sum "$V"/f*.png | awk '{print $1}'
rm -rf "$V"
