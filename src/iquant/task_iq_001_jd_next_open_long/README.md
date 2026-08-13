# TASK-IQ-001：JD2609 阳线后次 K 开盘买入

## 文件用途

- `strategy.py`：粘贴或导入国信 iQuant 的策略脚本。
- 完整需求：`requirements/TASK-IQ-001/v1.md`。
- 验收结果：`tests/TASK-IQ-001/expected_v1.md`。

## 策略摘要

当天日 K 收盘价大于开盘价时产生信号，在下一根日 K 的开盘价买入 1 手。策略仅用于回测，不应在实盘模式发送订单。

## iQuant 提供的接口

脚本依赖 iQuant 运行环境提供以下对象或函数，仓库本身不实现它们：

- `ContextInfo`
- `buy_open`
- `timetag_to_datetime`

## 版本定位

```bash
# 查看原始 v1.0 代码
git show task-iq-001-v1.0:src/iquant/task_iq_001_jd_next_open_long/strategy.py
```
