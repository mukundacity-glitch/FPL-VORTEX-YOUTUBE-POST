"""Production opening contracts: facts, timing, privacy, integration and fallbacks."""
import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest

from vortex.day1_brief import (badge, build_brief, build_intro_agenda, build_timeline,
                               caption_cues, datum, format_datum, render_brief)
from vortex.day1_media import _filter_graph
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 7, 0, tzinfo=timezone.utc)


def snapshot():
    # Explicit fixtures for offline regression only; never used in production.
    return dict(gw=9, status="FINAL",
        bootstrap={"events":[{"id":9,"finished":True,"data_checked":True,"average_entry_score":40},{"id":10}],
            "elements":[{"id":1,"web_name":"Test player","status":"a"}]},
        fixtures=[{"event":9,"finished":True,"team_h_score":1,"team_a_score":0}],
        picks={"entry_history":{"points":16},"picks":[
            {"element":1,"multiplier":2,"is_captain":True,"position":1},
            {"element":2,"multiplier":0,"position":12}]},
        history={"current":[{"event":8,"overall_rank":100},
            {"event":9,"points":16,"overall_rank":80,"rank":50,"event_transfers_cost":4}]},
        live={"elements":[{"id":1,"stats":{"total_points":8,"minutes":90}},
                          {"id":2,"stats":{"total_points":3,"minutes":20}}]},
        provenance={k:{"source":"Official FPL "+k,"retrievedAt":NOW.isoformat()}
                    for k in ("bootstrap","fixtures","picks","history","live")})


def cards():
    return build_intro_agenda(["00_intro","gw_review"],next_gw=10,review_gw=9,
        review_status="FINAL", review_segments=[{"id":x} for x in
            ("headline","editorial_squad_context","editorial_routes","editorial_verdict")])


class BriefFacts(unittest.TestCase):
    def build(self, data=None, **kw):
        return build_brief(data or snapshot(),next_gw=10,now=NOW,**kw)

    def test_season_follows_official_event_deadlines_and_requires_provenance(self):
        data=snapshot()
        data['bootstrap']['events'][0]['deadline_time']='2026-08-15T10:00:00Z'
        self.assertEqual(self.build(data)['season']['value'],'2026/27')
        data['bootstrap']['events'][0]['deadline_time']='2027-05-15T10:00:00Z'
        self.assertEqual(self.build(data)['season']['value'],'2026/27')
        data['provenance'].pop('bootstrap')
        self.assertEqual(format_datum(self.build(data)['season']),'Not verified')
        self.assertEqual(format_datum(self.build()['season']),'Unavailable')

    def test_actual_applied_points_hits_and_rank_direction(self):
        board=self.build()["scoreboard"]
        self.assertEqual(board["Before deductions"]["value"],16)
        self.assertEqual(board["After deductions"]["value"],12)
        self.assertEqual(board["Official GW points"]["value"],16)
        self.assertEqual(board["Rank movement"]["value"],20)
        self.assertEqual(board["Captain points (applied)"]["value"],16)
        self.assertEqual(board["Bench points (raw)"]["value"],3)
        self.assertTrue(all(x["freshnessStatus"]=="fresh" for x in board.values()))

    def test_mismatched_presenter_score_is_rejected(self):
        data=snapshot();data["history"]["current"][-1]["points"]=99
        with self.assertRaisesRegex(ValueError,"disagree"):
            self.build(data)

    def test_effective_vice_captain_promotion_and_triple_captain(self):
        data=snapshot()
        data["picks"]["picks"][0]["multiplier"]=0
        data["picks"]["picks"][1].update(multiplier=2,is_vice_captain=True)
        data["history"]["current"][-1]["points"]=6
        data["picks"]["entry_history"]["points"]=6
        self.assertEqual(self.build(data)["scoreboard"]["Captain points (applied)"]["value"],6)
        data["picks"]["picks"][1]["multiplier"]=3
        data["history"]["current"][-1]["points"]=9
        data["picks"]["entry_history"]["points"]=9
        self.assertEqual(self.build(data)["scoreboard"]["Captain points (applied)"]["value"],9)

    def test_wrong_gameweek_is_rejected(self):
        data=snapshot();data["gw"]=10
        with self.assertRaisesRegex(ValueError,"inconsistent"):
            self.build(data)

    def test_missing_official_event_is_not_guessed(self):
        data=snapshot();data["bootstrap"]["events"]=[]
        with self.assertRaisesRegex(ValueError,"official event"):
            self.build(data)

    def test_points_final_only_after_official_lock_and_all_matches(self):
        self.assertEqual(self.build()["status"],"FINAL")
        for field in ("finished","data_checked"):
            data=snapshot();data["bootstrap"]["events"][0][field]=False
            self.assertEqual(self.build(data)["status"],"PROVISIONAL")
        data=snapshot();data["fixtures"].append({"event":9,"finished":False})
        self.assertEqual(self.build(data)["status"],"PROVISIONAL")

    def test_missing_injury_is_not_labelled_fit(self):
        data=snapshot();data["bootstrap"]["elements"][0].pop("status")
        self.assertEqual(self.build(data)["players"][0]["fields"]["availability"]["freshnessStatus"],"unavailable")

    def test_missing_xpts_and_split_fdr_remain_unavailable(self):
        projections=self.build()["projections"]
        for key in ("xPts","attackFDR","defenceFDR","xMinutes"):
            self.assertIsNone(projections[key]["value"])
            self.assertEqual(projections[key]["freshnessStatus"],"unavailable")

    def test_forecast_requires_methodology_timestamp_and_matching_horizon(self):
        model={"value":6.2,"source":"VORTEX","retrievedAt":NOW.isoformat(),
               "gameweek":10,"methodologyVersion":"test-v1"}
        valid=self.build(forecasts={"xPts":model})["projections"]["xPts"]
        self.assertEqual(valid["dataStatus"],"MODEL ESTIMATE")
        self.assertEqual(valid["freshnessStatus"],"fresh")
        self.assertIn("test-v1",badge(valid))
        for field in ("methodologyVersion","retrievedAt","gameweek","source"):
            invalid=deepcopy(model);invalid.pop(field)
            self.assertNotEqual(self.build(forecasts={"xPts":invalid})["projections"]["xPts"]["freshnessStatus"],"fresh")

    def test_zero_is_valid_missing_is_not_zero(self):
        self.assertEqual(format_datum(datum(0,source="FPL",retrieved_at=NOW.isoformat(),gameweek=9,now=NOW)),"0")
        self.assertEqual(format_datum(datum(None)),"Unavailable")

    def test_missing_provenance_not_silently_verified(self):
        data=snapshot();data["provenance"]={}
        result=self.build(data)
        self.assertEqual(format_datum(result["scoreboard"]["Official GW points"]),"Not verified")
        self.assertNotIn("Data verified",badge(result["reviewSource"]))

    def test_stale_data_and_actual_eastern_timestamp(self):
        item=datum(12,source="FPL",retrieved_at=(NOW-timedelta(hours=2)).isoformat(),gameweek=9,now=NOW)
        self.assertEqual(item["freshnessStatus"],"stale")
        self.assertIn("Data may be stale",badge(item))
        self.assertIn("2026-11-06 17:00:00 EST -0500",badge(item))

    def test_future_naive_and_nonfinite_values_not_verified(self):
        for ts in ((NOW+timedelta(hours=1)).isoformat(),"2026-11-07T00:00:00",None):
            self.assertEqual(datum(3,source="FPL",retrieved_at=ts,gameweek=9,now=NOW)["freshnessStatus"],"not_verified")
        self.assertEqual(datum(float("nan"))["freshnessStatus"],"unavailable")

    def test_missing_personal_team_has_no_example_or_invented_result(self):
        data=snapshot();data.pop("picks");data.pop("history")
        result=self.build(data)
        self.assertFalse(result["personalTeamAvailable"])
        self.assertTrue(all(x["value"] is None for k,x in result["scoreboard"].items() if k!="Average score"))

    def test_serialized_ui_contains_no_private_entry_data(self):
        data=snapshot();data["entry"]={"id":123456,"email":"private@example.test","player_first_name":"Private"}
        result=json.dumps(self.build(data))
        for private in ("123456","private@example.test","player_first_name"):
            self.assertNotIn(private,result)

    def test_missing_dependency_stamp_invalidates_derived_points(self):
        data=snapshot();data["provenance"]["picks"].pop("retrievedAt")
        self.assertEqual(self.build(data)["scoreboard"]["Captain points (applied)"]["freshnessStatus"],"not_verified")

    def test_double_gameweek_requires_both_model_legs(self):
        data=snapshot();data["bootstrap"]["elements"][0]["team"]=1
        data["fixtures"] += [dict(id=i,event=10,team_h=1,team_a=2) for i in (101,102)]
        rows=[dict(player_id=1,gameweek=10,fixture_id=i,fixture_expected_points=4.2,
            expected_minutes=75,calculation_status="READY",model_version="test-v1",
            source_name="VORTEX test",forecast_timestamp=NOW.isoformat()) for i in (101,102)]
        complete=self.build(data,player_model_rows=rows)["players"][0]["fields"]
        self.assertEqual(complete["xPts"]["value"],8.4)
        self.assertEqual(complete["expectedMinutes"]["value"],150)
        partial=self.build(data,player_model_rows=rows[:1])["players"][0]["fields"]
        self.assertEqual(partial["xPts"]["freshnessStatus"],"unavailable")

    def test_missing_fixture_model_stays_unavailable_but_opponent_is_sourced(self):
        data=snapshot();data["bootstrap"]["elements"][0]["team"]=1
        data["bootstrap"]["teams"]=[dict(id=2,short_name="TST")]
        data["fixtures"].append(dict(id=101,event=10,team_h=1,team_a=2))
        fixture=self.build(data)["players"][0]["nextFixtures"][0]
        self.assertEqual(fixture["opponent"]["value"],"TST (H)")
        self.assertEqual(fixture["opponent"]["gameweek"],10)
        self.assertEqual(fixture["ratings"]["attack"]["freshnessStatus"],"unavailable")


class BriefProduction(unittest.TestCase):
    def test_new_agenda_uses_exact_current_headings_and_anchors(self):
        self.assertEqual([c["title"] for c in cards()], ["GAMEWEEK REVIEW","PLAYERS AND FIXTURES",
            "NUMBERS BEHIND THE POINTS","TRANSFER PRIORITIES","CAPTAINCY AND FINAL XI"])
        for c in cards():self.assertIn(c["anchor"].lower(),c["speech"].lower())

    def test_opening_cannot_be_disconnected_from_review(self):
        with self.assertRaisesRegex(ValueError,"directly"):
            build_intro_agenda(["00_intro"],next_gw=10)

    def test_actual_timing_enforced_without_speed_changes(self):
        sequence={"This is":4,"Welcome":9,"Let's review":33}
        sequence.update({c["anchor"]:14+i*3.5 for i,c in enumerate(cards())})
        lookup=lambda words,phrase,**kw:(sequence[phrase],.5)
        timeline=build_timeline([],duration=38,phrase_span=lookup,cards=cards())
        self.assertLess(timeline["transition"],40)
        for duration in (34,41):
            with self.assertRaisesRegex(ValueError,"35–40"):
                build_timeline([],duration=duration,phrase_span=lookup,cards=cards())

    def test_html_escapes_news_and_handles_missing_data(self):
        result=build_brief(snapshot(),next_gw=10,now=NOW)
        altered=cards();altered[0]["subtitle"]='<script>alert(1)</script>'
        page=render_brief(result,cards=altered)
        self.assertIn('&lt;script&gt;',page)
        self.assertNotIn('<script>alert(1)',page)
        self.assertNotIn('vxFixtureGrid',page)
        self.assertIn('prefers-reduced-motion',page)
        self.assertIn('id="gameweek-review"',page)

    def test_caption_groups_keep_all_measured_words(self):
        words=[dict(text=str(i),start=i*.4,duration=.3) for i in range(20)]
        cues=caption_cues(words)
        self.assertEqual(' '.join(c["text"] for c in cues),' '.join(w["text"] for w in words))
        self.assertTrue(all(len(c["text"].split())<=8 for c in cues))

    def test_media_filter_never_concatenates_second_intro(self):
        args=dict(width=854,height=480,fps=Fraction(24),opening_duration=0,program_duration=60)
        graph=_filter_graph(**args,include_opening=False)
        self.assertNotIn('[0:',graph)
        self.assertNotIn('concat=n=2',graph)
        self.assertIn('[program_video]null[final_video]',graph)
        self.assertIn('concat=n=2',_filter_graph(**dict(args,opening_duration=8)))

    def test_production_uses_one_opening_and_preserves_review(self):
        source=(ROOT/'1_final_day1.py').read_text()
        self.assertEqual(source.count('INTRO = render_brief('),1)
        self.assertIn('"opening_policy": "gameweek_brief"',source)
        self.assertIn('review_uri=review_uri',source)
        self.assertIn('SCENE_RENDER_REVISIONS',source)
        self.assertIn('"brief_timeline": cfg.get("brief_timeline")',source)
        self.assertIn('profile["rate"] = "+0%"',source)
        self.assertIn('el.classList.contains("reviewPanel")',source)
        self.assertIn('data.players.find(p=>Number(p.multiplier)>1)',source)
        self.assertIn('"retrievedAt": datetime.now(timezone.utc).isoformat()',source)


if __name__ == '__main__':unittest.main()
