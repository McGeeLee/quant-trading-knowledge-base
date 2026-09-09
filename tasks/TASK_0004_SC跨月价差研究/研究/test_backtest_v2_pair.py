import unittest
import random
from backtest_v2_pair import simulate, load
from test_v2_pair_signal import simulate as reference


def rows(closes, opens=None):
    opens=closes if opens is None else opens
    return [dict(date=f'2026-01-{i+1:02}', near_open=100+o,far_open=100,
                 near_close=100+c,far_close=100,far_open_interest=1000,
                 near_volume=100,far_volume=100) for i,(c,o) in enumerate(zip(closes,opens))]


class BacktestTests(unittest.TestCase):
    def test_cost_and_two_leg_accounting(self):
        r=simulate(rows([10,11,12,13,20,21],[10,11,12,13,15,22]))
        self.assertAlmostEqual(r['gross'],7)
        self.assertAlmostEqual(r['net'],6.6)
        self.assertAlmostEqual(r['total_mark'],6.6)
        self.assertAlmostEqual(r['equity'][4]['equity_points'],4.8)

    def test_open_position_not_closed(self):
        r=simulate(rows([10,11,12,13,20],[10,11,12,13,15]))
        self.assertEqual(r['count'],0)
        self.assertEqual(r['pending']['action'],'exit')
        self.assertAlmostEqual(r['total_mark'],4.8)

    def test_stop_gap_and_drawdown(self):
        r=simulate(rows([10,11,12,13,12,9],[10,11,12,13,15,9]))
        self.assertAlmostEqual(r['net'],-6.4)
        self.assertAlmostEqual(r['mdd'],6.4)

    def test_next_day_liquidity_not_used(self):
        data=rows([10,11,12,13,20,21],[10,11,12,13,15,22])
        data[4]['far_open_interest']=0
        data[4]['far_volume']=0
        self.assertEqual(simulate(data,liquid=True)['count'],1)
        data[3]['far_open_interest']=999
        self.assertEqual(simulate(data,liquid=True)['count'],0)

    def test_cancel_missing_entry_and_delay_missing_exit(self):
        data=rows([10,11,12,13,20,21,22],[10,11,12,13,15,22,23])
        data[5]['far_open']=''
        r=simulate(data)
        self.assertEqual(r['flags']['delayed_exit_missing_open'],1)
        self.assertAlmostEqual(r['net'],7.6)
        data[4]['far_open']=''
        self.assertEqual(simulate(data)['flags']['cancelled_entry_missing_open'],1)

    def test_random_valid_data_matches_mc_reference(self):
        rng=random.Random(26102611)
        for _ in range(100):
            closes=[rng.uniform(-10,30) for _ in range(200)]
            opens=[rng.uniform(-10,30) for _ in range(200)]
            data=rows(closes,opens)
            event,state=reference([(r['near_open'],r['far_open'],r['near_close'],r['far_close']) for r in data])
            expected=[e for e in event if e[0]=='exit']
            r=simulate(data,cost=0)
            self.assertEqual(len(expected),r['count'])
            self.assertAlmostEqual(sum(e[2] for e in expected),r['gross'])
            self.assertEqual(state in (2,3),r['open_position'] is not None)

    def test_real_data_identities(self):
        for group in load().values():
            r=simulate(group,liquid=True)
            self.assertFalse(r['flags'].get('delayed_exit_missing_open'))
            self.assertFalse(r['flags'].get('cancelled_entry_missing_open'))
            extra=r['open_position']['net_mark_points'] if r['open_position'] else 0
            self.assertAlmostEqual(r['total_mark'],r['net']+extra)
            for t in r['trades']:
                self.assertAlmostEqual(t['near_pnl']+t['far_pnl'],t['gross_points'])
                self.assertLess(t['signal_date'],t['entry_date'])
                self.assertLess(t['exit_signal_date'],t['exit_date'])


if __name__=='__main__':
    unittest.main()
