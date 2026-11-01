#!/usr/bin/env bash
# Restore Day 1's original opening/audio, retaining a separate Drive backup.
set -euo pipefail

: "${DAY1_ASSET_DIR:?DAY1_ASSET_DIR must be set}"
: "${DAY1_ASSET_FOLDER_ID:?DAY1_ASSET_FOLDER_ID must be set}"

primary_remote="day1-assets:"
backup_remote="${DAY1_ASSET_BACKUP_REMOTE:-vortex-drive:FPL_VORTEX_DATA/01_DAY1_MEDIA_BACKUP}"
asset_names=(opening.mp4 Background_music.mp3 outro.mp3)

copy_required_assets() {
  rclone copy "$1" "$2" \
    --filter '+ /opening.mp4' \
    --filter '+ /Background_music.mp3' \
    --filter '+ /outro.mp3' \
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

mkdir -p "${DAY1_ASSET_DIR}"
copy_required_assets "${primary_remote}" "${DAY1_ASSET_DIR}"
mapfile -t missing < <(list_missing_assets)
if (( ${#missing[@]} > 0 )); then
  echo "Day 1 Drive asset folder ${DAY1_ASSET_FOLDER_ID} lacks: ${missing[*]}. Checking backup." >&2
  if rclone lsf "${backup_remote}" --max-depth 1 >/dev/null 2>&1; then
    copy_required_assets "${backup_remote}" "${DAY1_ASSET_DIR}"
  fi
fi
mapfile -t missing < <(list_missing_assets)
if (( ${#missing[@]} > 0 )); then
  echo "Required Day 1 original media unavailable in primary AND backup: ${missing[*]}." >&2
  echo "Restore these three original files in Google Drive folder ${DAY1_ASSET_FOLDER_ID}; no substitute media will be generated." >&2
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
if hashes["Background_music.mp3"] == hashes["outro.mp3"]:
    raise SystemExit("Day 1 background and outro music must not be identical")
print("Verified authentic Day 1 media files (SHA256): " + json.dumps(hashes, sort_keys=True))
PY

# Seed/update backup only after all three real source files pass integrity checks.
rclone mkdir "${backup_remote}"
copy_required_assets "${DAY1_ASSET_DIR}" "${backup_remote}"
echo "Day 1 original opening/audio restored and independently backed up: PASS"
