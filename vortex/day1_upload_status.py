"""Day 1 upload receipt gate: a green workflow must mean a PRIVATE YouTube video."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

DEFAULT_RECEIPT = Path(
    "/content/drive/MyDrive/FPL_VORTEX/FIRST VIDEO/DATA/youtube_private_upload.json"
)


def validated_private_receipt(receipt_path: Path) -> dict[str, Any]:
    if not receipt_path.is_file() or receipt_path.stat().st_size == 0:
        raise RuntimeError(f"YouTube private-upload receipt is missing: {receipt_path}")
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("YouTube private-upload receipt must be a JSON object")
    status = str(payload.get("status") or "")
    if status not in {"private_upload_complete", "already_uploaded"}:
        raise RuntimeError(f"Day 1 private YouTube upload did not complete: {status or 'no status'}")
    youtube = payload.get("youtube")
    if not isinstance(youtube, dict):
        raise RuntimeError("YouTube private-upload receipt has no video details")
    privacy = str(youtube.get("privacy_status") or "").lower()
    if privacy != "private":
        raise RuntimeError(
            f"Day 1 upload is NOT a private draft (reported visibility: {privacy or 'unknown'}); "
            "do not mark this workflow as a successful private upload"
        )
    video_id = str(youtube.get("video_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise RuntimeError("YouTube private-upload receipt has an invalid video ID")
    return {
        "status": status,
        "video_id": video_id,
        "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
        "watch_url": f"https://www.youtube.com/watch?v={video_id}",
        "privacy_status": "private",
    }


def main() -> None:
    receipt_path = Path(os.environ.get("DAY1_YOUTUBE_RECEIPT") or DEFAULT_RECEIPT)
    result = validated_private_receipt(receipt_path)
    outcome = (
        "New private upload completed"
        if result["status"] == "private_upload_complete"
        else "Previously uploaded private draft reused"
    )
    print(f"[YOUTUBE] Day 1 draft: {outcome}")
    print(f"[YOUTUBE] Privacy: PRIVATE")
    print(f"[YOUTUBE] Studio: {result['studio_url']}")
    summary_path = (os.environ.get("GITHUB_STEP_SUMMARY") or "").strip()
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as summary:
            summary.write(
                "## Day 1 — YouTube private video\n\n"
                f"- **Result:** {outcome}\n"
                "- **Visibility:** Private (never automatically Public)\n"
                f"- **Review in YouTube Studio:** {result['studio_url']}\n"
                f"- **Video ID:** `{result['video_id']}`\n\n"
                "The video stays Private until you manually publish it in YouTube Studio.\n"
            )


if __name__ == "__main__":
    main()
