# 可执行脚本

这里放“调用正式模块完成一项任务”的薄脚本，例如：

- `download_market_data.py`：下载并登记数据版本；
- `run_backtest.py`：读取配置并运行回测；
- `generate_report.py`：从结果生成研究报告。

计算逻辑不要直接堆在脚本里，应放入 `src/quant_trading/` 并接受测试。脚本负责解析参数、调用模块、记录输出位置和退出状态。
