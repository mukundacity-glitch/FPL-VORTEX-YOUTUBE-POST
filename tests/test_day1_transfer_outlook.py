from datetime import datetime, timezone
import unittest

from vortex.day1_transfer_outlook import build_outlook, narration, render


def example():
    elements = [
        dict(id=i, web_name=f"Player {i}", team=1, element_type=4 if i % 2 else 2,
             now_cost=45 + i, form=str(i / 2), status="a",
             transfers_in_event=20000 - 1300 * i if i <= 6 else i,
             transfers_out_event=100 * i if i <= 6 else 12000 + 1400 * (i - 6))
        for i in range(1, 13)
    ]
    elements.append(dict(elements[0], id=13, transfers_out_event=None))
    bootstrap = dict(events=[dict(id=11, is_next=True)], elements=elements,
                     teams=[dict(id=1, name="Example Town"), dict(id=2, name="Example City")],
                     element_types=[dict(id=4, singular_name="Forward", singular_name_short="FWD"),
                                    dict(id=2, singular_name="Defender", singular_name_short="DEF")])
    fixtures = [dict(id=61, event=11, team_h=1, team_a=2)]
    return build_outlook(bootstrap, fixtures, 11, datetime(2026, 11, 14, tzinfo=timezone.utc))


class TransferOutlookTests(unittest.TestCase):
    def test_ranked_six_per_side_and_narration_maps_exactly_to_rows(self):
        board = example()
        self.assertEqual([p["id"] for p in board["in"]], list(range(1, 7)))
        self.assertEqual([p["id"] for p in board["out"]], list(range(12, 6, -1)))
        self.assertEqual(board["out"][0]["net"], 12 - 20400)
        speech, beats = narration(board, lambda p: p["name"])
        self.assertEqual(len(beats), 6)
        self.assertEqual({b["row"] for b in beats}, {"out-10", "out-11", "out-12", "in-1", "in-2", "in-3"})
        self.assertIn("separate totals", speech)
        self.assertIn("cheaper than", speech)
        self.assertNotIn("managers are selling", speech)
        assets = dict.fromkeys(range(1, 13), ("", ""))
        html = render(board, [], assets, [], "")
        self.assertIn("18,700", html)
        self.assertIn("-20,388", html)
        self.assertEqual(html.count('<tr id='), 12)

    def test_missing_activity_does_not_generate_fake_rows_or_cues(self):
        board = dict(example(), **{"in": [], "out": []})
        text, beats = narration(board, lambda p: p["name"])
        self.assertEqual(beats, [])
        self.assertIn("no official transfer activity", text)
        self.assertIn("No qualifying transfers", render(board, [], {}, [], ""))
