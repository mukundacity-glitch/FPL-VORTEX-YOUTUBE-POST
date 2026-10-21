"""Prevent publishing an analysis whose evidence or rendered files changed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from day3.live_evidence import EvidenceChangedError, PublicClient, collect, now_iso


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def save_render_contract(namespace: dict[str, Any]) -> None:
    context = namespace.get("DAY3_AVAILABILITY")
    if context is None or context.research is None:
        raise RuntimeError("A completed analysis needs current live evidence")
    root = Path(namespace["OUTPUT_ROOT"]).resolve()
    context.save_audit(root / "DATA")
    artifacts = {str(path.relative_to(root)): file_digest(path)
                 for directory in ("SLIDE", "MP3", "MP4", "DATA")
                 for path in sorted((root / directory).glob("*"))
                 if path.is_file() and path.suffix.lower() in {".mp4", ".mp3", ".png", ".txt"}}
    if not artifacts:
        raise RuntimeError("No generated analysis artifacts were available to validate")
    contract = {"version": 1, "rendered_at": now_iso(), "gameweek": context.gameweek,
                "core_fingerprint": context.research["core_fingerprint"],
                "news_fingerprint": context.research["news"]["fingerprint"], "artifacts": artifacts}
    (root / "DATA" / "analysis_render_contract.json").write_text(json.dumps(contract, indent=2))


def validate_publication(root: Path, *, client: PublicClient | None = None) -> dict:
    root = root.resolve()
    evidence_path = root / "DATA" / "live_analysis_evidence.json"
    contract_path = root / "DATA" / "analysis_render_contract.json"
    if not evidence_path.is_file() or not contract_path.is_file():
        raise RuntimeError("Publication requires an evidence-validated render; regenerate Day 3")
    evidence = json.loads(evidence_path.read_text())
    contract = json.loads(contract_path.read_text())
    if contract["core_fingerprint"] != evidence["core_fingerprint"] or contract["news_fingerprint"] != evidence["news"]["fingerprint"]:
        raise EvidenceChangedError("Render and evidence snapshots do not match")
    if not contract.get("artifacts"):
        raise RuntimeError("The analysis render has no artifact manifest")
    for name, expected in contract["artifacts"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path) != expected:
            raise EvidenceChangedError(f"Rendered artifact changed or is missing: {name}")
    fresh = collect(evidence["bootstrap"], evidence["fixtures"], int(evidence["gameweek"]), client=client, histories=False)
    if fresh["news"]["fingerprint"] != contract["news_fingerprint"]:
        raise EvidenceChangedError("New research changes the player evidence; regenerate narration and graphics")
    approval = {"verified_at": now_iso(), "gameweek": evidence["gameweek"],
                "core_fingerprint": fresh["core_fingerprint"], "news_fingerprint": fresh["news"]["fingerprint"],
                "research_coverage": fresh["news"]["coverage"]}
    (root / "DATA" / "analysis_publication_check.json").write_text(json.dumps(approval, indent=2))
    return approval
