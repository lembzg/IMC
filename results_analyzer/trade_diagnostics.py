"""
trade_diagnostics.py
--------------------
FIFO round-trip reconstruction + MFE / MAE per round trip.

Inputs:  fills_df, market_df.
Outputs: round_trips DF (entry_ts, exit_ts, side, qty, entry_px, exit_px,
                          pnl, holding_ticks, mfe, mae).

Trading decision informed:
  * Large MAE relative to PnL -> stop logic missing or too wide.
  * Large MFE not captured -> exits too late or too early.
  * Holding time skewed long with negative PnL -> trapped inventory; size
    down or widen entry.
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Tuple

import numpy as np
import pandas as pd


def _fifo_match(fills: pd.DataFrame) -> pd.DataFrame:
    """FIFO match buys against sells per product → round trips."""
    rows = []
    for prod, f in fills.groupby("product"):
        f = f.sort_values("ts")
        long_q: Deque[Tuple[int, int, float]] = deque()   # (ts, remaining qty, price)
        short_q: Deque[Tuple[int, int, float]] = deque()
        for _, r in f.iterrows():
            ts, side, price, size = int(r["ts"]), int(r["side"]), float(r["price"]), int(r["size"])
            if side > 0:  # buy
                # match against open shorts first
                while size > 0 and short_q:
                    e_ts, e_qty, e_px = short_q[0]
                    take = min(size, e_qty)
                    pnl = (e_px - price) * take  # short opened at e_px, closed buying at price
                    rows.append({"product": prod, "entry_ts": e_ts, "exit_ts": ts,
                                 "side": -1, "qty": take, "entry_px": e_px,
                                 "exit_px": price, "pnl": pnl,
                                 "holding_ticks": (ts - e_ts) // 100})
                    size -= take
                    if e_qty == take:
                        short_q.popleft()
                    else:
                        short_q[0] = (e_ts, e_qty - take, e_px)
                if size > 0:
                    long_q.append((ts, size, price))
            else:  # sell
                while size > 0 and long_q:
                    e_ts, e_qty, e_px = long_q[0]
                    take = min(size, e_qty)
                    pnl = (price - e_px) * take
                    rows.append({"product": prod, "entry_ts": e_ts, "exit_ts": ts,
                                 "side": +1, "qty": take, "entry_px": e_px,
                                 "exit_px": price, "pnl": pnl,
                                 "holding_ticks": (ts - e_ts) // 100})
                    size -= take
                    if e_qty == take:
                        long_q.popleft()
                    else:
                        long_q[0] = (e_ts, e_qty - take, e_px)
                if size > 0:
                    short_q.append((ts, size, price))
    return pd.DataFrame(rows)


def round_trips(fills: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    if fills.empty:
        return pd.DataFrame()
    rt = _fifo_match(fills)
    if rt.empty or market.empty:
        return rt

    # Compute MFE / MAE in price units using mid between entry and exit.
    mfe, mae = [], []
    for _, row in rt.iterrows():
        m = market[(market["product"] == row["product"]) &
                   (market["ts"] >= row["entry_ts"]) &
                   (market["ts"] <= row["exit_ts"])]["mid"].dropna()
        if m.empty:
            mfe.append(float("nan")); mae.append(float("nan")); continue
        if row["side"] > 0:
            mfe.append(float((m.max() - row["entry_px"]) * row["qty"]))
            mae.append(float((m.min() - row["entry_px"]) * row["qty"]))
        else:
            mfe.append(float((row["entry_px"] - m.min()) * row["qty"]))
            mae.append(float((row["entry_px"] - m.max()) * row["qty"]))
    rt = rt.copy()
    rt["mfe"] = mfe
    rt["mae"] = mae
    return rt


def round_trip_summary(rt: pd.DataFrame) -> dict:
    if rt.empty:
        return {}
    out = {}
    for prod, g in rt.groupby("product"):
        out[prod] = {
            "n_round_trips": int(len(g)),
            "total_pnl": float(g["pnl"].sum()),
            "win_rate": float((g["pnl"] > 0).mean()),
            "avg_pnl": float(g["pnl"].mean()),
            "median_pnl": float(g["pnl"].median()),
            "avg_holding_ticks": float(g["holding_ticks"].mean()),
            "median_holding_ticks": float(g["holding_ticks"].median()),
            "avg_mfe": float(g["mfe"].mean()) if "mfe" in g else float("nan"),
            "avg_mae": float(g["mae"].mean()) if "mae" in g else float("nan"),
        }
    return out
