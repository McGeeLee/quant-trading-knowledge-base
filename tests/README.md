# 自动化测试

测试目录与 `src/quant_trading/` 的模块对应。当前不依赖第三方库，可以直接运行：

```bash
python -m unittest discover -s tests -v
```

新增功能时至少覆盖：一个正常案例、一个边界案例和一个明确的错误输入案例。涉及时间序列时，还要检查没有使用未来数据。
