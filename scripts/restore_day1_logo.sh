#!/usr/bin/env bash
# Restore the approved Day 1 lion logo, or derive it from the user's opening video.
set -euo pipefail

: "${DAY1_ASSET_DIR:?DAY1_ASSET_DIR must be set}"
logo="${DAY1_LOGO_FILE:-/content/drive/MyDrive/elements/logo.png}"
opening="${DAY1_ASSET_DIR}/opening.mp4"

is_valid_png() {
  [[ -s "$1" ]] &&
    [[ "$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$1" | head -n 1)" == "png" ]]
}

# Do not overwrite an existing valid logo restored through Drive.
if is_valid_png "$logo"; then
  echo "Day 1 original logo restored: $logo"
  exit 0
fi

if [[ ! -s "$opening" ]]; then
  echo "Day 1 brand logo missing and approved opening.mp4 unavailable: $logo" >&2
  exit 1
fi

duration="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$opening")"
python - "$duration" <<'PY'
import math
import sys
try:
    duration = float(sys.argv[1])
except ValueError:
    raise SystemExit("Invalid Day 1 opening media duration")
if not math.isfinite(duration) or duration < 7.0:
    raise SystemExit(f"Day 1 opening ({duration:.3f}s) is too short for approved 6s logo frame")
PY

mkdir -p "$(dirname "$logo")"
tmp="${logo%.png}.tmp.png"
trap 'rm -f "$tmp"' EXIT
rm -f "$tmp"

# The 6s frame contains the complete branded lion crest, without intro text in
# the crop. Coordinates scale with the video's actual resolution.
ffmpeg -hide_banner -loglevel error -y -ss 6.0 -i "$opening" -vf \
  'crop=iw*0.34:ih*0.62:(iw-ow)/2:ih*0.08' -frames:v 1 -f image2 "$tmp"

if ! is_valid_png "$tmp"; then
  echo "Failed to extract a valid FPL VORTEX logo from approved opening.mp4" >&2
  exit 1
fi
mv "$tmp" "$logo"
echo "Day 1 lion logo recovered from approved opening.mp4 at 6s: $logo"
