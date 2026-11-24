"""Source compatibility for the checksum-verified forecast model.

These are club aliases, never fuzzy matches. Fixture kickoff, home/away, score,
uniqueness and red-card-count checks remain in the pinned upstream model.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
from functools import wraps
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType


TEAM_ALIASES = {
    "afc bournemouth": "bournemouth",
    "brighton hove albion": "brighton and hove albion",
    "sunderland afc": "sunderland",
    "ipswich": "ipswich town",
    "leicester": "leicester city",
}
CORE_REPOSITORY = "https://github.com/olbauday/FPL-Core-Insights.git"
CORE_TREE_URL = "https://api.github.com/repos/olbauday/FPL-Core-Insights/git/trees/main?recursive=1"


def install_team_aliases(model: ModuleType) -> None:
    """Apply the same canonical names to CSVs, FPL, ESPN events and rosters."""
    original = getattr(model, "_vx_norm_team_name", None)
    if not callable(original):
        raise ValueError("Pinned forecast team-name contract changed")
    if getattr(original, "_wc_fh_team_aliases", False):
        return

    @wraps(original)
    def normalize(value):
        name = original(value)
        return original(TEAM_ALIASES.get(name, name))

    normalize._wc_fh_team_aliases = True
    model._vx_norm_team_name = normalize


def fetch_core_git_tree() -> dict:
    """Read the current public branch's object IDs without downloading file contents."""
    with TemporaryDirectory(prefix="wc-fh-core-") as directory:
        checkout = Path(directory) / "source"
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
        subprocess.run(
            ["git", "-c", "credential.helper=", "clone", "--depth=1", "--filter=blob:none",
             "--no-checkout", "--single-branch", "--no-tags", "--branch=main", CORE_REPOSITORY, str(checkout)],
            cwd=directory, env=env, check=True, capture_output=True, timeout=60,
        )
        sha = subprocess.check_output(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"], cwd=checkout, text=True, timeout=10,
        ).strip()
        listing = subprocess.check_output(
            ["git", "ls-tree", "-rz", sha, "--", "data/"], cwd=checkout, text=True, encoding="utf-8", timeout=15,
        )

    tree = []
    for entry in listing.rstrip("\0").split("\0") if listing else []:
        metadata, path = entry.split("\t", 1)
        _, object_type, object_sha = metadata.split()
        if object_type == "blob":
            tree.append({"path": path, "type": object_type, "sha": object_sha})
    if not tree:
        raise RuntimeError("The current FPL-Core main branch has no data files")
    return {"sha": sha, "tree": tree, "truncated": False}


class ForecastSourceClient:
    def __init__(self, client):
        self.client = client

    def get(self, url, **options):
        if url != CORE_TREE_URL:
            return self.client.get(url, **options)
        try:
            result = self.client.get(url, **options)
            if isinstance(result, dict):
                sha, tree = result.get("sha"), result.get("tree")
                if (isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha)
                        and isinstance(tree, list) and tree and not result.get("truncated")):
                    return result
            rest_error = "GitHub REST returned an incomplete tree"
        except RuntimeError as error:
            rest_error = str(error)

        try:
            result = fetch_core_git_tree()
        except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as error:
            raise RuntimeError(f"Current FPL-Core listing unavailable via REST ({rest_error}) or Git ({error})") from error
        print(f"WC-FH: FPL-Core REST listing unavailable. Using verified Git tree at {result['sha']}.", flush=True)
        return result


def install_forecast_source(model: ModuleType) -> None:
    original = getattr(model, "refresh_fpl_core", None)
    if not callable(original):
        raise ValueError("Pinned forecast source client contract changed")
    if getattr(original, "_wc_fh_source_client", False):
        return

    @wraps(original)
    def refresh(boot, official_fixtures, input_root, now, client):
        return original(boot, official_fixtures, input_root, now, ForecastSourceClient(client))

    refresh._wc_fh_source_client = True
    model.refresh_fpl_core = refresh


def patch_forecast_loader(source: str) -> str:
    """Install compatibility after the notebook verifies and imports its model."""
    imports = [node for node in ast.parse(source).body
               if isinstance(node, ast.Import)
               and any(alias.name == "vortex_upstream_fdr" and alias.asname is None
                       for alias in node.names)]
    if len(imports) != 1:
        raise ValueError("Pinned forecast loader contract changed; expected one model import")
    lines = source.splitlines(keepends=True)
    position = imports[0].end_lineno
    lines[position:position] = [
        "\nfrom wc_fh.forecast_compat import (\n"
        "    install_forecast_source as _wc_fh_install_forecast_source,\n"
        "    install_team_aliases as _wc_fh_install_team_aliases,\n"
        ")\n"
        "_wc_fh_install_team_aliases(vortex_upstream_fdr)\n"
        "_wc_fh_install_forecast_source(vortex_upstream_fdr)\n"
    ]
    return "".join(lines)
