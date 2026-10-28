"""One WC/FH fixture model for Day 1, Day 2, Day 3 and WC/FH.

The model was vendored from FPL-VORTEX-AGENT commit
31e088378736a0f622eb51e7da6b3e2ab18ba55b (the WC/FH notebook's pin).
Presentation, planning Gameweeks and player-selection policy belong to callers.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from . import fixture_forecast_model as model
from wc_fh.forecast_compat import install_team_aliases

install_team_aliases(model)


def input_root():
    return Path(os.environ.get("VORTEX_FIXTURE_INPUT_ROOT",
        "/content/drive/MyDrive/FPL_VORTEX/MODEL_INPUTS/canonical_fixtures"))


class SourceClient:
    """WC/FH's one-hour source cache; expired evidence never substitutes for live."""
    def __init__(self, directory, now):
        self.directory, self.now = Path(directory), now
        self.directory.mkdir(parents=True, exist_ok=True)

    def get(self, url, required=False, hours=1, timeout=12):
        path = self.directory / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")
        try:
            cached = json.loads(path.read_text())
            stamp = datetime.fromisoformat(cached["fetched_at"].replace("Z", "+00:00"))
            if 0 <= (self.now - stamp).total_seconds() <= hours * 3600:
                return cached["data"]
        except (OSError, ValueError, TypeError, KeyError):
            pass
        error = None
        for _ in range(2):
            try:
                response = requests.get(url, timeout=timeout,
                    headers={"User-Agent": "FPL-Vortex/2.0 (analytics)"})
                response.raise_for_status()
                data = response.json()
                path.write_text(json.dumps({"fetched_at": self.now.isoformat(), "data": data}))
                return data
            except (requests.RequestException, ValueError) as exc:
                error = exc
        if required:
            raise RuntimeError(f"Required current fixture source unavailable: {url}") from error
        return None


def records(value):
    # FPL's weekly loader stores timestamps/nullable fields in DataFrames.
    return json.loads(value.to_json(orient="records", date_format="iso")) if isinstance(value, pd.DataFrame) else value


def forecast_rows(boot, fixtures, now=None, root=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Forecast time must have a timezone")
    root = Path(root) if root is not None else input_root()
    root.mkdir(parents=True, exist_ok=True)
    fixtures = records(fixtures)
    archive = model.refresh_fpl_core(boot, fixtures, root, now, SourceClient(root / "current_source_cache", now))
    rows = model.rebuild(boot, fixtures, archive, root, now)
    validate_rows(rows, fixtures)
    (root / "fixture_forecast.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return rows


def validate_rows(rows, fixtures):
    expected = {int(f["id"]): f for f in fixtures if not f.get("finished") and f.get("event") is not None}
    found = set()
    for row in rows:
        fid = int(row["fixture_id"])
        if fid in found or fid not in expected:
            raise ValueError(f"Duplicate or unexpected canonical fixture {fid}")
        found.add(fid)
        fixture = expected[fid]
        if tuple(int(row[k]) for k in ("home_team_id", "away_team_id", "gameweek")) != tuple(int(fixture[k]) for k in ("team_h", "team_a", "event")):
            raise ValueError(f"Canonical fixture identity mismatch {fid}")
        for side, opponent in (("home", "away"), ("away", "home")):
            lam = float(row[f"model_lambda_{side}"])
            cs = float(row[f"{side}_clean_sheet_probability"])
            if not math.isfinite(lam) or lam <= 0 or not math.isfinite(cs) or not math.isclose(cs, math.exp(-float(row[f"model_lambda_{opponent}"])), abs_tol=1e-12):
                raise ValueError(f"Invalid canonical goals/clean sheet for fixture {fid}")
    if found != expected.keys():
        raise ValueError("Canonical fixture coverage is incomplete")


def fixture_values(rows, fixture_id, team_id, position="MID"):
    row = next(r for r in rows if int(r["fixture_id"]) == int(fixture_id))
    if int(team_id) not in (int(row["home_team_id"]), int(row["away_team_id"])):
        raise ValueError("Team does not belong to canonical fixture")
    side = "home" if int(row["home_team_id"]) == int(team_id) else "away"
    goals = float(row[f"model_lambda_{side}"])
    cs = float(row[f"{side}_clean_sheet_probability"])
    return {"fdr": model.vx_phase4_defence_fdr(cs) if position in ("GK", "GKP", "DEF") else model.vx_phase4_attack_fdr(goals),
            "projected_goals": goals, "clean_sheet_probability": cs}


def build_weekly_frame(namespace):
    """Build the existing weekly schema directly from WC/FH fixture evidence.

    The legacy goal predictor is not executed. Keep the caller's Gameweek window,
    row order, columns and established structural-uncertainty method.
    """
    boot = namespace.get("data", {}).get("bootstrap")
    if boot is None:
        boot = {key: records(namespace[value]) for key, value in
                (("teams", "teams"), ("events", "events"), ("elements", "players"))}
    rows = forecast_rows(boot, namespace["fixtures"])
    canonical = {int(row["fixture_id"]): row for row in rows}
    context = namespace["fixture_context_phase2"]
    if context["fixture_id"].duplicated().any():
        raise ValueError("Weekly fixture window contains duplicate fixture IDs")
    state = namespace["team_strength_updated"].set_index("team_id")
    priors = namespace["team_priors"].set_index("team_id")
    if state.index.duplicated().any() or priors.index.duplicated().any():
        raise ValueError("Weekly uncertainty state contains duplicate teams")
    output = []
    for _, fixture in context.iterrows():
        fid = int(fixture["fixture_id"])
        row = dict(canonical[fid])
        if tuple(int(fixture[k]) for k in ("home_team_id", "away_team_id", "gameweek")) != tuple(int(row[k]) for k in ("home_team_id", "away_team_id", "gameweek")):
            raise ValueError(f"Weekly fixture identity mismatch {fid}")
        home_u = namespace["_vx_phase3_team_uncertainty"](row["home_team_id"], state, priors)
        away_u = namespace["_vx_phase3_team_uncertainty"](row["away_team_id"], state, priors)
        uncertainty = math.sqrt(home_u ** 2 + away_u ** 2)
        for side in ("home", "away"):
            low, high = namespace["_vx_phase3_lambda_range"](row[f"model_lambda_{side}"], uncertainty)
            row[f"model_lambda_{side}_low"] = low
            row[f"model_lambda_{side}_high"] = high
            row[f"{side}_lambda_uncertainty"] = uncertainty
        for key in ("forecast_timestamp", "source_timestamp", "data_snapshot_timestamp"):
            row[key] = row["data_snapshot_timestamp"]
        row.update(model_confidence=math.exp(-uncertainty),
            uncertainty_status="PREVALIDATION_STRUCTURAL_RANGE_NOT_COVERAGE",
            model_version=namespace["model_version"], source_name="VORTEX SHARED WC/FH FIXTURE MODEL",
            is_pre_deadline_data=namespace["_phase0_is_pre_deadline"](row["gameweek"]))
        output.append(row)
    namespace["VORTEX_FIXTURE_BY_ID"] = canonical
    return pd.DataFrame(output, columns=namespace["PHASE3_OUTPUT_FIELDS"])


def weekly_clean_sheets(namespace, fixture_id, lambda_home, lambda_away):
    """Read CS from the same fixture record as projected goals and FDR."""
    row = namespace["VORTEX_FIXTURE_BY_ID"][int(fixture_id)]
    if (float(row["model_lambda_home"]), float(row["model_lambda_away"])) != (float(lambda_home), float(lambda_away)):
        raise ValueError(f"Weekly goal/clean-sheet snapshot drift for fixture {fixture_id}")
    return float(row["home_clean_sheet_probability"]), float(row["away_clean_sheet_probability"])


def patch_weekly_source(source):
    anchor = "    fixture_goal_expectations_model = pd.DataFrame(_rows, columns=PHASE3_OUTPUT_FIELDS)"
    if source.count(anchor) == 1:
        start = source.index("    _required_strength = {\n")
        stop = source.index(anchor, start) + len(anchor)
        source = source[:start] + ("    from vortex.fixture_forecast import build_weekly_frame\n"
            "    fixture_goal_expectations_model = build_weekly_frame(globals())") + source[stop:]
        old_log = '    print(f"   L_H={_L_H:.4f} | L_A={_L_A:.4f}")'
        if source.count(old_log) != 1:
            raise ValueError("Weekly Phase 3 output contract changed")
        return source.replace(old_log, '    print("   Fixture goals and components use the shared WC/FH model.")', 1)
    signature = "def _vx_phase4_closed_form_probabilities(lambda_home, lambda_away):"
    if source.count(signature) == 1:
        replacements = (
            (signature, "def _vx_phase4_closed_form_probabilities(lambda_home, lambda_away, fixture_id):"),
            ("    home_cs = p_a0\n    away_cs = p_h0", "    from vortex.fixture_forecast import weekly_clean_sheets\n"
             "    home_cs, away_cs = weekly_clean_sheets(globals(), fixture_id, lh, la)"),
            ("_closed = _vx_phase4_closed_form_probabilities(_lh, _la)",
             "_closed = _vx_phase4_closed_form_probabilities(_lh, _la, _fid)"),
        )
        for before, after in replacements:
            if source.count(before) != 1:
                raise ValueError("Weekly clean-sheet contract changed")
            source = source.replace(before, after, 1)
        return source
    names = {"_vx_phase4_clip_fdr", "vx_phase4_attack_fdr", "vx_phase4_defence_fdr"}
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name in names]
    if len(nodes) != 3 or {n.name for n in nodes} != names:
        raise ValueError("Weekly forecast/FDR source contract changed")
    lines = source.splitlines(keepends=True)
    for node in sorted(nodes, key=lambda n: n.lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = [] if node != nodes[0] else [
            "from vortex.fixture_forecast_model import _vx_phase4_clip_fdr, vx_phase4_attack_fdr, vx_phase4_defence_fdr\n"]
    return "".join(lines)
