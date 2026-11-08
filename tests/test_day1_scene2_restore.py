from __future__ import annotations
import unittest
from vortex.day1_scene2_restore import build_scene2_manifest


def episode():
    players = [
        dict(id=i, name=f"Player {i}", position="GK" if i == 1 else "MID",
             club="Verified Club", gw_points=i % 8, minutes=90,
             slot=f"original-slot-{i}") for i in range(1, 16)
    ]
    narration = [dict(player_id=i, start=10.0 + (i-1)*7,
                      end=17.0 + (i-1)*7,
                      text=f"Player {i} earned verified points.") for i in range(1, 16)]
    return dict(gameweek=9, starters=players[:11], bench=players[11:],
                narration=narration, captain_id=3, vice_captain_id=4,
                captain_multiplier=2,
                gameweek_table=dict(gw_points=55, captain_points=10, bench_points=9,
                                    net_points=55),
                rank_movement=dict(previous=2000, current=1500),
                transfers=[dict(status="potential", name="Example")],
                results=[dict(home="A", away="B", home_score=2,
                              away_score=1, status="FT")])


class Scene2RestorationTests(unittest.TestCase):
    def test_all_15_cards_fly_from_left_and_stay_on_pitch(self):
        manifest = build_scene2_manifest(**episode())
        self.assertEqual(len(manifest["players"]), 15)
        self.assertEqual(len(manifest["final_pitch_player_ids"]), 15)
        self.assertEqual(manifest["rank_movement"]["direction"], "green_up")
        for player in manifest["players"]:
            self.assertEqual(player["hero_component"], "VXPlayerCard")
            self.assertTrue(player["left_hero_enter"] <
                            player["pitch_flight_start"] ==
                            player["narration_end"] < player["pitch_arrival"])
            self.assertTrue(player["persist_in_pitch"])
        self.assertEqual(len([p for p in manifest["players"] if p["role"] == "starter"]), 11)
        self.assertEqual(len([p for p in manifest["players"] if p["role"] == "bench"]), 4)
        self.assertTrue(manifest["players"][2]["captain"])
        self.assertTrue(manifest["players"][3]["vice"])

    def test_invalid_roster_fails_instead_of_inventing_players(self):
        data = episode()
        data["starters"] = data["starters"][:-1]
        with self.assertRaisesRegex(ValueError, "exactly 11"):
            build_scene2_manifest(**data)

    def test_incomplete_table_rejected(self):
        data = episode()
        del data["gameweek_table"]["net_points"]
        with self.assertRaisesRegex(ValueError, "net_points"):
            build_scene2_manifest(**data)

    def test_unverified_completed_transfer_rejected(self):
        data = episode()
        data["transfers"] = [dict(status="completed", name="Example", verified=False)]
        with self.assertRaisesRegex(ValueError, "unverified"):
            build_scene2_manifest(**data)

    def test_negative_player_points_allowed(self):
        data = episode()
        data["starters"][0]["gw_points"] = -1
        self.assertEqual(build_scene2_manifest(**data)["players"][0]["actual_points"], -1)

    def test_duplicate_pitch_slot_rejected(self):
        data = episode()
        data["bench"][0]["slot"] = data["starters"][0]["slot"]
        with self.assertRaisesRegex(ValueError, "slots must be unique"):
            build_scene2_manifest(**data)

    def test_down_rank_red_and_missing_rank_unavailable(self):
        data = episode()
        data["rank_movement"] = dict(previous=100, current=200)
        self.assertEqual(build_scene2_manifest(**data)["rank_movement"]["direction"], "red_down")
        data["rank_movement"] = None
        self.assertEqual(build_scene2_manifest(**data)["rank_movement"]["direction"], "unavailable")


if __name__ == "__main__":
    unittest.main()
