# Quant Trading Code

个人量化交易代码仓库，只保存代码、测试和代码要求。

## 目录

```text
.
├── requirements/       # 每个任务、每个版本的完整要求
├── src/quant_trading/  # 可复用的通用量化代码
├── src/iquant/         # 国信 iQuant 策略代码
├── tests/              # 自动化测试和验收结果
├── CHANGELOG.md        # 版本变化记录
├── CODE_REQUIREMENTS.md
├── pyproject.toml
└── README.md
```

所有代码必须遵守 [CODE_REQUIREMENTS.md](CODE_REQUIREMENTS.md)。

## 运行测试

```bash
python3 -m unittest discover -s tests -v
```

## 本地安装

```bash
python3 -m pip install -e .
```

## 当前任务

- `TASK-IQ-001`：JD2609 阳线后次 K 开盘买入策略。
- 需求：[requirements/TASK-IQ-001/v1.md](requirements/TASK-IQ-001/v1.md)
- 代码：[src/iquant/task_iq_001_jd_next_open_long/](src/iquant/task_iq_001_jd_next_open_long/)
