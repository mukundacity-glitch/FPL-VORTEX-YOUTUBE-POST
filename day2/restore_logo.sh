#!/usr/bin/env bash
# Recover Day 2's logo locally from the approved opening, preserving shared files.
set -euo pipefail

: "${DAY2_ASSET_DIR:?DAY2_ASSET_DIR must be set}"
logo="${DAY2_ASSET_DIR}/logo1.png"

valid_image() {
  [[ -s "$1" ]] && ffmpeg -hide_banner -loglevel error -xerror \
    -i "$1" -frames:v 1 -f null - >/dev/null 2>&1
}

if valid_image "$logo"; then
  echo "[DAY 2] Existing approved logo preserved: $logo"
  exit 0
fi

mkdir -p "$DAY2_ASSET_DIR"
candidate="$(mktemp "${DAY2_ASSET_DIR}/.day2-logo-XXXXXX.png")"
trap 'rm -f "$candidate"' EXIT

# Reuse the established crop of the original crest at six seconds. A temporary
# target prevents an invalid existing file from passing a codec-name-only check.
DAY1_ASSET_DIR="$DAY2_ASSET_DIR" DAY1_LOGO_FILE="$candidate" \
  bash "$(dirname "${BASH_SOURCE[0]}")/../scripts/restore_day1_logo.sh"
if ! valid_image "$candidate"; then
  echo "[DAY 2] Recovered logo could not be decoded" >&2
  exit 1
fi
mv "$candidate" "$logo"
echo "[DAY 2] Original crest recovered and validated: $logo"
