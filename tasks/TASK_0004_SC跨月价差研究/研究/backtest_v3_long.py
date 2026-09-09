"""V3: independent near-long versus far-long; spread streak is entry only."""
import json
from collections import defaultdict
from backtest_v2_pair import ROOT, EPS, load, number, spread


def simulate(rows, leg='near', n=3, tp=5, sl=3, cost=0.2, liquid=False):
    if leg not in ('near','far') or n < 1 or int(n)!=n or min(tp,sl)<=0 or cost<0:
        raise ValueError('Invalid parameters')
    previous, streak, pending, position = None, 0, None, None
    cash, peak, mdd, mark = 0., 0., 0., None
    trades, equity, flags = [], [], defaultdict(int)
    for i,row in enumerate(rows):
        day=row['date']
        opening=number(row,leg+'_open')
        closing=number(row,leg+'_close')
        opening=opening if opening is not None and opening>0 else None
        closing=closing if closing is not None and closing>0 else None
        signal_spread=spread(row,'close')
        exited=False
        if pending and pending['action']=='exit':
            if opening is None:
                flags['delayed_exit_missing_open']+=1
            else:
                gross=opening-position['entry_price']
                trades.append(dict(position,exit_date=day,exit_price=opening,
                    gross_points=gross,net_points=gross-cost,reason=pending['reason'],
                    exit_signal_date=pending['date'],holding_bars=i-position['entry_index']))
                cash+=gross-cost/2
                position,pending,streak,exited=None,None,0,True
        if pending and pending['action']=='entry':
            if opening is None:
                flags['cancelled_entry_missing_open']+=1
                exited=True
            else:
                position=dict(signal_date=pending['date'],entry_date=day,entry_index=i,entry_price=opening)
                cash-=cost/2
                mark=opening
            pending,streak=None,0
        if position:
            streak=0
            if closing is not None:
                mark=closing
                pnl=closing-position['entry_price']
                if pending is None and (pnl>=tp-EPS or pnl<=-sl+EPS):
                    pending=dict(action='exit',date=day,reason='TP' if pnl>=tp-EPS else 'SL')
            else:
                flags['stale_position_mark']+=1
        elif not exited:
            streak=streak+1 if signal_spread is not None and previous is not None and signal_spread>previous+EPS else 0
            eligible=not liquid or ((number(row,'far_open_interest') or 0)>=1000
                     and (number(row,'near_volume') or 0)>=100
                     and (number(row,'far_volume') or 0)>=100)
            if streak>=n and eligible:
                pending,streak=dict(action='entry',date=day),0
            elif streak>=n:
                flags['filtered_signal_days']+=1
        value=cash+(mark-position['entry_price'] if position else 0)
        peak=max(peak,value)
        mdd=max(mdd,peak-value)
        equity.append(dict(date=day,equity_points=value,position=bool(position)))
        previous=signal_spread
    opened=dict(position,mark_date=rows[-1]['date'],mark_price=mark,
                net_mark_points=mark-position['entry_price']-cost/2) if position else None
    return dict(start=rows[0]['date'],end=rows[-1]['date'],count=len(trades),
        wins=sum(t['net_points']>EPS for t in trades),gross=sum(t['gross_points'] for t in trades),
        net=sum(t['net_points'] for t in trades),total_mark=equity[-1]['equity_points'],
        mdd=mdd,open_position=opened,pending=pending,flags=dict(flags),trades=trades,equity=equity)


def main():
    groups=load()
    results={mode:{leg:{y:simulate(rows,leg=leg,liquid=liquid) for y,rows in groups.items()}
                   for leg in ('near','far')} for mode,liquid in [('raw',False),('liquid',True)]}
    sensitivity=[]
    for n,tp,sl in [(2,5,3),(3,5,3),(4,5,3),(3,4,3),(3,6,3),(3,5,2),(3,5,4)]:
        for leg in ('near','far'):
            rs=[simulate(rows,leg,n,tp,sl,liquid=True) for rows in groups.values()]
            sensitivity.append(dict(n=n,tp=tp,sl=sl,leg=leg,count=sum(r['count'] for r in rs),
                total_mark=sum(r['total_mark'] for r in rs)))
    costs=[]
    for cost in (0,0.2,0.4,0.8):
        costs.append(dict(cost=cost,**{leg:sum(simulate(rows,leg=leg,cost=cost,liquid=True)['total_mark']
                          for rows in groups.values()) for leg in ('near','far')}))
    out=ROOT/'output'
    (out/'v3_近月多_vs_远月多_明细.json').write_text(json.dumps(dict(results=results,sensitivity=sensitivity,costs=costs),ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# v3：价差连涨三日，近月做多 vs 远月做多','',
        '## 口径','',
        '- 两个独立策略，不开空单、不对冲、不同时买两腿。入场信号均为近月收盘−远月收盘连续上涨3次，至少需要4个收盘。',
        '- 信号日后下一交易日开盘买入各自合约1手；各自价格相对入场价上涨5点/下跌3点，在收盘触发退出、下一交易日开盘卖出。不再按价差退出。',
        '- 各策略持仓期间不累计连涨次数；平仓当天不重新入场，之后重新累计。因此两策略成交日期和交易笔数可能不同，本表比较独立策略，不是逐笔同持有期的合约强弱检验。',
        '- 单腿往返假设成本0.2点=200元，入场/退出各扣一半；原v2双腿为0.4点。不是已核实的逐日真实佣金或滑点。',
        '- 原始规则不加流动性筛选；附加过滤版与前次研究相同，仅信号日远月持仓≥1000、两腿成交各≥100。不使用次日信息决定今天发单。MC代码对应原始规则，过滤版仅Python研究。',
        '- 沿用2020—2026年10月/11月合约1224个配对日，2020仅6月17日起，其余从前一年12月初起；历史年份截至9月15日附近，2026截至9月8日。没有新增未来行情。',
        '- 期末未平仓按最后收盘盯市、仅扣入场成本；未假设期末平仓。各年为独立窗口，合计不是完整连续可投资账户。',
        '- 以下金额单位为元，每手1000桶。回撤是各年份内部日线盯市最大回撤，不代表盘中最大损失；不提供保证金收益率。','']
    for mode,title in [('raw','原始规则（对应MC v3）'),('liquid','附加流动性过滤（研究对照）')]:
        lines+=['## '+title,'','|年份|近月笔数|近月净收益含盯市|近月日线回撤|远月笔数|远月净收益含盯市|远月日线回撤|','|---|---:|---:|---:|---:|---:|---:|']
        for y in groups:
            a,b=results[mode]['near'][y],results[mode]['far'][y]
            lines.append(f"|{y}|{a['count']}|{a['total_mark']*1000:,.0f}|{a['mdd']*1000:,.0f}|{b['count']}|{b['total_mark']*1000:,.0f}|{b['mdd']*1000:,.0f}|")
        for leg in ('near','far'):
            rs=list(results[mode][leg].values());ts=[t for r in rs for t in r['trades']]
            total=sum(r['total_mark'] for r in rs)
            lines+=['',f"{'近月' if leg=='near' else '远月'}：已平仓{len(ts)}笔，净胜率{sum(r['wins'] for r in rs)/len(ts):.1%}；已平仓净收益{sum(r['net'] for r in rs)*1000:,.0f}元；含期末净盯市合计{total*1000:,.0f}元；正收益年份{sum(r['total_mark']>EPS for r in rs)}/7。"]
            for y,r in results[mode][leg].items():
                anomalies={k:v for k,v in r['flags'].items() if k!='filtered_signal_days'}
                if anomalies: lines.append(f"- {y}缺价处理：{anomalies}")
                if r['open_position']: lines.append(f"- {y}期末未平仓：{r['open_position']}")
                if r['pending']: lines.append(f"- {y}待执行信号：{r['pending']}")
        lines.append('')
    lines+=['## 邻近参数（过滤版，元）','','不据此选最优参数，不是样本外验证。','','|连涨|止盈|止损|合约|笔数|净收益含盯市|','|---:|---:|---:|---|---:|---:|']
    for r in sensitivity: lines.append(f"|{r['n']}|{r['tp']}|{r['sl']}|{r['leg']}|{r['count']}|{r['total_mark']*1000:,.0f}|")
    lines+=['','## 单腿往返成本敏感性（过滤版，元）','','|每笔假设成本|近月合计净盯市|远月合计净盯市|','|---:|---:|---:|']
    for r in costs: lines.append(f"|{r['cost']*1000:.0f}|{r['near']*1000:,.0f}|{r['far']*1000:,.0f}|")
    lines+=['','## 2026原始规则逐笔（元）','','|合约|信号日|开仓日|平仓日|开仓价|平仓价|净收益|退出触发|','|---|---|---|---|---:|---:|---:|---|']
    for leg in ('near','far'):
        for t in results['raw'][leg]['2026']['trades']:
            lines.append(f"|{leg}|{t['signal_date']}|{t['entry_date']}|{t['exit_date']}|{t['entry_price']:.1f}|{t['exit_price']:.1f}|{t['net_points']*1000:,.0f}|{t['reason']}|")
    lines+=['','## 边界与复现','',
        '- 日线价差仍可能由不同步或不活跃的收盘价形成。单腿开盘价也不保证能成交；没有模拟盘口、涨跌停排队、资金/到期强平。',
        '- 止盈止损是收盘阈值，不是硬性获利或最大亏损。原油单腿风险明显不同于对冲组合，不可按价差风险预期单腿损失。',
        '- Python缺开盘价时取消入场/延后退出；缺持仓收盘价沿用上一有效估值；缺信号价差则断开连涨。MC遇数据缺口或持仓异常会报错而不是继续，故缺价区间不可声称完全对应MC。',
        '- 运行 `python3 研究/backtest_v3_long.py`。JSON包含所有逐笔和每日净值。MC尚未实际编译或回测，Python结果不能冒充MC验收。',
        '- [上期能源日行情来源](https://www.ine.cn/data/tradedata/future/dailydata/kx20260908.dat)',
        '- [MultiCharts订单与次根K线说明](https://www.multicharts.cn/post?idno=169)','']
    (out/'v3_近月多_vs_远月多_报告.md').write_text('\n'.join(lines),encoding='utf-8')
    for mode in results:
        for leg,years in results[mode].items():
            print(mode,leg,json.dumps({y:{k:r[k] for k in ('count','net','total_mark','mdd','flags')} for y,r in years.items()}))


if __name__=='__main__':
    main()
