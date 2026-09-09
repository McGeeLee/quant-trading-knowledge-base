import unittest
from backtest_v3_long import simulate
from backtest_v2_pair import load


def bars(near,far,near_open=None,far_open=None):
    no=near if near_open is None else near_open
    fo=far if far_open is None else far_open
    return [dict(date=f'2026-01-{i+1:02}',near_close=a,far_close=b,near_open=c,far_open=d,
                 far_open_interest=1000,near_volume=100,far_volume=100)
            for i,(a,b,c,d) in enumerate(zip(near,far,no,fo))]


class V3Tests(unittest.TestCase):
    def test_four_closes_then_next_open(self):
        r=simulate(bars([110,111,112,113],[100]*4))
        self.assertEqual(r['count'],0)
        self.assertEqual(r['pending']['action'],'entry')

    def test_both_are_long_not_far_short(self):
        data=bars([110,111,112,113,125,130],[100,100,100,100,109,112],
                  [110,111,112,113,120,128],[100,100,100,100,103,111])
        a,b=simulate(data),simulate(data,leg='far')
        self.assertAlmostEqual(a['net'],7.8)
        self.assertAlmostEqual(b['net'],7.8)
        self.assertEqual(a['trades'][0]['entry_date'],'2026-01-05')
        self.assertEqual(b['trades'][0]['reason'],'TP')

    def test_price_not_spread_stop(self):
        data=bars([110,111,112,113,105,104],[100,100,100,100,90,89],
                  [110,111,112,113,113,104])
        r=simulate(data)
        self.assertEqual(r['trades'][0]['reason'],'SL')
        self.assertAlmostEqual(r['net'],-9.2)
        self.assertAlmostEqual(r['mdd'],9.2)

    def test_far_uses_same_near_minus_far_signal(self):
        r=simulate(bars([110,109,108,107],[100]*4),leg='far')
        self.assertIsNone(r['pending'])

    def test_open_position_half_cost_only(self):
        r=simulate(bars([110,111,112,113,120],[100]*5,[110,111,112,113,115]))
        self.assertEqual(r['count'],0)
        self.assertAlmostEqual(r['total_mark'],4.9)
        self.assertEqual(r['pending']['action'],'exit')

    def test_no_future_liquidity_filter(self):
        data=bars([110,111,112,113,120],[100]*5)
        data[4]['far_volume']=0
        self.assertIsNotNone(simulate(data,liquid=True)['open_position'])
        data[3]['far_volume']=0
        self.assertIsNone(simulate(data,liquid=True)['open_position'])

    def test_missing_selected_open_cancels_only_selected(self):
        data=bars([110,111,112,113,120],[100]*5)
        data[4]['far_open']=''
        self.assertIsNotNone(simulate(data)['open_position'])
        self.assertEqual(simulate(data,leg='far')['flags']['cancelled_entry_missing_open'],1)

    def test_history_accounting_and_timing(self):
        for group in load().values():
            for leg in ('near','far'):
                r=simulate(group,leg=leg,liquid=True)
                extra=r['open_position']['net_mark_points'] if r['open_position'] else 0
                self.assertAlmostEqual(r['net']+extra,r['total_mark'])
                for t in r['trades']:
                    self.assertLess(t['signal_date'],t['entry_date'])
                    self.assertLess(t['exit_signal_date'],t['exit_date'])
                    self.assertAlmostEqual(t['exit_price']-t['entry_price']-.2,t['net_points'])


if __name__=='__main__':
    unittest.main()
