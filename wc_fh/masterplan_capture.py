from __future__ import annotations

import ast
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

VERSION = "wc-masterplan-pinned-capture-v1"
PATCH_VARIABLE = "_VX_REMOTION_RENDER_SAFE_PATCH"
FRAME_BYTES = 128 * 16 * 3


def masterplan_browser_arguments(project: Path, cli: str) -> list[str]:
    project = Path(project).resolve()
    # Full Playwright Chrome can silently tile compositor surfaces during parallel extraction.
    subprocess.run([cli, "browser", "ensure", "--chrome-mode=headless-shell"], cwd=project, check=True)
    binaries = sorted((project / "node_modules/.remotion/chrome-headless-shell").glob("**/chrome-headless-shell"))
    binaries = [path for path in binaries if path.is_file()]
    if len(binaries) != 1:
        raise RuntimeError("Wildcard masterplan requires exactly one Remotion-provisioned Chrome Headless Shell")
    return [f"--browser-executable={binaries[0]}", "--chrome-mode=headless-shell"]


def heading_fraction(frame: bytes) -> float:
    if len(frame) != FRAME_BYTES:
        raise ValueError("Incomplete masterplan capture QA frame")
    pixels = np.frombuffer(frame, dtype=np.uint8).reshape(-1, 3).astype(np.float32)
    red, green, blue = pixels.T
    return float(np.mean((red > 120) & (green > 85) & (red > blue * 1.2) & (green > blue * 1.08)))


def verify_masterplan_capture(video: Path, duration: float, fps: int) -> dict:
    video = Path(video)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for masterplan capture QA")
    command = [ffmpeg, "-v", "error", "-i", str(video), "-map", "0:v:0", "-an",
               "-vf", "scale=320:180,crop=128:16:71:2", "-fps_mode", "passthrough",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
    frames = 0
    minimum = 1.0
    with tempfile.TemporaryFile() as errors, subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors) as process:
        try:
            assert process.stdout is not None
            while frame := process.stdout.read(FRAME_BYTES):
                score = heading_fraction(frame)
                minimum = min(minimum, score)
                if score < 0.15:
                    raise ValueError(f"Wildcard masterplan capture lost its persistent heading at frame {frames} ({frames / fps:.3f}s)")
                frames += 1
            if process.wait():
                errors.seek(0)
                raise RuntimeError("Masterplan capture decode failed: " + errors.read().decode(errors="replace")[-2000:])
        except BaseException:
            process.kill()
            process.wait()
            raise
    if abs(frames - math.ceil(duration * fps)) > 1 or frames == 0:
        raise ValueError(f"Masterplan capture frame count differs from measured narration: {frames}")
    report = dict(version=VERSION, frames_checked=frames, minimum_heading_fraction=minimum, verified=True)
    video.with_suffix(".capture_qa.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wildcard masterplan: {frames} consecutive frames passed capture QA", flush=True)
    return report


def replace_masterplan_runtime(source: str, runtime: str) -> str:
    names = {"_vx_masterplan_safe_render_video", "_vx_masterplan_safe_frame"}
    replacements = {node.name: ast.get_source_segment(runtime, node) for node in ast.parse(runtime).body
                    if isinstance(node, ast.FunctionDef) and node.name in names}
    originals = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name in names]
    if set(replacements) != names or {node.name for node in originals} != names or len(originals) != 2:
        raise ValueError("Notebook embedded masterplan runtime contract changed")
    lines = source.splitlines(keepends=True)
    for node in sorted(originals, key=lambda item: item.lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = [replacements[node.name] + "\n"]
    # The notebook already embeds its old safe functions, so patch that source before its reload.
    updated = "".join(lines) + "\nfrom wc_fh.masterplan_capture import masterplan_browser_arguments, verify_masterplan_capture\n"
    compile(updated, "masterplan-capture-module", "exec")
    return updated


def patch_masterplan_capture(source: str) -> str:
    nodes = [node for node in ast.parse(source).body if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == PATCH_VARIABLE for target in node.targets)]
    if len(nodes) != 1 or not isinstance(nodes[0].value, ast.Constant) or not isinstance(nodes[0].value.value, str):
        raise ValueError("Notebook masterplan capture contract changed")
    node = nodes[0]
    versions = [item for item in ast.parse(source).body if isinstance(item, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "VX_RENDERER_VERSION" for target in item.targets)]
    if len(versions) != 1 or not isinstance(versions[0].value, ast.Constant) or not isinstance(versions[0].value.value, str):
        raise ValueError("Notebook masterplan renderer version contract changed")
    runtime = node.value.value
    changes = {
        "browser = _vx_remotion_browser_arguments(self.project)": "browser = masterplan_browser_arguments(self.project, cli)",
        "*_vx_remotion_browser_arguments(self.project)": "*masterplan_browser_arguments(self.project, cli)",
        "    return target\n": "    verify_masterplan_capture(target, duration, int(profile['fps']))\n    return target\n",
    }
    for before, after in changes.items():
        if runtime.count(before) != 1:
            raise ValueError("Notebook masterplan capture contract changed: " + before.strip())
        runtime = runtime.replace(before, after, 1)
    runtime += "\nfrom wc_fh.masterplan_capture import masterplan_browser_arguments, verify_masterplan_capture\n"
    compile(runtime, "masterplan-capture-runtime", "exec")
    lines = source.splitlines(keepends=True)
    version = versions[0]
    installation = (f"{PATCH_VARIABLE} = {runtime!r}\n"
                    "from wc_fh.masterplan_capture import replace_masterplan_runtime\n"
                    "_VX_MASTERPLAN_SOURCE = replace_masterplan_runtime(_VX_MASTERPLAN_SOURCE, _VX_REMOTION_RENDER_SAFE_PATCH)\n")
    edits = [(node.lineno - 1, node.end_lineno, installation),
             (version.lineno - 1, version.end_lineno, f"VX_RENDERER_VERSION = {version.value.value + ':' + VERSION!r}\n")]
    for first, last, replacement in sorted(edits, reverse=True):
        lines[first:last] = [replacement]
    return "".join(lines)
