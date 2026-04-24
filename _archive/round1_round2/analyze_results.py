"""analyze_results.py
=====================
Top-level entrypoint shim for the results analyzer. Real implementation
lives in the ``results_analyzer/`` package; this file exists because the
project spec asked for a module literally named ``analyze_results.py``.

Usage:
    python analyze_results.py --log-path backtests/2026-04-13_02-32-38.log

Programmatic:
    from analyze_results import run_pipeline, ResultsConfig
    run_pipeline(ResultsConfig(log_path='backtests'))
"""
from __future__ import annotations

from results_analyzer import (Fill, MarketSnap, Order, PnlSnap, PositionSnap,
                              Run, SignalEvent, run_pipeline)
from results_analyzer.cli import main
from results_analyzer.config import ResultsConfig

__all__ = ["run_pipeline", "ResultsConfig", "Run", "Order", "Fill",
           "PositionSnap", "PnlSnap", "SignalEvent", "MarketSnap", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
