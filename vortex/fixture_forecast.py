"""One WC/FH fixture model for Day 1, Day 2, Day 3 and WC/FH.

The model was vendored from FPL-VORTEX-AGENT commit
31e088378736a0f622eb51e7da6b3e2ab18ba55b (the WC/FH notebook's pin).
Presentation, planning Gameweeks and player-selection policy belong to callers.
"""
from __future__ import annotations

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


def align_weekly_frame(frame, namespace):
    """Replace Phase 3 fixture math before Poisson, FDR and player consumers run.

    Keep the existing fixture window, row order, columns and uncertainty method.
    The shared model supplies component provenance as well as the exact lambdas.
    """
    boot = namespace.get("data", {}).get("bootstrap")
    if boot is None:
        boot = {key: records(namespace[value]) for key, value in
                (("teams", "teams"), ("events", "events"), ("elements", "players"))}
    rows = forecast_rows(boot, namespace["fixtures"])
    canonical = {int(row["fixture_id"]): row for row in rows}
    result = frame.copy()
    for index, old in frame.iterrows():
        fid = int(old["fixture_id"])
        row = canonical[fid]
        if tuple(int(old[k]) for k in ("home_team_id", "away_team_id", "gameweek")) != tuple(int(row[k]) for k in ("home_team_id", "away_team_id", "gameweek")):
            raise ValueError(f"Weekly fixture identity mismatch {fid}")
        for key, value in row.items():
            if key in result.columns:
                result.at[index, key] = value
        for side in ("home", "away"):
            scale = float(row[f"model_lambda_{side}"]) / float(old[f"model_lambda_{side}"])
            for bound in ("low", "high"):
                key = f"model_lambda_{side}_{bound}"
                if key in result.columns:
                    result.at[index, key] = float(old[key]) * scale
        for key in ("forecast_timestamp", "source_timestamp", "data_snapshot_timestamp"):
            if key in result.columns:
                result.at[index, key] = row["data_snapshot_timestamp"]
        if "source_name" in result.columns:
            result.at[index, "source_name"] = "VORTEX SHARED WC/FH FIXTURE MODEL"
    return result


def patch_weekly_source(source):
    anchor = "    fixture_goal_expectations_model = pd.DataFrame(_rows, columns=PHASE3_OUTPUT_FIELDS)"
    fdr_anchor = "    _rows = []\n    for _, _fx in fixture_probabilities_model_only.iterrows():"
    if source.count(fdr_anchor) == 1 and anchor not in source:
        return source.replace(fdr_anchor,
            "    from vortex.fixture_forecast_model import vx_phase4_attack_fdr, vx_phase4_defence_fdr\n" + fdr_anchor, 1)
    if source.count(anchor) != 1:
        raise ValueError("Weekly Phase 3 fixture contract changed")
    return source.replace(anchor, anchor + "\n    from vortex.fixture_forecast import align_weekly_frame\n    fixture_goal_expectations_model = align_weekly_frame(fixture_goal_expectations_model, globals())", 1)
