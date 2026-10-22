"""Exact provider-name compatibility for the checksum-verified forecast model.

These are club aliases, never fuzzy matches. Fixture kickoff, home/away, score,
uniqueness and red-card-count checks remain in the pinned upstream model.
"""
from __future__ import annotations

import ast
from functools import wraps
from types import ModuleType


TEAM_ALIASES = {
    "afc bournemouth": "bournemouth",
    "brighton hove albion": "brighton and hove albion",
    "sunderland afc": "sunderland",
    "ipswich": "ipswich town",
    "leicester": "leicester city",
}


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
        "\nfrom wc_fh.forecast_compat import install_team_aliases as _wc_fh_install_team_aliases\n"
        "_wc_fh_install_team_aliases(vortex_upstream_fdr)\n"
    ]
    return "".join(lines)
