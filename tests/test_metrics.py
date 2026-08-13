"""Tests for the example performance-metrics module."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quant_trading.metrics import (  # noqa: E402
    annualized_return,
    annualized_volatility,
    max_drawdown,
    sharpe_ratio,
)


class MetricsTest(unittest.TestCase):
    def test_annualized_return_compounds_period_returns(self) -> None:
        result = annualized_return([0.01, 0.01], periods_per_year=2)
        self.assertAlmostEqual(result, 0.0201)

    def test_annualized_volatility_uses_sample_standard_deviation(self) -> None:
        result = annualized_volatility([0.01, -0.01], periods_per_year=2)
        self.assertAlmostEqual(result, 0.02)

    def test_sharpe_ratio_is_zero_for_zero_mean_returns(self) -> None:
        result = sharpe_ratio([0.01, -0.01], periods_per_year=2)
        self.assertTrue(math.isclose(result, 0.0, abs_tol=1e-15))

    def test_max_drawdown_tracks_compounded_wealth(self) -> None:
        result = max_drawdown([0.10, -0.20, 0.05])
        self.assertAlmostEqual(result, -0.20)

    def test_empty_returns_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            max_drawdown([])

    def test_total_loss_is_rejected_for_simple_returns(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than -1"):
            annualized_return([-1.0])


if __name__ == "__main__":
    unittest.main()
