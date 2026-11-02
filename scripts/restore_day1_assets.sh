#!/usr/bin/env bash
# Restore approved Day 1 media, accepting new Drive filenames without changing uploads.
set -euo pipefail

: "${DAY1_ASSET_DIR:?DAY1_ASSET_DIR must be set}"
: "${DAY1_ASSET_FOLDER_ID:?DAY1_ASSET_FOLDER_ID must be set}"

primary_remote="day1-assets:"
backup_remote="${DAY1_ASSET_BACKUP_REMOTE:-vortex-drive:FPL_VORTEX_DATA/01_DAY1_MEDIA_BACKUP}"
asset_names=(opening.mp4 Background_music.mp3 outro.mp3)

copy_approved_assets() {
  rclone copy "$1" "$2" \
    --filter '+ /opening.mp4' \
    --filter '+ /Background_music.mp3' \
    --filter '+ /outro.mp3' \
    --filter '+ /background.mp3' \
    --filter '+ /Outro.mp4' \
    --filter '- **' \
    --transfers 3 --checkers 6
}

list_missing_assets() {
  local name
  for name in "${asset_names[@]}"; do
    if [[ ! -s "${DAY1_ASSET_DIR}/${name}" ]]; then
      printf '%s\n' "${name}"
    fi
  done
}

require_stream() {
  local file="$1" stream="$2"
  if [[ -z "$(ffprobe -v error -select_streams "${stream}" \
      -show_entries stream=index -of csv=p=0 "${file}")" ]]; then
    echo "Invalid Day 1 asset (missing ${stream} stream): ${file##*/}" >&2
    exit 1
  fi
}


# The Day 1 mixer loops short background music. It uses exactly six seconds
# of outro audio and keeps the full opening image/video reveal.
normalize_approved_assets() {
  local input output temp duration
  input="\${DAY1_ASSET_DIR}/background.mp3"
  output="\${DAY1_ASSET_DIR}/Background_music.mp3"
  if [[ ! -s "\${output}" && -s "\${input}" ]]; then
    require_stream "\${input}" 'a:0'
    cp "\${input}" "\${output}"
    echo "Day 1 normalized background.mp3 -> Background_music.mp3 (looped by mixer)"
  fi

  input="\${DAY1_ASSET_DIR}/Outro.mp4"
  output="\${DAY1_ASSET_DIR}/outro.mp3"
  if [[ ! -s "\${output}" && -s "\${input}" ]]; then
    require_stream "\${input}" 'v:0'
    require_stream "\${input}" 'a:0'
    temp="\${DAY1_ASSET_DIR}/.outro-converted.mp3"
    rm -f "\${temp}"
    ffmpeg -hide_banner -loglevel error -y -i "\${input}" -map 0:a:0 \
      -t 6.0 -vn -c:a libmp3lame -b:a 192k -ar 48000 "\${temp}"
    mv "\${temp}" "\${output}"
    echo "Day 1 extracted first 6.0 seconds of Outro.mp4 audio -> outro.mp3"
  fi

  input="\${DAY1_ASSET_DIR}/opening.mp4"
  if [[ -s "\${input}" ]]; then
    require_stream "\${input}" 'v:0'
    require_stream "\${input}" 'a:0'
    duration="$(ffprobe -v error -show_entries format=duration \
      -of default=noprint_wrappers=1:nokey=1 "\${input}")"
    if python - "\${duration}" <<'PY'
import math
import sys
value = float(sys.argv[1])
if not math.isfinite(value) or value <= 0.5:
    raise SystemExit('Invalid Day 1 opening duration')
raise SystemExit(0 if value > 8.0 else 1)
PY
    then
      temp="\${DAY1_ASSET_DIR}/.opening-trimmed.mp4"
      rm -f "\${temp}"
      # Preserve the full WELCOME TO FPL VORTEX reveal visible near the end.
      ffmpeg -hide_banner -loglevel error -y -i "\${input}" -t 8.0 \
        -map 0:v:0 -map 0:a:0 -c:v libx264 -preset veryfast -crf 18 \
        -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart "\${temp}"
      mv "\${temp}" "\${input}"
      echo "Day 1 trimmed opening to 8.0 seconds (full logo reveal preserved)"
    fi
  fi
}

mkdir -p "${DAY1_ASSET_DIR}"
copy_approved_assets "${primary_remote}" "${DAY1_ASSET_DIR}"
normalize_approved_assets
mapfile -t missing < <(list_missing_assets)
if (( ${#missing[@]} > 0 )); then
  echo "Day 1 Drive asset folder ${DAY1_ASSET_FOLDER_ID} lacks: ${missing[*]}. Checking backup." >&2
  if rclone lsf "${backup_remote}" --max-depth 1 >/dev/null 2>&1; then
    copy_approved_assets "${backup_remote}" "${DAY1_ASSET_DIR}"
    normalize_approved_assets
  fi
fi
mapfile -t missing < <(list_missing_assets)
if (( ${#missing[@]} > 0 )); then
  echo "Required Day 1 original media unavailable in primary AND backup: ${missing[*]}." >&2
  echo "Provide opening.mp4 plus Background_music.mp3 or background.mp3 and outro.mp3 or Outro.mp4 in Google Drive folder ${DAY1_ASSET_FOLDER_ID}." >&2
  exit 1
fi

require_stream "${DAY1_ASSET_DIR}/opening.mp4" 'v:0'
require_stream "${DAY1_ASSET_DIR}/opening.mp4" 'a:0'
require_stream "${DAY1_ASSET_DIR}/Background_music.mp3" 'a:0'
require_stream "${DAY1_ASSET_DIR}/outro.mp3" 'a:0'
python - "${DAY1_ASSET_DIR}" <<'PY'
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

folder = Path(sys.argv[1])

def duration(filename):
    output = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(folder / filename)],
        text=True,
    ).strip()
    value = float(output)
    if not math.isfinite(value):
        raise ValueError(f"Invalid duration for {filename}")
    return value

for name, minimum in (("opening.mp4", 0.5), ("Background_music.mp3", 0.5), ("outro.mp3", 5.98)):
    if duration(name) <= minimum:
        raise SystemExit(f"Invalid Day 1 asset duration: {name}")

hashes = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
          for name in ("opening.mp4", "Background_music.mp3", "outro.mp3")}
if duration("opening.mp4") > 8.10:
    raise SystemExit("Day 1 opening exceeds eight-second target")
if hashes["Background_music.mp3"] == hashes["outro.mp3"]:
    raise SystemExit("Day 1 background and outro music must not be identical")
print("Verified Day 1 media SHA256: " + json.dumps(hashes, sort_keys=True))
print("Day 1 lengths: opening={:.3f}s, background={:.3f}s (loops), outro={:.3f}s".format(
    *(duration(name) for name in ("opening.mp4", "Background_music.mp3", "outro.mp3"))))
PY

# Seed/update backup only after validated canonical files pass integrity checks.
rclone mkdir "${backup_remote}"
copy_approved_assets "${DAY1_ASSET_DIR}" "${backup_remote}"
echo "Day 1 media restored, duration-checked, and backed up: PASS"
