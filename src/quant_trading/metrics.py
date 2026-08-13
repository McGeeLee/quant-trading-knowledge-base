"""Performance metrics for periodic simple returns.

All functions accept decimal simple returns, so 1% is written as ``0.01``.
Inputs must be finite and greater than -1. The module intentionally avoids
third-party dependencies so the initial learning project is easy to run.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable


def _validated_returns(period_returns: Iterable[float]) -> tuple[float, ...]:
    """Materialize and validate a non-empty series of simple returns."""
    values = tuple(float(value) for value in period_returns)
    if not values:
        raise ValueError("period_returns must not be empty")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("period_returns must contain only finite values")
    if any(value <= -1.0 for value in values):
        raise ValueError("simple returns must be greater than -1")
    return values


def _validated_periods_per_year(periods_per_year: int) -> int:
    """Validate the annualization frequency and return it unchanged."""
    if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int):
        raise TypeError("periods_per_year must be an integer")
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    return periods_per_year


def annualized_return(
    period_returns: Iterable[float], periods_per_year: int = 252
) -> float:
    """Return the geometrically annualized return.

    ``periods_per_year`` should match the input frequency: commonly 252 for
    daily trading data, 52 for weekly data, and 12 for monthly data.
    """
    values = _validated_returns(period_returns)
    frequency = _validated_periods_per_year(periods_per_year)
    total_growth = math.prod(1.0 + value for value in values)
    return total_growth ** (frequency / len(values)) - 1.0


def annualized_volatility(
    period_returns: Iterable[float], periods_per_year: int = 252
) -> float:
    """Return sample volatility annualized by the square-root-of-time rule."""
    values = _validated_returns(period_returns)
    frequency = _validated_periods_per_year(periods_per_year)
    if len(values) < 2:
        raise ValueError("at least two returns are required for volatility")
    return statistics.stdev(values) * math.sqrt(frequency)


def sharpe_ratio(
    period_returns: Iterable[float],
    periods_per_year: int = 252,
    annual_risk_free_rate: float = 0.0,
) -> float:
    """Return the annualized Sharpe ratio based on periodic excess returns.

    The annual risk-free rate is converted to the matching periodic compound
    rate. A zero-volatility input has no defined Sharpe ratio and raises an
    explicit error instead of returning infinity.
    """
    values = _validated_returns(period_returns)
    frequency = _validated_periods_per_year(periods_per_year)
    if len(values) < 2:
        raise ValueError("at least two returns are required for a Sharpe ratio")
    if not math.isfinite(annual_risk_free_rate) or annual_risk_free_rate <= -1.0:
        raise ValueError("annual_risk_free_rate must be finite and greater than -1")

    periodic_risk_free_rate = (1.0 + annual_risk_free_rate) ** (1.0 / frequency) - 1.0
    excess_returns = tuple(value - periodic_risk_free_rate for value in values)
    volatility = statistics.stdev(excess_returns)
    if volatility == 0.0:
        raise ValueError("Sharpe ratio is undefined when volatility is zero")
    return statistics.mean(excess_returns) / volatility * math.sqrt(frequency)


def max_drawdown(period_returns: Iterable[float]) -> float:
    """Return the worst peak-to-trough drawdown as a non-positive decimal."""
    values = _validated_returns(period_returns)
    wealth = 1.0
    peak = 1.0
    worst_drawdown = 0.0

    for period_return in values:
        wealth *= 1.0 + period_return
        peak = max(peak, wealth)
        worst_drawdown = min(worst_drawdown, wealth / peak - 1.0)

    return worst_drawdown
