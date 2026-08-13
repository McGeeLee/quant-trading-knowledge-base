# coding: gbk

CONTRACT = 'JD2609.DF'
END_DATE = '20260716'
FINAL_CLOSE = 4377.0
CONTRACT_MULTIPLIER = 10.0


def init(ContextInfo):
    ContextInfo.set_universe([CONTRACT])

    ContextInfo.start = '2026-07-01 00:00:00'
    ContextInfo.end = '2026-07-16 23:59:59'

    # A signal generated after today's close is filled at the next day's open.
    ContextInfo.pending_entry = False
    ContextInfo.entry_prices = []
    ContextInfo.result_printed = False


def handlebar(ContextInfo):
    # This assignment is backtest-only. Do not send orders in run/live mode.
    if not ContextInfo.do_back_test:
        return

    open_data = ContextInfo.get_history_data(1, '1d', 'open')
    close_data = ContextInfo.get_history_data(1, '1d', 'close')

    opens = open_data.get(CONTRACT, [])
    closes = close_data.get(CONTRACT, [])
    if not opens or not closes:
        return

    today_open = float(opens[-1])
    today_close = float(closes[-1])
    timetag = ContextInfo.get_bar_timetag(ContextInfo.barpos)
    trade_date = timetag_to_datetime(timetag, '%Y%m%d')

    # Record the theoretical fill of yesterday's signal at today's open.
    if ContextInfo.pending_entry:
        ContextInfo.entry_prices.append(today_open)
        print('ENTRY date=%s price=%.2f lots=1' % (trade_date, today_open))
        ContextInfo.pending_entry = False

    # Do not create an order after the last bar of this fixed test window.
    if trade_date < END_DATE and today_close > today_open:
        # In iQuant backtest mode, this signal is filled on the first tick of
        # the next daily bar, i.e. at the next trading day's opening price.
        buy_open(CONTRACT, 1, ContextInfo)
        ContextInfo.pending_entry = True
        print('SIGNAL date=%s open=%.2f close=%.2f' %
              (trade_date, today_open, today_close))

    # Keep all positions open and mark them at the 2026-07-16 close.
    if trade_date == END_DATE and not ContextInfo.result_printed:
        entry_count = len(ContextInfo.entry_prices)
        entry_sum = sum(ContextInfo.entry_prices)
        total_pnl = sum(
            (FINAL_CLOSE - price) * CONTRACT_MULTIPLIER
            for price in ContextInfo.entry_prices
        )

        print('FINAL entry_count=%d' % entry_count)
        print('FINAL entry_price_sum=%.2f' % entry_sum)
        print('FINAL close=%.2f multiplier=%.2f' %
              (FINAL_CLOSE, CONTRACT_MULTIPLIER))
        print('FINAL total_pnl=%.2f' % total_pnl)
        print('EXPECTED entry_count=5 total_pnl=-6420.00')

        ContextInfo.result_printed = True
