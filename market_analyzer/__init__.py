"""
market_analyzer
===============
Comprehensive research/analyzer system for IMC Prosperity 4.

Phase 1 (implemented): data loading, per-product market-structure features,
fair-value model comparison, reversion / signal / execution tests, benchmark
strategies with a unified simulator, parameter sweeps, plots, and per-product
markdown reports.

Phase 2 (stubbed): cross-product cointegration / lead-lag, regime detection,
robustness train/test splits.

Phase 3 (stubbed): baskets, options, conversions hooks in pipeline.

The old analyzer (`analyze.py` in the project root) is preserved as a fallback.
"""

from .pipeline import run_pipeline

__all__ = ["run_pipeline"]
__version__ = "0.1.0"
