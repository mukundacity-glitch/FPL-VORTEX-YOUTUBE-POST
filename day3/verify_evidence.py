from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

from day3.live_evidence import VERSION, assert_snapshot_current, digest, get_json, save_snapshot


def file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def finalize_evidence_bundle(namespace: dict[str, Any]) -> None:
    snapshot = namespace["DAY3_EVIDENCE"]
    output_root = Path(namespace["OUTPUT_ROOT"])
    directory = output_root / "DATA"
    exports = namespace["vx_export_narration_scripts"](available_only=False)
    scripts = {Path(filename).name: Path(filename).read_text(encoding="utf-8") for filename in exports}
    if not scripts or any(not text.strip() for text in scripts.values()):
        raise RuntimeError("A selected scene lacks a newly generated narration export")
    videos = list((output_root / "MP4").glob("*COMBINED*.mp4"))
    if len(videos) != 1:
        raise RuntimeError("Exactly one assembled video is required to seal current evidence")
    save_snapshot(snapshot, directory)
    payload = {
        "version": VERSION, "cutoff": snapshot["cutoff"], "next_gw": snapshot["next_gw"],
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "source_hash": snapshot["source_hash"], "scripts": scripts, "scripts_hash": digest(scripts),
        "video": videos[0].name, "video_sha256": file_hash(videos[0]),
    }
    (directory / "day3_script_evidence.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (directory / "Day3_Complete_Narration.txt").write_text(
        "\n\n".join(filename + "\n" + text for filename, text in scripts.items()), encoding="utf-8")
    print(f"Sealed {len(scripts)} regenerated scene scripts and final video against {snapshot['source_hash'][:12]}")


def verify_bundle(output_root: Path, loader: Callable[[str], Any] = get_json) -> None:
    folder = output_root / "DATA"
    snapshot = json.loads((folder / "day3_live_evidence.json").read_text(encoding="utf-8"))
    evidence = json.loads((folder / "day3_script_evidence.json").read_text(encoding="utf-8"))
    if evidence.get("version") != VERSION or snapshot.get("version") != VERSION:
        raise RuntimeError("Old narration implementation cannot pass the evidence gate")
    if evidence["run_id"] != os.environ.get("GITHUB_RUN_ID", "local"):
        raise RuntimeError("Narration belongs to a different workflow run")
    if evidence["source_hash"] != snapshot["source_hash"] or evidence["next_gw"] != snapshot["next_gw"]:
        raise RuntimeError("Narration and source snapshot disagree")
    if digest(evidence["scripts"]) != evidence["scripts_hash"]:
        raise RuntimeError("Narration evidence manifest was changed")
    for filename, script in evidence["scripts"].items():
        if Path(filename).name != filename or not filename.endswith(".txt"):
            raise RuntimeError("Invalid narration export path")
        if (folder / filename).read_text(encoding="utf-8") != script:
            raise RuntimeError("A narration export changed after the video was assembled")
    filename = evidence["video"]
    if Path(filename).name != filename or not filename.endswith(".mp4"):
        raise RuntimeError("Invalid final video path")
    if file_hash(output_root / "MP4" / filename) != evidence["video_sha256"]:
        raise RuntimeError("Final video does not match the sealed narration run")
    assert_snapshot_current(snapshot, loader)
    print("Day 3 upload evidence verified: current sources, matching scripts, matching final video")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reject stale or mismatched Day 3 narration before upload")
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    verify_bundle(arguments.output_root.resolve())


if __name__ == "__main__":
    main()
