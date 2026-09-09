"""Synthetic acceptance tests for v2's daily pair model, not an MC compiler.

Run: python3 -m unittest discover -s <this directory> -p test_v2_pair_signal.py
Rows are (near_open, far_open, near_close, far_close). No historical data needed.
"""

import unittest


def simulate(rows, up_days=3, sp=5, sl=3, near_is_data1=True):
    if up_days < 1 or up_days != int(up_days) or min(sp, sl) <= 0:
        raise ValueError("Invalid parameters")
    state, count, previous, entry, entry_legs = 0, 0, None, None, None
    events = []
    for day, (o1, o2, c1, c2) in enumerate(rows):
        no, fo, nc, fc = (o1, o2, c1, c2) if near_is_data1 else (o2, o1, c2, c1)
        opening, closing = no - fo, nc - fc
        exited = False
        if state == 3:
            near_pnl, far_pnl = no - entry_legs[0], entry_legs[1] - fo
            events.append(("exit", day, opening - entry, near_pnl, far_pnl))
            state, count, exited = 0, 0, True
        if state == 1:
            entry, entry_legs, state = opening, (no, fo), 2
            events.append(("entry", day, opening))
        if state == 2:
            count = 0
            points = closing - entry
            if points >= sp - 1e-7:
                state = 3
                events.append(("tp", day, points))
            elif points <= -sl + 1e-7:
                state = 3
                events.append(("sl", day, points))
        elif state == 0 and not exited:
            count = count + 1 if previous is not None and closing > previous + 1e-7 else 0
            if count >= up_days:
                state, count = 1, 0
                events.append(("signal", day, closing))
        previous = closing
    return events, state


def bars(closes, opens=None):
    opens = closes if opens is None else opens
    return [(100 + o, 100, 100 + c, 100) for o, c in zip(opens, closes)]


class PairSignalTests(unittest.TestCase):
    def test_three_increases_need_four_closes_then_next_open(self):
        events, state = simulate(bars([10, 11, 12, 13]))
        self.assertEqual(events, [("signal", 3, 13)])
        self.assertEqual(state, 1)  # Last-bar pending order is not a fill.

    def test_profit_uses_entry_open_and_exits_next_open(self):
        events, state = simulate(bars([10, 11, 12, 13, 20, 21], [10, 11, 12, 13, 15, 22]))
        self.assertEqual(events, [("signal", 3, 13), ("entry", 4, 15),
                                  ("tp", 4, 5), ("exit", 5, 7, 7, 0)])
        self.assertEqual(state, 0)

    def test_stop_gap_exceeds_threshold(self):
        events, _ = simulate(bars([10, 11, 12, 13, 12, 9], [10, 11, 12, 13, 15, 9]))
        self.assertIn(("sl", 4, -3), events)
        self.assertEqual(events[-1], ("exit", 5, -6, -6, 0))

    def test_flat_and_falling_days_reset_streak(self):
        events, _ = simulate(bars([10, 11, 11, 12, 10, 11, 12]))
        self.assertEqual(events, [])

    def test_no_pyramiding_or_early_reentry(self):
        rows = bars([10, 11, 12, 13, 20, 21, 22, 23, 24, 25],
                    [10, 11, 12, 13, 15, 21, 22, 23, 24, 25])
        events, _ = simulate(rows)
        self.assertEqual([e[1] for e in events if e[0] == "signal"], [3, 8])
        self.assertEqual([e[1] for e in events if e[0] == "entry"], [4, 9])

    def test_swapped_charts_have_identical_pair_events(self):
        rows = bars([10, 11, 12, 13, 20, 21], [10, 11, 12, 13, 15, 22])
        swapped = [(fo, no, fc, nc) for no, fo, nc, fc in rows]
        self.assertEqual(simulate(rows), simulate(swapped, near_is_data1=False))

    def test_two_leg_pnl_adds_to_spread_change(self):
        rows = bars([10, 11, 12, 13]) + [(120, 105, 135, 115), (140, 118, 141, 119)]
        events, _ = simulate(rows)
        self.assertEqual(events[-1], ("exit", 5, 7, 20, -13))
        self.assertEqual(events[-1][2], sum(events[-1][3:]))

    def test_pending_exit_stays_open_without_next_bar(self):
        events, state = simulate(bars([10, 11, 12, 13, 20], [10, 11, 12, 13, 15]))
        self.assertEqual(state, 3)
        self.assertFalse(any(e[0] == "exit" for e in events))

    def test_decimal_streak_and_threshold(self):
        events, _ = simulate(bars([0.1, 0.2, 0.3, 0.4, 0.9],
                                  [0.1, 0.2, 0.3, 0.4, 0.4]), sp=0.5)
        self.assertTrue(any(e[0] == "tp" for e in events))

    def test_invalid_parameters(self):
        for kwargs in ({"up_days": 0}, {"up_days": 1.5}, {"sp": 0}, {"sl": -1}):
            with self.assertRaises(ValueError):
                simulate([], **kwargs)


if __name__ == "__main__":
    unittest.main()
