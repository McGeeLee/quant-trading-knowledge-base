"""Reusable building blocks for quantitative-trading research.

The package starts deliberately small. Stable logic should be moved here from
notebooks only after its assumptions and expected behavior are documented.
"""

from .metrics import (
    annualized_return,
    annualized_volatility,
    max_drawdown,
    sharpe_ratio,
)

__all__ = [
    "annualized_return",
    "annualized_volatility",
    "max_drawdown",
    "sharpe_ratio",
]

__version__ = "0.1.0"
