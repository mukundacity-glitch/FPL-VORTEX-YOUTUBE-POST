from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from day3.live_evidence import VERSION, SourceChanged, assert_snapshot_current, digest, get_json, save_snapshot


RENDER_WORK_ROOT = Path("/content/FPL_VORTEX_DAY3_WORK")


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


def verify_bundle(
    output_root: Path, loader: Callable[[str], Any] = get_json, *, expected_target: tuple[int, str] | None = None,
) -> None:
    folder = output_root / "DATA"
    snapshot = json.loads((folder / "day3_live_evidence.json").read_text(encoding="utf-8"))
    evidence = json.loads((folder / "day3_script_evidence.json").read_text(encoding="utf-8"))
    if evidence.get("version") != VERSION or snapshot.get("version") != VERSION:
        raise RuntimeError("Old narration implementation cannot pass the evidence gate")
    if evidence["run_id"] != os.environ.get("GITHUB_RUN_ID", "local"):
        raise RuntimeError("Narration belongs to a different workflow run")
    if evidence["source_hash"] != snapshot["source_hash"] or evidence["next_gw"] != snapshot["next_gw"]:
        raise RuntimeError("Narration and source snapshot disagree")
    if expected_target and (snapshot["next_gw"], snapshot["deadline"]) != expected_target:
        raise RuntimeError("Regenerated Day 3 video belongs to a different planning Gameweek or deadline")
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


def prepare_output(output_root: Path) -> None:
    expected = Path("/content/drive/MyDrive/FPL_VORTEX/Day_3_3")
    if output_root.absolute() != expected or output_root.resolve() != expected:
        raise RuntimeError(f"Unsafe Day 3 output path: {output_root}")
    for name in ("MP4", "MP3", "SLIDE", "DATA"):
        folder = output_root / name
        if folder.is_symlink():
            raise RuntimeError(f"Unsafe Day 3 output directory symlink: {folder}")
        folder.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryFile(dir=folder):
                pass
        except OSError as error:
            raise RuntimeError(f"Day 3 output directory is not writable: {folder}") from error
        for child in folder.iterdir():
            if child.is_symlink() or not child.is_dir():
                child.unlink()
            else:
                shutil.rmtree(child)


def verify_with_recovery(output_root: Path, rerender: Callable[[], None]) -> None:
    try:
        verify_bundle(output_root)
    except SourceChanged as changed:
        print(f"[DAY 3] {changed}. Regenerating GW{changed.target[0]} once from a fresh snapshot.", flush=True)
        rerender()
        verify_bundle(output_root, expected_target=changed.target)



def main() -> None:
    parser = argparse.ArgumentParser(description="Reject stale or mismatched Day 3 narration before upload")
    parser.add_argument("--output-root", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare-output", action="store_true")
    mode.add_argument("--rerender-notebook", type=Path)
    arguments = parser.parse_args()
    if arguments.prepare_output:
        prepare_output(arguments.output_root)
        print("Previous Day 3 render outputs cleared")
    elif arguments.rerender_notebook:
        notebook = arguments.rerender_notebook.resolve()

        def rerender() -> None:
            if not notebook.is_file():
                raise FileNotFoundError(notebook)
            if RENDER_WORK_ROOT.resolve() != RENDER_WORK_ROOT:
                raise RuntimeError(f"Unsafe Day 3 render work directory: {RENDER_WORK_ROOT}")
            prepare_output(arguments.output_root)
            if RENDER_WORK_ROOT.exists():
                shutil.rmtree(RENDER_WORK_ROOT)
            subprocess.run([sys.executable, "-m", "day3.run_notebook", str(notebook)], check=True)

        verify_with_recovery(arguments.output_root, rerender)
    else:
        verify_bundle(arguments.output_root.resolve())


if __name__ == "__main__":
    main()
