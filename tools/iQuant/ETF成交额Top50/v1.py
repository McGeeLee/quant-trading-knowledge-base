#coding:gbk

# QMT daily backtest scanner: rank ETFs by daily turnover (amount).
#
# This is a signal/scanner model. It never sends an order.
# Run it on a DAILY chart. The ranking for date T is known after T closes,
# so it may only be used for trading from the next trading day.

import datetime

BENCHMARK = '000300.SH'
FUND_SECTOR = '\u6caa\u6df1\u57fa\u91d1'
TOP_N = 50

# Empty string: print every backtest day.
# Example: '20260811' prints detailed rows only for that date.
PRINT_DATE = ''

# Shanghai ETF code families. Shenzhen listed ETFs use 159xxx.
# The name check below is also kept as a fallback for future code families.
SH_ETF_PREFIXES = (
    '510', '511', '512', '513', '514', '515', '516', '517',
    '518', '520', '521', '522', '523',
    '560', '561', '562', '563',
    '588', '589'
)

STATE = {}


def init(ContextInfo):
    global STATE

    ContextInfo.set_universe([BENCHMARK])
    STATE = {
        'last_date': '',
        'previous_date': '',
        'previous_top50': [],
        'name_cache': {},
        'fallback_warned': False,
        'data_fallback_warned': False,
        'empty_daily_warned': False,
        'full_tick_warned': False,
        'days_scanned': 0,
        'current_etf_count': 0,
        'data_source': 'NONE'
    }

    print(
        'ETF TOP50 AMOUNT START BENCHMARK=%s SECTOR=%s TOP_N=%d '
        'PERIOD=1D FIELD=AMOUNT'
        % (BENCHMARK, FUND_SECTOR, TOP_N)
    )
    print(
        'NOTICE: DATE T RANKING IS AVAILABLE AFTER DATE T CLOSE; '
        'USE IT FROM THE NEXT TRADING DAY.'
    )


def get_trade_date(ContextInfo):
    timetag = ContextInfo.get_bar_timetag(ContextInfo.barpos)
    trade_date = timetag_to_datetime(timetag, '%Y%m%d')
    return timetag, trade_date


def get_instrument_name(ContextInfo, stock_code):
    cache = STATE['name_cache']
    if stock_code in cache:
        return cache[stock_code]

    name = ''
    detail = None

    try:
        detail = ContextInfo.get_instrument_detail(stock_code)
    except Exception:
        try:
            detail = ContextInfo.get_instrumentdetail(stock_code)
        except Exception:
            detail = None

    if isinstance(detail, dict):
        name = detail.get('InstrumentName', '')

    if not name:
        try:
            name = ContextInfo.get_stock_name(stock_code)
        except Exception:
            name = ''

    if name is None:
        name = ''

    name = str(name)
    cache[stock_code] = name
    return name


def is_etf(ContextInfo, stock_code):
    symbol = str(stock_code).upper()
    raw_code = symbol.split('.')[0]
    market = symbol.split('.')[-1] if '.' in symbol else ''

    if market == 'SZ' and raw_code.startswith('159'):
        return True

    if market == 'SH' and raw_code.startswith(SH_ETF_PREFIXES):
        return True

    # Fallback for a future exchange code family.
    name = get_instrument_name(ContextInfo, symbol).upper()
    return 'ETF' in name


def get_etf_universe(ContextInfo, timetag):
    codes = []
    universe_mode = 'HISTORICAL'

    try:
        codes = ContextInfo.get_stock_list_in_sector(
            FUND_SECTOR,
            timetag
        )
    except Exception:
        codes = []

    if not codes:
        universe_mode = 'CURRENT_FALLBACK'
        try:
            codes = ContextInfo.get_stock_list_in_sector(FUND_SECTOR)
        except Exception:
            codes = []

        if not STATE['fallback_warned']:
            print(
                'WARNING: HISTORICAL FUND MEMBERS WERE NOT AVAILABLE. '
                'CURRENT FUND LIST IS USED; OLD BACKTESTS MAY HAVE '
                'SURVIVORSHIP BIAS.'
            )
            STATE['fallback_warned'] = True

    unique_codes = []
    seen = set()

    for stock_code in codes:
        symbol = str(stock_code).upper()
        if symbol in seen:
            continue
        seen.add(symbol)

        if is_etf(ContextInfo, symbol):
            unique_codes.append(symbol)

    return unique_codes, universe_mode


def normalized_index_date(index_value):
    try:
        return index_value.strftime('%Y%m%d')
    except Exception:
        pass

    text = str(index_value)
    digits = ''.join([char for char in text if char.isdigit()])
    if len(digits) >= 8:
        return digits[:8]
    return ''


def valid_amount(raw_value):
    try:
        value = float(raw_value)
    except Exception:
        return None

    # NaN is the only ordinary float that is not equal to itself.
    if value != value or value <= 0.0:
        return None
    return value


def extract_amount_from_ex(data, stock_code, trade_date):
    if not isinstance(data, dict):
        return None

    frame = data.get(stock_code)
    if frame is None or len(frame) == 0:
        return None
    if 'amount' not in frame.columns:
        return None

    row_date = normalized_index_date(frame.index[-1])
    if row_date and row_date != trade_date:
        return None

    return valid_amount(frame['amount'].iloc[-1])


def get_amounts_with_ex(ContextInfo, etf_codes, trade_date):
    try:
        data = ContextInfo.get_market_data_ex(
            fields=['amount'],
            stock_code=etf_codes,
            period='1d',
            start_time=trade_date,
            end_time=trade_date,
            count=1,
            dividend_type='none',
            fill_data=False,
            subscribe=False
        )
    except TypeError:
        # Compatibility with QMT builds that have no subscribe parameter.
        data = ContextInfo.get_market_data_ex(
            fields=['amount'],
            stock_code=etf_codes,
            period='1d',
            start_time=trade_date,
            end_time=trade_date,
            count=1,
            dividend_type='none',
            fill_data=False
        )

    result = []
    for stock_code in etf_codes:
        amount = extract_amount_from_ex(data, stock_code, trade_date)
        if amount is not None:
            result.append((stock_code, amount))
    return result


def get_amounts_with_old_api(ContextInfo, etf_codes, trade_date):
    data = ContextInfo.get_market_data(
        ['amount'],
        stock_code=etf_codes,
        start_time=trade_date,
        end_time=trade_date,
        skip_paused=False,
        period='1d',
        dividend_type='none',
        count=-1
    )

    result = []

    # Some older QMT/pandas builds return a Panel for multiple symbols.
    if hasattr(data, 'major_axis') and hasattr(data, 'minor_axis'):
        for stock_code in etf_codes:
            try:
                frame = data[stock_code]
                amount = valid_amount(frame['amount'].iloc[-1])
            except Exception:
                amount = None

            if amount is not None:
                result.append((stock_code, amount))
        return result

    if data is None or not hasattr(data, 'columns'):
        return result
    if 'amount' not in data.columns:
        return result

    amount_series = data['amount']
    for stock_code in etf_codes:
        try:
            amount = valid_amount(amount_series.loc[stock_code])
        except Exception:
            amount = None

        if amount is not None:
            result.append((stock_code, amount))
    return result


def get_amounts_with_full_tick(ContextInfo, etf_codes):
    result = []
    batch_size = 200

    for start_pos in range(0, len(etf_codes), batch_size):
        batch = etf_codes[start_pos:start_pos + batch_size]

        try:
            tick_data = ContextInfo.get_full_tick(batch)
        except Exception:
            tick_data = {}

        if not isinstance(tick_data, dict):
            continue

        for stock_code in batch:
            quote = tick_data.get(stock_code, {})
            if not isinstance(quote, dict):
                continue

            amount = valid_amount(quote.get('amount'))
            if amount is not None:
                result.append((stock_code, amount))

    return result


def get_daily_amounts(ContextInfo, etf_codes, trade_date):
    if not etf_codes:
        return []

    STATE['data_source'] = 'NONE'

    try:
        rows = get_amounts_with_ex(ContextInfo, etf_codes, trade_date)
        if rows:
            STATE['data_source'] = 'GET_MARKET_DATA_EX'
            return rows
    except Exception as error:
        if not STATE['data_fallback_warned']:
            print(
                'WARNING: GET_MARKET_DATA_EX FAILED: %s; '
                'TRYING OLD GET_MARKET_DATA.'
                % error
            )
            STATE['data_fallback_warned'] = True

    if not STATE['empty_daily_warned']:
        print(
            'WARNING: LOCAL DAILY DATA RETURNED ZERO VALID AMOUNTS; '
            'TRYING OLD DAILY API.'
        )
        STATE['empty_daily_warned'] = True

    try:
        rows = get_amounts_with_old_api(
            ContextInfo,
            etf_codes,
            trade_date
        )
        if rows:
            STATE['data_source'] = 'GET_MARKET_DATA'
            return rows
    except Exception as error:
        print('WARNING: OLD DAILY API FAILED: %s' % error)

    # The full-tick snapshot is current-day real-time data. Never use it for
    # an older backtest date, because that would introduce future data.
    today = datetime.datetime.now().strftime('%Y%m%d')
    if trade_date == today:
        rows = get_amounts_with_full_tick(ContextInfo, etf_codes)
        if rows:
            STATE['data_source'] = 'FULL_TICK_CURRENT_DAY'
            if not STATE['full_tick_warned']:
                print(
                    'NOTICE: CURRENT-DAY AMOUNT USES FULL-TICK SNAPSHOT. '
                    'THE FINAL RANKING IS VALID AFTER MARKET CLOSE.'
                )
                STATE['full_tick_warned'] = True
            return rows

    print(
        'ERROR: NO VALID ETF AMOUNT DATA DATE=%s. '
        'DOWNLOAD DAILY DATA FOR THE FUND SECTOR.'
        % trade_date
    )
    return []


def print_usable_list(trade_date):
    if not STATE['previous_top50']:
        print('USABLE_TODAY DATE=%s SOURCE=NONE COUNT=0' % trade_date)
        return

    print(
        'USABLE_TODAY DATE=%s SOURCE_DATE=%s COUNT=%d CODES=%s'
        % (
            trade_date,
            STATE['previous_date'],
            len(STATE['previous_top50']),
            ','.join(STATE['previous_top50'])
        )
    )


def print_ranking(
    ContextInfo,
    trade_date,
    universe_mode,
    valid_amount_count,
    ranked
):
    print(
        'TOP50_AMOUNT DATE=%s ETF_COUNT=%d VALID_AMOUNT_COUNT=%d '
        'UNIVERSE_MODE=%s DATA_SOURCE=%s'
        % (
            trade_date,
            STATE['current_etf_count'],
            valid_amount_count,
            universe_mode,
            STATE['data_source']
        )
    )

    print(
        'TOP50_AMOUNT_CODES DATE=%s CODES=%s'
        % (trade_date, ','.join([item[0] for item in ranked]))
    )

    for rank, item in enumerate(ranked, 1):
        stock_code, amount = item
        name = get_instrument_name(ContextInfo, stock_code)
        print(
            'RANK=%02d CODE=%s NAME=%s AMOUNT_YUAN=%.2f '
            'AMOUNT_YI=%.4f'
            % (
                rank,
                stock_code,
                name,
                amount,
                amount / 100000000.0
            )
        )


def handlebar(ContextInfo):
    timetag, trade_date = get_trade_date(ContextInfo)

    # Protect against repeated callbacks if the model is not on a daily chart.
    if trade_date == STATE['last_date']:
        return
    STATE['last_date'] = trade_date

    print_usable_list(trade_date)

    etf_codes, universe_mode = get_etf_universe(ContextInfo, timetag)
    STATE['current_etf_count'] = len(etf_codes)

    amount_rows = get_daily_amounts(
        ContextInfo,
        etf_codes,
        trade_date
    )
    amount_rows.sort(key=lambda item: (-item[1], item[0]))
    top50 = amount_rows[:TOP_N]

    if not PRINT_DATE or trade_date == PRINT_DATE:
        print_ranking(
            ContextInfo,
            trade_date,
            universe_mode,
            len(amount_rows),
            top50
        )

    # This is the only ranking that may be used on the next trading day.
    STATE['previous_date'] = trade_date
    STATE['previous_top50'] = [item[0] for item in top50]
    STATE['days_scanned'] += 1

    try:
        is_last_bar = ContextInfo.is_last_bar()
    except Exception:
        is_last_bar = False

    if is_last_bar:
        print(
            'ETF TOP50 AMOUNT FINISHED DAYS=%d LAST_DATE=%s '
            'LAST_COUNT=%d'
            % (
                STATE['days_scanned'],
                trade_date,
                len(top50)
            )
        )
