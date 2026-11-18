from datetime import datetime, timedelta
import unittest

from day3.preview_editorial import preview_intro, transfer_player_line
from day3.test_live_evidence import sample_inputs
from day3.live_evidence import build_evidence


class PreviewEditorialTests(unittest.TestCase):
    def test_live_opening_uses_checked_results_deadlines_and_recent_team_news(self):
        bootstrap, fixtures, live, cutoff = sample_inputs()
        deadline = datetime.fromisoformat(bootstrap["events"][1]["deadline_time"])
        bootstrap["events"] += [
            {"id": 3, "deadline_time": (deadline + timedelta(days=3)).isoformat()},
            {"id": 4, "deadline_time": (deadline + timedelta(days=7)).isoformat()},
        ]
        fixtures[0]["team_a_score"] = 4
        bootstrap["elements"][0].update(
            status="d", chance_of_playing_next_round=75, selected_by_percent="30",
            news_added=cutoff, news="Knock",
        )
        snapshot = build_evidence(bootstrap, fixtures, live, cutoff)
        snapshot["_bootstrap"] = bootstrap
        args = (snapshot, "the transfer desk and captaincy", lambda tid: snapshot["teams"][tid]["name"],
                lambda pid: snapshot["players"][pid]["name"])
        spoken = preview_intro(*args)
        self.assertIn("3 deadlines", spoken)
        self.assertIn("Club Beta beat Club Alpha 4 to 1", spoken)
        self.assertIn("Alex Same at 75% to play", spoken)
        self.assertIn("the transfer desk and captaincy", spoken)

        bootstrap["events"][0]["data_checked"] = False
        snapshot["players"][11]["news_added"] = (datetime.fromisoformat(cutoff) - timedelta(days=8)).isoformat()
        spoken = preview_intro(*args)
        self.assertNotIn("beat", spoken)
        self.assertNotIn("Alex Same", spoken)

    def test_transfer_copy_leads_with_actual_market_and_respects_absence(self):
        record = {"action": "BUY", "transfers_in": 1200, "has_projection": True,
                  "has_horizon": True, "has_minutes": True, "xmins": 75, "xpts": 4.5, "next_5_xpts": 20}
        available = {"availability_reason": "AVAILABLE", "availability": 1}
        spoken = transfer_player_line(record, "Alex Same", "Club Alpha", "away to Club Beta", available)
        self.assertIn("Alex Same from Club Alpha", spoken)
        self.assertIn("1,200 transfers in", spoken)
        self.assertIn("20.0 points across the next five", spoken)
        doubtful = {"availability_reason": "DOUBTFUL", "availability": .25}
        self.assertIn("25% chance", transfer_player_line(record, "Alex Same", "Club Alpha", "away to Club Beta", doubtful))
        blank = transfer_player_line(record, "Alex Same", "Club Alpha", "with no fixture currently assigned", available)
        self.assertIn("blank this Gameweek", blank)
        self.assertNotIn("20.0", blank)
