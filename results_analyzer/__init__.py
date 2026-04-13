"""
results_analyzer
================
Post-run diagnostics and PnL attribution for IMC Prosperity 4 submissions.

Companion to ``market_analyzer/`` (market structure / strategy research).
This package answers: "What did my submitted bot actually do, what made or
lost money, and what should I change next?"

Phase 1 (implemented): log parsing, canonical schema, order lifecycle, fills,
position & PnL reconstruction, signal effectiveness, round-trip diagnostics,
plots, markdown + JSON reports.

Phase 2 (stubs): richer tag-level attribution, regime-conditioned perf.

Phase 3 (hooks): linkage to market_analyzer outputs.

Old analyzer (``analyze.py`` in project root) is untouched.
"""
from .pipeline import run_pipeline
from .schema import Fill, MarketSnap, Order, PnlSnap, PositionSnap, Run, SignalEvent

__all__ = ["run_pipeline", "Run", "Order", "Fill", "PositionSnap",
           "PnlSnap", "SignalEvent", "MarketSnap"]
__version__ = "0.1.0"
