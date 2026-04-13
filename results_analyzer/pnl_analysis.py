"""
pnl_analysis.py
---------------
Reconstruct realized & mark-to-market PnL from fills + market, and reconcile
against the authoritative PnL from the Activities log when present.

Inputs:  fills_df, market_df, pnl_df (from Activities log, optional).
Outputs: pnl_series_df(ts, product, realized, unrealized, total),
         summary (totals, drawdown, profit factor, win rate).

Trading decision informed:
  * Monotonically rising realized PnL with shrinking unrealized volatility
    -> strategy is healthy.
  * Realized PnL drifting down while unrealized swings wide -> risk taking
    that doesn't compound.
  * Attribution (take vs make) tells which engine part earns.
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd


def reconstruct_pnl(fills: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """Mark-to-mid running PnL per product.

    Realized PnL = cumulative cashflow from fills.
    Unrealized PnL = running position * mid.
    Total = realized + unrealized.
    """
    if fills.empty:
        return pd.DataFrame(columns=["ts", "product", "realized", "unrealized", "total"])

    rows = []
    for prod, f in fills.groupby("product"):
        f = f.sort_values("ts")
        # cash delta: buy (side=+1) costs price*size; sell (-1) earns price*size.
        cash_delta = -f["side"] * f["price"] * f["size"]
        realized = cash_delta.cumsum().values
        pos = (f["side"] * f["size"]).cumsum().values
        fill_pnl = pd.DataFrame({
            "ts": f["ts"].values,
            "product": prod,
            "realized_at_fill": realized,
            "pos_at_fill": pos,
        })
        # Build per-tick series by merging with market mids for this product.
        if not market.empty:
            m = market[market["product"] == prod][["ts", "mid"]].sort_values("ts")
            merged = m.merge(fill_pnl, on="ts", how="left")
            merged["realized"] = merged["realized_at_fill"].ffill().fillna(0.0)
            merged["position"] = merged["pos_at_fill"].ffill().fillna(0).astype(float)
            merged["unrealized"] = merged["position"] * merged["mid"]
            merged["total"] = merged["realized"] + merged["unrealized"]
            merged["product"] = prod
            rows.append(merged[["ts", "product", "realized", "unrealized", "total"]])
        else:
            # No market mid: only know realized at fill timestamps.
            fill_pnl["realized"] = fill_pnl["realized_at_fill"]
            fill_pnl["unrealized"] = np.nan
            fill_pnl["total"] = fill_pnl["realized"]
            rows.append(fill_pnl[["ts", "product", "realized", "unrealized", "total"]])

    return pd.concat(rows, ignore_index=True)


def pnl_summary(pnl_series: pd.DataFrame, fills: pd.DataFrame) -> Dict[str, Dict]:
    """Per-product summary. ``fills`` used for win rate and profit factor."""
    out: Dict[str, Dict] = {}
    if pnl_series.empty:
        return out
    for prod, g in pnl_series.groupby("product"):
        g = g.sort_values("ts")
        total = g["total"].astype(float).values
        realized = g["realized"].astype(float).values
        running_max = np.maximum.accumulate(total)
        drawdown = (total - running_max)
        out[prod] = {
            "final_total_pnl": float(total[-1]) if len(total) else 0.0,
            "final_realized": float(realized[-1]) if len(realized) else 0.0,
            "final_unrealized": float(total[-1] - realized[-1]) if len(total) else 0.0,
            "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0,
            "peak_total_pnl": float(total.max()) if len(total) else 0.0,
        }
    # Win rate + profit factor via per-fill signed cashflow.
    if not fills.empty:
        for prod, f in fills.groupby("product"):
            f_sorted = f.sort_values("ts")
            cash = (-f_sorted["side"] * f_sorted["price"] * f_sorted["size"]).values
            wins = cash[cash > 0]
            losses = cash[cash < 0]
            out.setdefault(prod, {})
            out[prod]["n_fills"] = int(len(f_sorted))
            out[prod]["fill_win_rate"] = float((cash > 0).mean()) if len(cash) else 0.0
            out[prod]["profit_factor"] = float(wins.sum() / abs(losses.sum())) \
                if len(losses) and losses.sum() != 0 else float("inf")
    return out


def authoritative_pnl(pnl_snaps: pd.DataFrame) -> pd.DataFrame:
    """Pivot authoritative PnL from Activities log (wide by product).

    Decision: treat this as ground truth for totals; reconstructed PnL is used
    for decomposition (realized vs unrealized) the authoritative row doesn't
    give us.
    """
    if pnl_snaps.empty:
        return pd.DataFrame()
    return pnl_snaps.pivot_table(index="ts", columns="product",
                                 values="total", aggfunc="last").sort_index()


def attribution_by_tag(fills: pd.DataFrame) -> pd.DataFrame:
    """PnL attribution by fill ``tag`` (if trader emits tags). FIFO-free proxy:
    uses signed cashflow per fill — interpret as 'cash earned or spent per
    order reason'.

    Decision informed: highlights which order tags net-contribute. If your
    trader doesn't emit tags, see the trader snippet in the final report.
    """
    if fills.empty or "tag" not in fills or fills["tag"].isna().all():
        return pd.DataFrame()
    f = fills.copy()
    f["cash"] = -f["side"] * f["price"] * f["size"]
    g = f.groupby(["product", "tag"], dropna=False).agg(
        n=("size", "count"), qty=("size", "sum"), cash=("cash", "sum")
    ).reset_index()
    return g.sort_values("cash", ascending=False)
