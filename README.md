# Quant Trading Code

个人量化交易代码仓库，只保存代码、测试和代码要求。

## 目录

```text
.
├── src/quant_trading/  # 正式 Python 代码
├── tests/              # 自动化测试
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
