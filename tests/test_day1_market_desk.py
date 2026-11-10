from __future__ import annotations
import unittest
from pathlib import Path
from vortex.day1_market_desk import build_market_desk, insert_market_segments, market_card


def snapshot():
    def player(pid, incoming, outgoing, **extra):
        p=dict(id=pid, code=100+pid, web_name=f'Player {pid}', first_name='Example',
               second_name=f'Player {pid}', team=1, element_type=3, now_cost=65,
               status='a', minutes=700, selected_by_percent='20.0', form='2.0',
               transfers_in_event=incoming, transfers_out_event=outgoing,
               total_points=40, points_per_game='4.0')
        p.update(extra)
        return p
    return dict(total_players=1000000, elements=[
        player(1,50000,2000), player(2,1000,60000,status='i'), player(3,50,100),
        player(4,55000,2000,status='d'),
    ])


class MarketDeskTests(unittest.TestCase):
    def test_reuses_event_policy_and_excludes_unavailable_buys(self):
        rows=build_market_desk(snapshot())
        self.assertEqual([r['action'] for r in rows],['BUY','HOLD','SELL'])
        self.assertEqual([r['element']['id'] for r in rows],[1,3,2])
        self.assertIn('availability flag',rows[-1]['text'])
        self.assertIn('50,000',rows[0]['text'])
        self.assertNotIn('rolling',rows[0]['text'])

    def test_no_hold_is_honest_and_no_unavailable_buy_is_substituted(self):
        boot=snapshot()
        for p in boot['elements']:
            p['form']='8.0'
            p['status']='i'
        rows=build_market_desk(boot)
        self.assertIsNone(rows[0]['element'])
        self.assertIsNone(rows[1]['element'])
        self.assertIn('no player clears',rows[0]['text'])

    def test_market_narration_uses_official_full_name_instead_of_display_initial(self):
        boot = snapshot()
        boot['elements'][0].update(web_name='N.Jackson', first_name='Nicolas', second_name='Jackson')
        buy = build_market_desk(boot)[0]
        self.assertIn('Nicolas Jackson', buy['text'])
        self.assertNotIn('N.Jackson', buy['text'])
        self.assertEqual(buy['element']['web_name'], 'N.Jackson')

    def test_agenda_promises_the_market_cards_that_will_actually_render(self):
        from vortex.day1_agenda import build_intro_agenda
        beats = ['headline','editorial_squad_context','editorial_routes',
                 'editorial_verdict','market_intro','editorial_comparison']
        cards = build_intro_agenda(['00_intro','gw_review'], next_gw=12, review_gw=11,
                                  review_segments=[dict(id=key) for key in beats])
        self.assertEqual(len(cards),5)
        self.assertEqual(cards[2]['key'],'market')
        self.assertIn('player cards',cards[2]['speech'])

    def test_invalid_official_counts_fail_before_tts(self):
        boot=snapshot();boot['elements'][0]['transfers_in_event']=-1
        with self.assertRaisesRegex(RuntimeError,'invalid official'):
            build_market_desk(boot)
        with self.assertRaises(ValueError):build_market_desk({})

    def test_insert_immediately_after_review_without_touching_scoring_identity(self):
        original=[dict(id='player_9',player_id=9),dict(id='review_close'),dict(id='editorial_squad_context'),
                  dict(id='editorial_comparison'),dict(id='editorial_defence'),dict(id='editorial_tradeoff')]
        result=insert_market_segments(original,build_market_desk(snapshot()))
        self.assertEqual([s['id'] for s in result][1:6],
            ['review_close','market_intro','market_buy','market_hold','market_sell'])
        self.assertEqual([s['player_id'] for s in result if 'player_id' in s],[9])
        self.assertEqual(len(original),6)
        self.assertNotIn('editorial_comparison',[s['id'] for s in result])
        self.assertNotIn('editorial_defence',[s['id'] for s in result])

    def test_card_uses_official_assets_identity_price_and_separate_fixture_handoff(self):
        row=build_market_desk(snapshot())[0]
        card=market_card(row,{1:dict(name='Example FC',short_name='EXF',code=11)},
                         lambda *args:[dict(opponent='ABC',venue='H')])
        self.assertEqual(card['id'],1)
        self.assertEqual(card['price'],'£6.5m')
        self.assertIn('p101.png',card['player_image'])
        self.assertIn('t11.png',card['club_badge'])
        self.assertEqual(len(card['display_stats']),6)
        self.assertEqual(card['display_stats'][0]['value'],'50,000')
        self.assertEqual(card['fixtures'][0]['venue'],'H')
        self.assertIn('BUY WATCHLIST',card['verdict_sub'])

    def test_runtime_binds_measured_segments_without_weakening_review_contract(self):
        source=(Path(__file__).resolve().parents[1]/'1_final_day1.py').read_text()
        self.assertIn('segments = insert_market_segments(segments, VX_DAY1_MARKET_DESK)',source)
        self.assertIn('s.id === item.segment_id && t >= s.t0 && t < s.t1',source)
        self.assertIn('window.VXPlayerCard.mount(hw, desk.card)',source)
        self.assertIn('desk ? 0 : scoreboardOpening ? 1 : panelsP',source)
        self.assertIn('el.classList.contains("reviewPanel")',source)
        self.assertIn('snapshot_review_animation_segments(pkg["segments"])',source)

if __name__=='__main__': unittest.main()
