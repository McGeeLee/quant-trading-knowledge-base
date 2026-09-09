"""Daily, paired-leg research simulation. Not an execution engine.

Run from anywhere: python3 backtest_v2_pair.py
Cost is TOTAL pair round-trip points, half charged per entry/exit.
Daily open prices of different contracts are NOT necessarily simultaneous.
"""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-7


def number(row, key):
    try:
        x = float(row[key])
        return x if math.isfinite(x) else None
    except (ValueError, TypeError, KeyError):
        return None


def spread(row, field):
    a, b = number(row, 'near_' + field), number(row, 'far_' + field)
    return a - b if a is not None and b is not None and a > 0 and b > 0 else None


def simulate(rows, n=3, tp=5, sl=3, cost=0.4, liquid=False):
    assert n >= 1 and int(n) == n and min(tp, sl) > 0 and cost >= 0
    pending, position, previous, streak = None, None, None, 0
    cash, peak, mdd = 0., 0., 0.
    trades, equity, flags = [], [], defaultdict(int)
    last_mark = None
    for i, row in enumerate(rows):
        day, opening, closing = row['date'], spread(row, 'open'), spread(row, 'close')
        exited = False
        if pending and pending['action'] == 'exit':
            if opening is None:
                flags['delayed_exit_missing_open'] += 1
            else:
                near = number(row, 'near_open') - position['near_entry']
                far = position['far_entry'] - number(row, 'far_open')
                gross = near + far
                assert abs(gross - (opening - position['entry_spread'])) < EPS
                trades.append(dict(position, exit_date=day,
                    near_exit=number(row, 'near_open'), far_exit=number(row, 'far_open'),
                    exit_spread=opening, near_pnl=near, far_pnl=far,
                    gross_points=gross, net_points=gross-cost,
                    exit_signal_date=pending['date'], reason=pending['reason'],
                    holding_bars=i-position['entry_index']))
                cash += gross - cost/2
                pending, position, streak, exited = None, None, 0, True
        if pending and pending['action'] == 'entry':
            # A missing opening price cannot be invented. Cancel both hypothetical legs.
            if opening is None:
                flags['cancelled_entry_missing_open'] += 1
                exited = True
            else:
                position = dict(signal_date=pending['date'], entry_date=day,
                    entry_index=i, near_entry=number(row, 'near_open'),
                    far_entry=number(row, 'far_open'), entry_spread=opening)
                cash -= cost/2
                last_mark = opening
            pending, streak = None, 0
        if position:
            streak = 0
            if closing is not None:
                last_mark = closing
                pnl = closing - position['entry_spread']
                if pending is None and (pnl >= tp-EPS or pnl <= -sl+EPS):
                    pending = dict(action='exit', date=day, reason='TP' if pnl >= tp-EPS else 'SL')
            else:
                flags['stale_position_mark'] += 1
        elif not exited:
            streak = streak + 1 if closing is not None and previous is not None and closing > previous+EPS else 0
            # Only information available at the signal close. Never use next day's OI/volume.
            eligible = (not liquid or ((number(row, 'far_open_interest') or 0) >= 1000
                        and (number(row, 'near_volume') or 0) >= 100
                        and (number(row, 'far_volume') or 0) >= 100))
            if streak >= n and eligible:
                pending, streak = dict(action='entry', date=day), 0
            elif streak >= n:
                flags['filtered_signal_days'] += 1
        marked = cash + (last_mark - position['entry_spread'] if position else 0)
        peak = max(peak, marked)
        mdd = max(mdd, peak-marked)
        equity.append(dict(date=day, equity_points=marked, position=bool(position)))
        previous = closing
    gross = sum(t['gross_points'] for t in trades)
    net = sum(t['net_points'] for t in trades)
    opened = dict(position, mark_date=rows[-1]['date'], mark_spread=last_mark,
                  gross_points=last_mark-position['entry_spread'],
                  net_mark_points=last_mark-position['entry_spread']-cost/2) if position else None
    return dict(start=rows[0]['date'], end=rows[-1]['date'], days=len(rows), count=len(trades),
        wins=sum(t['net_points'] > EPS for t in trades), gross=gross, net=net,
        total_mark=equity[-1]['equity_points'], mdd=mdd, open_position=opened,
        pending=pending, flags=dict(flags), trades=trades, equity=equity)


def load():
    groups = defaultdict(list)
    with (ROOT/'data/sc_oct_nov_panel_2020_2026.csv').open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            groups[row['pair_year']].append(row)
    for rows in groups.values():
        rows.sort(key=lambda r:r['date'])
        assert len({r['date'] for r in rows}) == len(rows)
    return dict(sorted(groups.items()))


def main():
    groups = load()
    results = {}
    for label, liquid in [('raw', False), ('liquid', True)]:
        results[label] = {year:simulate(rows, liquid=liquid) for year, rows in groups.items()}
    sensitivity = []
    for n, tp, sl in [(2,5,3),(3,5,3),(4,5,3),(5,5,3),(3,4,3),(3,6,3),(3,5,2),(3,5,4)]:
        runs = [simulate(rows,n,tp,sl,liquid=True) for rows in groups.values()]
        sensitivity.append(dict(n=n,tp=tp,sl=sl,count=sum(r['count'] for r in runs),
            net=sum(r['net'] for r in runs),total_mark=sum(r['total_mark'] for r in runs),
            positive_years=sum(r['total_mark']>EPS for r in runs)))
    costs = []
    for cost in [0,0.2,0.4,0.8,1.0]:
        runs=[simulate(rows,cost=cost,liquid=True) for rows in groups.values()]
        costs.append(dict(cost=cost,net=sum(r['net'] for r in runs),
                         total_mark=sum(r['total_mark'] for r in runs)))
    out=ROOT/'output'
    payload=dict(method='daily close signal, next daily opens; non-synchronous ideal fills',
                 cost_roundtrip_points=0.4,results=results,sensitivity=sensitivity,costs=costs)
    (out/'v2_双腿回测明细_20260909.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 连涨做多价差：双腿日线回测（2026-09-09）','',
        '结论必须结合下方成交与样本限制理解；这是历史假设回测，不是可锁定利润的套利。','',
        '## 主要发现','',
        '- 原始规则：2026年7笔，扣假设成本后亏3.0点；跨年24笔已平仓净赚2.7点，但加2024年末未平仓净盯市亏损后，合计约0点。',
        '- 加信号日流动性过滤：2026年4笔，净赚4.5点；跨年14笔净赚10.6点、胜率42.9%，7个年份4盈3亏。',
        '- 盈利集中：2026年8月18日至9月1日一笔净赚14.7点；去掉这一笔，2026年为亏10.2点，全部年份合计为亏4.1点。这是集中度检查，不是建议删除交易。',
        '- 过滤版2026年日线最大回撤20.9点=20900元，明显大于该年最终净收益4500元。止损按日收盘触发，不是硬性最大损失限制。',
        '- 邻近参数结果不稳：连涨2次的含期末净盯市为−2.2点，5次为−6.7点；将止盈从5改成4点，结果为−11.6点。',
        '- 因此能找到历史盈利交易，但本次数据尚不能证明稳定、可实际成交的盈利优势。下一步应使用同一时间戳的两腿分钟或盘口数据，核对可成交价差。','',
        '## 规则与数据','',
        '- 每年固定10月/11月合约，近月收盘价减远月收盘价连续上涨3次（至少4个收盘价）后，下一交易日开盘多近月1手、空远月1手。',
        '- 合并价差相对实际模拟开仓价差上涨5点或下跌3点，在当天收盘触发，下一交易日开盘同时平仓。不加仓；退出当天不重新累计信号。',
        '- 数据完整时与已有MC v2时序一致。缺开盘价的处理是本研究额外约定：无法开仓则取消、无法平仓则延后，异常计数另列；不是MC报错后的真实执行行为。过滤版主参数没有发生这些缺价异常。',
        '- 输入为此前从上期能源公开日行情接口下载的1224条配对记录；2020年仅6月17日起，其余大体从前一年12月初至当年9月15日；2026年截至9月8日。不是各合约全生命周期。',
        '- 原始版不限制流动性。过滤版仅在信号日检查远月持仓≥1000手、两腿各自成交量≥100手；不拿次日持仓/成交量提前筛选。不限制已有持仓的退出。',
        '- 默认组合全程成本0.4点=400元（两腿开平共四次成交），入场和离场各扣一半；这是手续费与滑点的假设合计，未逐日复原历史收费。',
        '- 1点=每腿1手组合1000元。毛收益=(近月平仓−近月开仓)+(远月开仓−远月平仓)。',
        '- 期末未平仓按最后收盘价盯市，仅扣已发生的入场半程成本，不算作已完成交易；未假装在期末成交。',
        '- 回撤为各年独立组合、日收盘盯市净值回撤，包含未平仓盈亏，不能代表盘中最大回撤。未计算保证金、资金占用、利息或收益率。','']
    for label,title in [('raw','原始规则'),('liquid','增加信号日流动性过滤')]:
        lines += ['## '+title,'','单位：点；乘1000即人民币元。胜率为扣成本后的已平仓交易胜率。','',
                  '|年份|数据天数|已平仓笔数|胜率|已平仓毛收益|已平仓净收益|期末未平仓净盯市|合计净盯市|日线最大回撤|',
                  '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for y,r in results[label].items():
            op=r['open_position']
            lines.append(f"|{y}|{r['days']}|{r['count']}|{r['wins']/r['count']:.1%}|{r['gross']:.2f}|{r['net']:.2f}|{op['net_mark_points'] if op else 0:.2f}|{r['total_mark']:.2f}|{r['mdd']:.2f}|")
        rs=list(results[label].values())
        lines += ['',f"合计已平仓{sum(r['count'] for r in rs)}笔；已平仓净收益{sum(r['net'] for r in rs):.2f}点；加各样本期末净盯市后{sum(r['total_mark'] for r in rs):.2f}点。各年是独立研究区间，不构成完整连续投资曲线。",'']
        for y,r in results[label].items():
            if r['flags']: lines.append(f"- {y} 数据/过滤记录：{r['flags']}")
            if r['open_position']: lines.append(f"- {y} 期末未平仓：{r['open_position']}")
            if r['pending']: lines.append(f"- {y} 期末待执行信号：{r['pending']}")
        lines.append('')
    lines += ['## 成本敏感性（过滤版）','','|组合往返成本/点|已平仓净收益/点|含期末净盯市/点|','|---:|---:|---:|']
    lines += [f"|{r['cost']:.1f}|{r['net']:.2f}|{r['total_mark']:.2f}|" for r in costs]
    lines += ['','## 邻近参数（过滤版，成本0.4点）','','仅用于检查脆弱性，不据此挑选最优参数；不是未见样本验证。','',
              '|连涨次数|止盈|止损|已平仓笔数|已平仓净收益|含期末净盯市|净盯市正收益年份|','|---:|---:|---:|---:|---:|---:|---:|']
    lines += [f"|{r['n']}|{r['tp']}|{r['sl']}|{r['count']}|{r['net']:.2f}|{r['total_mark']:.2f}|{r['positive_years']}/7|" for r in sensitivity]
    lines += ['','## 2026年过滤版逐笔交易','','|开仓日|平仓日|近月毛收益|远月毛收益|组合毛收益|组合净收益|退出触发|','|---|---|---:|---:|---:|---:|---|']
    for t in results['liquid']['2026']['trades']:
        lines.append(f"|{t['entry_date']}|{t['exit_date']}|{t['near_pnl']:.2f}|{t['far_pnl']:.2f}|{t['gross_points']:.2f}|{t['net_points']:.2f}|{t['reason']}|")
    lines += ['','## 不能忽略的限制','',
        '1. 两份合约的日开盘价可能来自不同时间，日线不能证明这两个价格可以同时成交。收盘价也可能不同步，早期远月尤其明显。过滤只能减少、不能消除该问题。',
        '2. 用日收盘信号、次日开盘平仓，止损3点不等于最大亏损3点；止盈触发后也可能因隔夜跳空变成亏损。没有用两个合约各自最高/最低价构造虚假可交易价差。',
        '3. 本样本只有每年的10月/11月组合，且窗口有限；小样本、价格异常、年份行情集中都可能导致回测失真。没有独立前瞻测试，不能视为稳定盈利证据。',
        '4. 没有模拟涨跌停排队、盘口容量、拒单、单腿成交、保证金不足或强平。每年窗口结束未平仓仅估值，不代表能持有到交割；实盘须额外实施到期和账户资格管理。',
        '5. 回测仅用于研究，未连接账户、未开自动交易；未在MC实际编译或核对报告。此前隔日进出研究的结果不适用于本次多日持有规则。','',
        '## 复现与来源','',
        '- 运行：`python3 研究/backtest_v2_pair.py`；完整逐笔、每日净值和待执行状态见同目录JSON。',
        '- [上期能源日行情接口示例](https://www.ine.cn/data/tradedata/future/dailydata/kx20260908.dat)。原始配对数据在`data/sc_oct_nov_panel_2020_2026.csv`。',
        '- [上期能源原油标准合约](https://www.ine.cn/products/futures/energyandchemical/sc_f/standard_sc_f/202312/t20231205_802540.html)：每手1000桶、报价元/桶。','']
    (out/'v2_连续上涨双腿组合回测_20260909.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({label:{y:{k:v for k,v in r.items() if k not in ('trades','equity')} for y,r in rs.items()} for label,rs in results.items()},ensure_ascii=False,indent=2))
    print('Sensitivity:',json.dumps(sensitivity,ensure_ascii=False))


if __name__=='__main__':
    main()
