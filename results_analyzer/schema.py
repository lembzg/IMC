"""
schema.py
---------
Canonical internal schema. Every parser must emit these types so all
downstream analysis modules are format-agnostic.

Trading decision informed: if a new log format ships (different round,
different engine version), we write one parser and nothing else changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd


# --- Atomic events ---------------------------------------------------------

@dataclass
class Order:
    """A quote or market order the bot emitted.

    ``side``: +1 buy, -1 sell.
    ``kind``: "quote" (passive) or "take" (aggressive/market). Parser infers.
    ``tag``: free-form strategy tag (e.g. "mm_bid", "zscore_buy"). Optional.
    """
    ts: int
    product: str
    side: int
    price: float
    size: int
    kind: str = "quote"
    tag: Optional[str] = None


@dataclass
class Fill:
    """An executed trade belonging to our bot."""
    ts: int
    product: str
    side: int          # +1 we bought, -1 we sold
    price: float
    size: int
    counterparty: Optional[str] = None
    tag: Optional[str] = None


@dataclass
class PositionSnap:
    ts: int
    product: str
    position: int


@dataclass
class PnlSnap:
    """Snapshot of PnL components. Any field may be NaN if inferred only."""
    ts: int
    product: str
    realized: float
    unrealized: float
    total: float


@dataclass
class SignalEvent:
    """Named signal value at a given timestamp (e.g. Z, OBI, SHIFT, EMA)."""
    ts: int
    product: str
    name: str
    value: float


@dataclass
class MarketSnap:
    """Per-tick per-product market state from the activities log, if present.

    Used by execution_analysis (adverse selection) and trade_diagnostics
    (MFE/MAE) without depending on a parallel market data file.
    """
    ts: int
    product: str
    best_bid: Optional[float]
    best_ask: Optional[float]
    mid: Optional[float]


# --- Run container ---------------------------------------------------------

@dataclass
class Run:
    """Everything parsed from a single log bundle."""
    run_id: str
    source_path: str
    products: List[str] = field(default_factory=list)
    orders: List[Order] = field(default_factory=list)
    fills: List[Fill] = field(default_factory=list)
    positions: List[PositionSnap] = field(default_factory=list)
    pnl: List[PnlSnap] = field(default_factory=list)
    signals: List[SignalEvent] = field(default_factory=list)
    market: List[MarketSnap] = field(default_factory=list)
    meta: Dict = field(default_factory=dict)

    # --- convenience DataFrames (materialised lazily in the pipeline) -----

    def orders_df(self) -> pd.DataFrame:
        return _to_df(self.orders)

    def fills_df(self) -> pd.DataFrame:
        return _to_df(self.fills)

    def positions_df(self) -> pd.DataFrame:
        return _to_df(self.positions)

    def pnl_df(self) -> pd.DataFrame:
        return _to_df(self.pnl)

    def signals_df(self) -> pd.DataFrame:
        return _to_df(self.signals)

    def market_df(self) -> pd.DataFrame:
        return _to_df(self.market)

    def has(self, section: str) -> bool:
        """Graceful-degradation helper — report layer queries this."""
        return bool(getattr(self, section))


def _to_df(items: List) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    return pd.DataFrame([i.__dict__ for i in items])
