from __future__ import annotations

import ast
import copy
from datetime import datetime, timedelta, timezone
import re
from random import Random
import textwrap
import unittest

import pandas as pd

from day3.player_availability import AvailabilityContext
from day3.projected_goals_narration import patch_projected_goals_narration_source, projected_goals_narration


# Archived run-120 numbers are regression input only, never production defaults.
HISTORICAL_TEAMS = [
    ("Manchester United", 2.43, 21.6), ("Arsenal", 1.87, 45.6),
    ("Manchester City", 1.73, 27), ("Liverpool", 1.61, 23.9),
    ("Chelsea", 1.55, 30.9), ("Bournemouth", 1.53, 8.8),
    ("Crystal Palace", 1.47, 31), ("Brighton", 1.43, 20),
    ("Ipswich", 1.37, 29.5), ("Fulham", 1.35, 26.7),
    ("Brentford", 1.33, 27.3), ("Coventry", 1.32, 25.9),
    ("Aston Villa", 1.31, 17.6), ("Hull", 1.30, 26.6),
    ("Sunderland", 1.27, 31.7), ("Nottingham Forest", 1.22, 25.5),
    ("Spurs", 1.17, 21.2), ("Newcastle", 1.17, 23),
    ("Leeds", 1.15, 28), ("Everton", .79, 15.4),
]
MATCHES = [(1, 6), (2, 20), (13, 3), (4, 8), (5, 17),
           (7, 18), (9, 16), (12, 10), (14, 11), (15, 19)]


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


class ProjectionNarrationTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"gameweek": 8, "teams": {
            index: {"name": name, "projected_goals": goals, "clean_sheet_pct": cs}
            for index, (name, goals, cs) in enumerate(HISTORICAL_TEAMS, 1)
        }}
        self.refresh()
        # The archived board placed Newcastle first within the displayed 1.17 tie.
        self.payload["bottom3_goals"][-1] = {"team_id": 18}
        self.namespace = {
            "PROJECTED_GOALS_PAYLOAD": self.payload,
            "vx_narration_team": lambda tid: self.payload["teams"][tid]["name"],
        }

    def refresh(self):
        teams = self.payload["teams"]
        for key, metric, reverse, count in (
            ("top5_goals", "projected_goals", True, 5),
            ("bottom3_goals", "projected_goals", False, 3),
            ("top5_clean_sheet", "clean_sheet_pct", True, 5),
            ("bottom3_clean_sheet", "clean_sheet_pct", False, 3),
        ):
            self.payload[key] = [{"team_id": tid} for tid in sorted(
                teams, key=lambda tid: teams[tid][metric], reverse=reverse
            )[:count]]
        self.payload["fixtures"] = [{
            "fixture_id": index, "home_team_id": home, "away_team_id": away,
            "home_goals": teams[home]["projected_goals"], "away_goals": teams[away]["projected_goals"],
            "home_cs_pct": teams[home]["clean_sheet_pct"], "away_cs_pct": teams[away]["clean_sheet_pct"],
        } for index, (home, away) in enumerate(MATCHES, 1)]

    def assert_cues(self, text, cues):
        tokens = norm(text).split()
        anchors = [cues["opening"]]
        for section in cues["sections"]:
            anchors += [section["intro"]] + [row["anchor"] for row in section["rows"]]
            self.assertEqual([r["team_id"] for r in section["rows"]],
                             [r["team_id"] for r in self.payload[section["bucket"]]])
        anchors.append(cues["closing"])
        starts = []
        for anchor in anchors:
            target = norm(anchor).split()
            matches = [i for i in range(len(tokens)) if tokens[i:i + len(target)] == target]
            self.assertEqual(len(matches), 1, anchor)
            starts.append(matches[0])
        self.assertEqual(starts, sorted(set(starts)))

    def test_requested_paragraphs_use_archived_board_values_and_exact_cues(self):
        original = copy.deepcopy(self.payload)
        text, cues = projected_goals_narration(self.namespace)
        for phrase in (
            "Gameweek 8, starting with attacking potential.",
            "Manchester United lead the model with 2.43 expected goals against Bournemouth.",
            "Bournemouth's clean-sheet probability at 8.8 percent",
            "Arsenal follow at 1.87 against Everton",
            "Manchester City sit at 1.73 away to Aston Villa",
            "all five opponents have clean-sheet probabilities of 21.2 percent or lower",
            "Everton project just 0.79 goals against Arsenal",
            "Arsenal are the clear leaders, with a 45.6 percent clean-sheet probability against Everton",
            "13.9 percentage points ahead of Sunderland, who sit second at 31.7 percent",
            "Crystal Palace follow closely at 31 percent",
            "Sunderland and Crystal Palace are separated by just 0.7 percentage points",
            "And that brings us neatly to our next section: defensive contribution.",
        ):
            self.assertIn(phrase, text)
        self.assertGreaterEqual(len(text.split("\n\n")), 11)
        self.assertEqual(original, self.payload)
        self.assert_cues(text, cues)

    def test_gameweek_teams_order_numbers_and_comparisons_all_change(self):
        self.payload["gameweek"] = 17
        for tid, row in self.payload["teams"].items():
            row["name"] = f"Example Club {tid}"
            row["projected_goals"] = tid / 4
            row["clean_sheet_pct"] = tid * 3
        self.refresh()
        text, cues = projected_goals_narration(self.namespace)
        for phrase in ("Gameweek 17", "Example Club 20 lead the model with 5.00", "3 percentage points ahead",
                       "clean-sheet probabilities of 45 percent or lower"):
            self.assertIn(phrase, text)
        for phrase in ("Manchester", "Gameweek 8", "2.43", "13.9", "narrow gap", "strong signal"):
            self.assertNotIn(phrase, text)
        self.assert_cues(text, cues)

    def test_ties_do_not_claim_exclusive_or_clear_lead(self):
        for row in self.payload["teams"].values():
            row["projected_goals"], row["clean_sheet_pct"] = 1.5, 30
        self.refresh()
        text, cues = projected_goals_narration(self.namespace)
        self.assertIn("share the lead with 1.50", text)
        self.assertIn("at the same 30 percent", text)
        self.assertNotIn("are the clear leaders", text)
        self.assertNotIn("0 percentage points ahead", text)
        self.assert_cues(text, cues)

    def test_double_gameweeks_use_fixture_odds_and_explain_aggregation(self):
        self.payload["fixtures"].append({"home_team_id": 1, "away_team_id": 20,
                                         "home_cs_pct": 70, "away_cs_pct": 35})
        text, cues = projected_goals_narration(self.namespace)
        self.assertIn("across fixtures against Bournemouth at home and Everton at home", text)
        self.assertIn("across those fixtures, opponents have", text)
        self.assertIn("goals are totaled across their fixtures", text)
        self.assertNotIn("all five opponents", text)
        self.assert_cues(text, cues)

    def test_attacking_and_defensive_rows_keep_distinct_cues_when_teams_overlap(self):
        rng = Random(8)
        for _ in range(100):
            for row in self.payload["teams"].values():
                row["projected_goals"] = rng.choice([.8, 1.2, 1.5, 1.8, 2.4])
                row["clean_sheet_pct"] = rng.choice([10, 20, 30, 40, 50])
            self.refresh()
            text, cues = projected_goals_narration(self.namespace)
            self.assert_cues(text, cues)

    def test_invalid_missing_and_stale_projection_data_fail_instead_of_inventing_facts(self):
        cases = [lambda p: p.pop("teams"),
                 lambda p: p["teams"][1].update(projected_goals=float("nan")),
                 lambda p: p["teams"][1].update(clean_sheet_pct=float("inf")),
                 lambda p: p["teams"][1].update(clean_sheet_pct=110),
                 lambda p: p["top5_goals"].reverse(),
                 lambda p: p["top5_clean_sheet"].pop(),
                 lambda p: p.update(fixtures=[])]
        for mutate in cases:
            with self.subTest(mutate=mutate):
                payload = copy.deepcopy(self.payload)
                mutate(payload)
                with self.assertRaises((RuntimeError, ValueError)):
                    projected_goals_narration(dict(self.namespace, PROJECTED_GOALS_PAYLOAD=payload))

    def players(self):
        now = datetime.now(timezone.utc)
        rows = []
        for pid, team, pos, score in ((501, 1, 3, 3), (502, 1, 4, 2), (503, 1, 3, 10),
                                      (504, 2, 2, 6), (505, 2, 2, 5), (506, 2, 1, 4),
                                      (507, 13, 2, 20), (508, 2, 2, 50)):
            rows.append({"id": pid, "code": pid + 1000, "team": team, "element_type": pos,
                         "web_name": f"Player {pid}", "status": "s" if pid == 503 else "a",
                         "chance_of_playing_this_round": 100})
        official = pd.DataFrame(rows)
        fixtures = pd.DataFrame([{"event": 8, "team_h": 1, "team_a": 2, "finished": False,
                                   "kickoff_time": (now + timedelta(days=2)).isoformat()}])
        context = AvailabilityContext({"events": [{"id": 8, "is_current": True}], "elements": rows},
                                      fixtures, 8, {"source": "LIVE_FPL_API", "fallback_used": False})
        context.bind_model(
            pd.DataFrame([{"player_id": r["id"], "start_probability": .95, "expected_minutes": 85} for r in rows]),
            pd.DataFrame([{"player_code": r["code"], "season_label": "test", "match_id": "last-prem-match",
                           "match_date": (now - timedelta(days=2)).isoformat(), "minutes_played": 90,
                           "is_starting": r["id"] != 508} for r in rows]), official, "test",
        )
        model = pd.DataFrame([{
            "player_id": pid, "team_id": team, "gameweek": 8, "calculation_status": "READY",
            "goal_points": score, "assist_points": 0, "fixture_expected_points": score,
        } for pid, team, pos, score in ((501, 1, 3, 3), (502, 1, 4, 2), (503, 1, 3, 10),
                                       (504, 2, 2, 6), (505, 2, 2, 5), (506, 2, 1, 4),
                                       (507, 2, 2, 20), (508, 2, 2, 50))])
        self.namespace.update(players=official, SLIDE_PLAYER_FIXTURE_XPTS=model,
                              DAY3_AVAILABILITY=context, vx_narration_player=lambda pid: f"Player {pid}")

    def test_player_mentions_use_forecasts_official_club_and_real_eligibility_gate(self):
        self.players()
        text, cues = projected_goals_narration(self.namespace)
        self.assertIn("Player 501 and Player 502 are threats", text)
        self.assertIn("From Arsenal, I'd consider Player 504, Player 505, and Player 506", text)
        for name in ("Player 503", "Player 507", "Player 508", "nailed", "Konsa"):
            self.assertNotIn(name, text)
        self.assert_cues(text, cues)

    def test_unready_wrong_week_and_incomplete_player_models_do_not_get_named(self):
        self.players()
        model = self.namespace["SLIDE_PLAYER_FIXTURE_XPTS"]
        for mutation in (lambda df: df.assign(gameweek=9),
                         lambda df: df.assign(calculation_status="PENDING"),
                         lambda df: df.drop(columns=["goal_points", "fixture_expected_points"])):
            with self.subTest(mutation=mutation):
                self.namespace["SLIDE_PLAYER_FIXTURE_XPTS"] = mutation(model)
                text, _ = projected_goals_narration(self.namespace)
                self.assertNotIn("Player ", text)
        self.namespace.pop("DAY3_AVAILABILITY")
        text, _ = projected_goals_narration(self.namespace)
        self.assertNotIn("Player ", text)

    def test_patch_replaces_only_the_requested_function_and_exports_current_cues(self):
        source = textwrap.dedent('''\
            SETTING = "preserve"
            if True:
                def _d3_projected_goals_narration():
                    return "old script"

                def _d3_defcon_narration():
                    return "unchanged defensive contribution"
            OTHER_SETTING = "preserve too"
        ''')
        patched = patch_projected_goals_narration_source(source)
        def strip_target(code):
            class Strip(ast.NodeTransformer):
                def visit_FunctionDef(self, node):
                    return None if node.name == "_d3_projected_goals_narration" else node
            return ast.dump(Strip().visit(ast.parse(code)))
        self.assertEqual(strip_target(source), strip_target(patched))
        namespace = dict(self.namespace)
        exec(patched, namespace)
        text = namespace["_d3_projected_goals_narration"]()
        self.assertIn("Manchester United lead the model", text)
        self.assert_cues(text, namespace["PROJECTED_GOALS_NARRATION_CUES"])
        for invalid in ("pass\n", source + source):
            with self.assertRaisesRegex(RuntimeError, "exactly one"):
                patch_projected_goals_narration_source(invalid)


if __name__ == "__main__":
    unittest.main()
