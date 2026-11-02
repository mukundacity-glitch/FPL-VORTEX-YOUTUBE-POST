"""Synthetic regression cases for Day 1 market-only (no guessed gameweek data)."""
import copy
import unittest
from vortex.day1_market import choose_market_transfer


def market_example():
    old = {'start':'2026-10-30T00:00:00Z','end':'2026-10-31T00:00:00Z',
           'source':'Recorded FPL snapshots',
           'players':{'1':{'in':10,'out':25,'owners_at_start':1000},
                      '2':{'in':30,'out':10,'owners_at_start':1000}}}
    new = {'start':'2026-10-31T00:00:00Z','end':'2026-11-01T00:00:00Z',
           'source':'Recorded FPL snapshots',
           'players':{'1':{'in':10,'out':50,'owners_at_start':1000},
                      '2':{'in':60,'out':10,'owners_at_start':1000}}}
    picks = [{'id':1,'name':'Owned Example','position':2,
              'club_id':1,'selling_value':6.0}]
    picks += [{'id':i+3,'name':f'Current {i}','position':3,
               'club_id':(i%17)+3,'selling_value':5.0}
              for i in range(14)]
    return {'windows':[old,new],
            'thresholds':{'min_owners':100,'min_activity':10,
                          'min_demand':.001,'min_momentum':.001},
            'current_squad':{'picks':picks,'bank':1.0,'free_transfers':1,
                             'verified_at':'2026-11-01T18:00:00Z',
                             'source':'Official editable FPL entry'},
            'pool':[{'id':2,'name':'Target Example','position':2,
                     'club_id':2,'price':6.5,'available':True}]}


class DayOneMarketTests(unittest.TestCase):
    def test_sustained_market_move_and_existing_roster_limit(self):
        r=choose_market_transfer(market_example())
        self.assertEqual(r['verdict'],'BUY')
        self.assertEqual((r['option']['outgoing'],r['option']['incoming']),(1,2))
        self.assertEqual(len(r['alternatives']),1)
        self.assertEqual(r['option']['outgoing_name'],'Owned Example')

    def test_no_market_input_is_watch_not_invented_buy(self):
        self.assertEqual(choose_market_transfer(None)['verdict'],'WATCH')
        p=market_example();p['windows']=[p['windows'][1]]
        self.assertEqual(choose_market_transfer(p)['verdict'],'WATCH')

    def test_incomparable_windows_cannot_create_market_claim(self):
        for field,value in [('start','2026-10-31T12:00:00Z'),('source','Different source')]:
            p=market_example();p['windows'][1][field]=value
            self.assertEqual(choose_market_transfer(p)['verdict'],'WATCH')

    def test_current_verified_money_and_squad_required(self):
        for field,value in [('bank',None),('free_transfers',None),('verified_at',None)]:
            p=market_example();p['current_squad'][field]=value
            self.assertEqual(choose_market_transfer(p)['verdict'],'WATCH')

    def test_feasibility_no_hit_availability_price_or_club_violation(self):
        for path,value in [('free_transfers',0),('bank',0)]:
            p=market_example();p['current_squad'][path]=value
            self.assertEqual(choose_market_transfer(p)['verdict'],'HOLD')
        p=market_example();p['pool'][0]['available']=False
        self.assertEqual(choose_market_transfer(p)['verdict'],'HOLD')
        p=market_example();p['pool'][0]['position']=4
        self.assertEqual(choose_market_transfer(p)['verdict'],'HOLD')
        p=market_example();p['current_squad']['picks'][1]['club_id']=2
        p['current_squad']['picks'][2]['club_id']=2
        p['current_squad']['picks'][3]['club_id']=2
        self.assertEqual(choose_market_transfer(p)['verdict'],'HOLD')

    def test_low_sample_or_missing_owners_never_recommends(self):
        p=market_example();p['windows'][0]['players']['2']['owners_at_start']=5
        self.assertEqual(choose_market_transfer(p)['verdict'],'HOLD')
        p=market_example();p['windows'][1]['players']['2']['owners_at_start']=None
        self.assertEqual(choose_market_transfer(p)['verdict'],'HOLD')


if __name__=='__main__':
    unittest.main()
