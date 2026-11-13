import re
import unittest
from vortex.day1_scene4 import build_outlook, outlook_narration, outlook_script, outlook_timing
from vortex.football_identity import full_club_name


class Scene4Tests(unittest.TestCase):
    def test_blank_double_and_missing_fixture_coverage(self):
        teams = {i: {"name":str(i),"short":f"T{i}","badge":""} for i in (1,2)}
        player = {"id":10,"code":99,"team":1,"element_type":3,"web_name":"Test",
                  "now_cost":50,"status":"a","minutes":90,"transfers_in_event":4,
                  "transfers_out_event":3,"selected_by_percent":"1.2","cost_change_event":-1}
        fixtures = [{"id":i,"event":gw,"team_h":1,"team_a":2}
                    for i,gw in enumerate([11,11,13,14,15],1)]
        forecasts = [{"player_id":10,"team_id":1,"gameweek":gw,"gameweek_expected_points":xp,"fixture_count":count}
                     for gw,xp,count in [(11,12,2),(13,3,1),(14,4,1),(15,5,1)]]
        history = lambda _: {"history":[{"round":10,"minutes":90,"selected":120},{"round":9,"minutes":90,"selected":100}]}
        def build(rows, **kwargs):
            return build_outlook(11,fixtures,teams,[player],rows,[],[9,10],history,lambda _:"","2026/27","QA", **kwargs)
        leader, = build(forecasts)["leaders"]
        self.assertEqual(leader["weeks"], [12.0,0.0,3.0,4.0,5.0])
        self.assertEqual(leader["total"], 24)
        self.assertAlmostEqual(leader["value"], 4.8)
        self.assertEqual(leader["owner_change"], 20)
        self.assertIsNone(leader["recent"]["shots"])
        self.assertEqual(leader["price_move"], -1)
        self.assertEqual(build(forecasts[:-1])["leaders"], [])
        wrong_double = [dict(forecasts[0],fixture_count=1), *forecasts[1:]]
        self.assertEqual(build(wrong_double)["leaders"], [])
        review = build(forecasts, fixture_forecast=[{"player_id":10,"gameweek":11,"goal_share":1}])
        self.assertEqual(review["leaders"][0]["verdict"], "REVIEW")
        self.assertEqual(review["value"], [])
        self.assertFalse(any(review["verdicts"].values()))

    def test_identical_player_metrics_and_verdicts_keep_distinct_sentences(self):
        row = {
            "team_id": 3, "price": 5.0, "tiles": [
                {"id": 18, "gw": 11, "opponent_id": 4, "venue": "H", "band": "easy", "rating": "2.0"},
            ],
            "weeks": [3.0] * 5, "total": 15.0, "recent": {"minutes": 90, "total_points": 2},
            "sample_matches": 1, "forecast_review": False, "net": 0, "verdict": "HOLD",
            "reason": "Projection and transfer flow give a mixed signal",
        }
        scene = {"gw": 11, "weeks": list(range(11, 16)), "board": [
            dict(row, id=1, name="Jackson"), dict(row, id=2, name="Palmer"),
        ]}
        script = outlook_script(scene, lambda i: {3: "Chelsea", 4: "Arsenal"}[i], lambda _, name: name)
        sentences = re.split(r"(?<=[.!?])\s+", " ".join(line for _, line in outlook_narration(script)))
        self.assertEqual(len(sentences), len(set(sentences)))
        self.assertIn("My verdict for Palmer is hold", " ".join(sentences))

    def test_measured_metric_spans_handle_repeated_projection_values(self):
        script = [
            ("opening", None, [("Opening.", None, None)]),
            ("hero-42", 42, [
                ("First player.", "identity.player", None),
                ("The next projection is three point zero.", "forecast.nextGwXpts", "three point zero"),
                ("The later projection is three point zero.", "forecast.fiveGwXpts", "three point zero"),
            ]),
            ("summary", None, [("Closing.", None, None)]),
        ]
        normalize = lambda text, **_: text
        tokenize = lambda text: re.findall(r"[a-z]+", text.lower())
        words = [
            {"text": token, "start": i * .25, "duration": .2}
            for i, token in enumerate(tokenize(" ".join(
                line for _, _, lines in script for line, _, _ in lines
            )))
        ]

        def span(boundaries, phrase, **_):
            target = tokenize(phrase)
            tokens = [w["text"] for w in boundaries]
            for i in range(len(tokens)):
                if tokens[i:i + len(target)] == target:
                    start = boundaries[i]["start"]
                    last = boundaries[i + len(target) - 1]
                    return start, last["start"] + last["duration"] - start
            raise ValueError(phrase)

        _, metrics = outlook_timing(script, words, 6, span, normalize)
        first, second = metrics[1:]
        self.assertEqual(first["playerId"], 42)
        self.assertEqual(first["metricId"], "forecast.nextGwXpts")
        self.assertLess(first["start"], first["emphasis"])
        self.assertLess(first["end"], second["start"])
        with self.assertRaises(ValueError):
            outlook_timing(script, [w for w in words if w["text"] != "zero"], 6, span, normalize)

    def test_full_club_names_preserve_provider_ids_and_fail_closed(self):
        team = {"id": 5, "code": 36, "name": "Brighton", "short": "BHA"}
        self.assertEqual(full_club_name(team), "Brighton & Hove Albion")
        self.assertEqual(full_club_name(team, speech=True), "Brighton and Hove Albion")
        with self.assertRaises(ValueError):
            full_club_name({"id": 900, "short": "XXX", "name": "XXX"})


if __name__ == "__main__":
    unittest.main()
