"""Render again when a final evidence check changes the analysis inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from day3.live_evidence import EvidenceChangedError
from day3.publication_validation import validate_publication


def discard_rendered_artifacts(output_root: Path) -> None:
    contract = json.loads((output_root / "DATA" / "analysis_render_contract.json").read_text())
    root = output_root.resolve()
    for name in contract["artifacts"]:
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise RuntimeError("Invalid generated artifact path")
        path.unlink(missing_ok=True)


def run_validated(notebook: Path, output_root: Path, *, attempts: int = 2) -> None:
    for attempt in range(attempts):
        try:
            subprocess.run([sys.executable, "-m", "day3.run_notebook", str(notebook)], check=True)
        except subprocess.CalledProcessError as error:
            if error.returncode == 75 and attempt + 1 < attempts:
                print("Official evidence changed during input collection; restarting from fresh data.", flush=True)
                continue
            raise
        try:
            validate_publication(output_root)
            return
        except EvidenceChangedError:
            if attempt + 1 >= attempts:
                raise
            print("Live evidence changed after rendering; rebuilding recommendations, narration and graphics.", flush=True)
            discard_rendered_artifacts(output_root)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("notebook", type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    run_validated(args.notebook.resolve(), args.output_root.resolve())


if __name__ == "__main__":
    main()
