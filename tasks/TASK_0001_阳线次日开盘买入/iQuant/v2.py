# coding: gbk

"""TASK_0001 v2: buy one futures lot at the next bar open.

The instrument, backtest dates and adjustment mode are configured in the
QMT/iQuant panel. The strategy explicitly reads daily bars. This script does
not close positions or calculate PnL. QMT/iQuant keeps the positions open and
reports their value at the end of the configured backtest window.
"""

ORDER_LOTS = 1


def init(ContextInfo):
    """Read the panel's default instrument and prepare its market data."""
    ContextInfo.contract = ContextInfo.stockcode + '.' + ContextInfo.market
    ContextInfo.set_universe([ContextInfo.contract])


def handlebar(ContextInfo):
    """Submit a long entry when the current daily bar closes above its open."""
    # This version is backtest-only. Never send orders in run/live mode.
    if not ContextInfo.do_back_test:
        return

    contract = ContextInfo.contract

    # Instrument, dates and adjustment mode follow panel settings.
    # Daily bars are part of this strategy's definition.
    open_data = ContextInfo.get_history_data(1, '1d', 'open')
    close_data = ContextInfo.get_history_data(1, '1d', 'close')

    opens = open_data.get(contract, [])
    closes = close_data.get(contract, [])
    if len(opens) == 0 or len(closes) == 0:
        return

    today_open = float(opens[-1])
    today_close = float(closes[-1])

    if today_close > today_open:
        timetag = ContextInfo.get_bar_timetag(ContextInfo.barpos)
        signal_date = timetag_to_datetime(timetag, '%Y%m%d')

        # Under the agreed daily-bar backtest model, this order is filled at
        # the next trading day's open. No next bar means no fill.
        buy_open(contract, ORDER_LOTS, ContextInfo)
        print('SIGNAL date=%s contract=%s open=%.2f close=%.2f lots=%d' %
              (signal_date, contract, today_open, today_close, ORDER_LOTS))
