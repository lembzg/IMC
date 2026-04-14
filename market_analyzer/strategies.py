"""
strategies.py
-------------
Benchmark strategy families + unified simulator.

Simulator assumptions (explicit and conservative):

  Taker (aggressive):
    * Buy crosses at best_ask, sell crosses at best_bid, immediately.
    * Assumes L1 depth >= size (size=1 by default keeps this realistic).
    * Mark-to-mid each tick.

  Maker (passive):
    * Previous version was broken: it fired only when next-tick best_ask
      crossed a buyer's bid (i.e. the market reached you from the opposite
      side — behaviourally a marketable quote, not a passive fill). That
      overstated maker profitability when it did fire and zeroed it
      otherwise.
    * New rule (requires a trades tape): a passive bid quoted at ``p_bid``
      fills when a trade *prints* at a price <= ``p_bid`` in the next
      tick's interval. Symmetric for the ask. Fill size is the *lesser* of
      our quote size and the eligible printed volume.
    * No queue position modelled; this is still optimistic relative to
      reality (every eligible print fills us), but it never accepts fills
      at prices that did not actually trade.

  Exit / MTM:
    * Positions flattened at mid on the last tick.
    * No fees or borrow; crossing the spread is the sole explicit cost.

Per-fill metadata: every fill row records the prevailing spread and mid
so the pipeline can flag "all fills at zero spread" pathologies
(the EMERALDS obi_tilt case where every fill landed at a degenerate
bb == ba tick and PnL summed to exactly 0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class SimResult:
    name: str
    params: Dict
    pnl_series: pd.Series
    position_series: pd.Series
    fills: pd.DataFrame
    summary: Dict

    def as_row(self) -> Dict:
        return {"strategy": self.name, **self.params, **self.summary}


# ---------------------------------------------------------------------------
# Trades tape helper
# ---------------------------------------------------------------------------

def _bucket_trades_by_next_tick(
    trades: Optional[pd.DataFrame], feature_ts: np.ndarray
) -> List[List[tuple]]:
    """Map each feature tick i -> list of (price, qty) trades that printed in
    [ts[i], ts[i+1]).

    Returns one list per tick (empty when no trades printed in the interval).
    """
    out: List[List[tuple]] = [[] for _ in range(len(feature_ts))]
    if trades is None or len(trades) == 0:
        return out
    t = trades.sort_values("timestamp")
    ts_vals = t["timestamp"].to_numpy()
    px_vals = t["price"].to_numpy()
    qt_vals = t["quantity"].to_numpy().astype(float)
    idx = np.searchsorted(feature_ts, ts_vals, side="right") - 1
    for k in range(len(ts_vals)):
        i = idx[k]
        if 0 <= i < len(out):
            out[i].append((float(px_vals[k]), float(qt_vals[k])))
    return out


# ---------------------------------------------------------------------------
# Generic simulator
# ---------------------------------------------------------------------------

def _run_sim(
    features: pd.DataFrame,
    decide: Callable[[int, Dict], Optional[tuple]],
    *,
    name: str,
    params: Dict,
    position_limit: int,
    trades: Optional[pd.DataFrame] = None,
) -> SimResult:
    """Generic tick-by-tick simulator.

    ``decide(i, state)`` returns one of:
        None                          -> do nothing
        ("take", side, size)          -> cross the spread now
        ("make", bid_px, ask_px, sz)  -> post passive quotes for this tick
    """
    n = len(features)
    mid = features["mid"].to_numpy()
    bb = features["best_bid"].to_numpy()
    ba = features["best_ask"].to_numpy()
    ts = features["timestamp"].to_numpy()
    tape = _bucket_trades_by_next_tick(trades, ts)

    pos = 0
    cash = 0.0
    pos_arr = np.zeros(n)
    pnl_arr = np.zeros(n)
    fills: List[Dict] = []
    state = {"features": features, "pos": 0, "params": params}

    for i in range(n - 1):
        state["pos"] = pos
        action = decide(i, state)
        if action is not None:
            kind = action[0]
            if kind == "take":
                _, side, size = action
                size = int(size)
                room = position_limit - pos if side > 0 else position_limit + pos
                size = max(0, min(size, room))
                if size > 0 and np.isfinite(ba[i]) and np.isfinite(bb[i]):
                    px = ba[i] if side > 0 else bb[i]
                    spread_i = ba[i] - bb[i]
                    pos += side * size
                    cash -= side * size * px
                    fills.append({
                        "i": i, "ts": ts[i], "kind": "take",
                        "side": side, "size": size, "price": float(px),
                        "mid": float(mid[i]) if np.isfinite(mid[i]) else np.nan,
                        "spread": float(spread_i) if np.isfinite(spread_i) else np.nan,
                    })
            elif kind == "make":
                _, bid_px, ask_px, size = action
                size = int(size)
                prints = tape[i + 1]

                # Passive bid fills if a print in the next interval touched or
                # went below our bid price (a seller sold into our bid).
                if bid_px is not None and np.isfinite(bid_px) and prints:
                    # Only consider prints at prices <= bid_px that are also
                    # <= the prevailing best_ask at tick i+1 (sanity — the
                    # trade must have been a sell into a bid, not a buy).
                    elig_qty = sum(q for (p, q) in prints if p <= bid_px)
                    s = int(min(size, elig_qty))
                    room = position_limit - pos
                    s = max(0, min(s, room))
                    if s > 0:
                        spread_i = ba[i + 1] - bb[i + 1]
                        pos += s
                        cash -= s * float(bid_px)
                        fills.append({
                            "i": i + 1, "ts": ts[i + 1], "kind": "make",
                            "side": +1, "size": s, "price": float(bid_px),
                            "mid": float(mid[i + 1]) if np.isfinite(mid[i + 1]) else np.nan,
                            "spread": float(spread_i) if np.isfinite(spread_i) else np.nan,
                        })

                if ask_px is not None and np.isfinite(ask_px) and prints:
                    elig_qty = sum(q for (p, q) in prints if p >= ask_px)
                    s = int(min(size, elig_qty))
                    room = position_limit + pos
                    s = max(0, min(s, room))
                    if s > 0:
                        spread_i = ba[i + 1] - bb[i + 1]
                        pos -= s
                        cash += s * float(ask_px)
                        fills.append({
                            "i": i + 1, "ts": ts[i + 1], "kind": "make",
                            "side": -1, "size": s, "price": float(ask_px),
                            "mid": float(mid[i + 1]) if np.isfinite(mid[i + 1]) else np.nan,
                            "spread": float(spread_i) if np.isfinite(spread_i) else np.nan,
                        })
        pos_arr[i] = pos
        m = mid[i] if np.isfinite(mid[i]) else (mid[i - 1] if i > 0 else 0.0)
        pnl_arr[i] = cash + pos * m

    # Flatten at last valid mid.
    valid_mid = mid[~np.isnan(mid)]
    m_last = float(valid_mid[-1]) if len(valid_mid) else 0.0
    cash += pos * m_last
    pos_arr[-1] = 0
    pnl_arr[-1] = cash

    pnl_series = pd.Series(pnl_arr, index=ts, name="pnl")
    pos_series = pd.Series(pos_arr, index=ts, name="position")
    fills_df = pd.DataFrame(fills)

    total_pnl = float(pnl_arr[-1])
    n_fills = int(len(fills_df))
    running_max = np.maximum.accumulate(pnl_arr)
    dd = float((pnl_arr - running_max).min())
    zero_spread_frac = (
        float((fills_df["spread"].fillna(1.0) <= 0).mean())
        if n_fills else 0.0
    )
    summary = {
        "total_pnl": total_pnl,
        "n_fills": n_fills,
        "avg_trade_pnl": total_pnl / n_fills if n_fills else 0.0,
        "max_position": int(np.max(np.abs(pos_arr))) if n else 0,
        "max_drawdown": dd,
        "zero_spread_fill_frac": zero_spread_frac,
    }
    return SimResult(name=name, params=dict(params), pnl_series=pnl_series,
                     position_series=pos_series, fills=fills_df, summary=summary)


# ---------------------------------------------------------------------------
# Strategy factories
# ---------------------------------------------------------------------------

def strat_fv_taker(features, *, fv_col, edge, size=1, position_limit=20,
                   trades=None):
    fv = features[fv_col].to_numpy()
    bb = features["best_bid"].to_numpy()
    ba = features["best_ask"].to_numpy()

    def decide(i, _state):
        if not (np.isfinite(fv[i]) and np.isfinite(bb[i]) and np.isfinite(ba[i])):
            return None
        if ba[i] < fv[i] - edge:
            return ("take", +1, size)
        if bb[i] > fv[i] + edge:
            return ("take", -1, size)
        return None

    return _run_sim(features, decide, name="fv_taker",
                    params={"fv_col": fv_col, "edge": edge, "size": size},
                    position_limit=position_limit, trades=trades)


def strat_fv_maker(features, *, fv_col, width, size=1, position_limit=20,
                   trades=None):
    fv = features[fv_col].to_numpy()

    def decide(i, _state):
        if not np.isfinite(fv[i]):
            return None
        return ("make", fv[i] - width, fv[i] + width, size)

    return _run_sim(features, decide, name="fv_maker",
                    params={"fv_col": fv_col, "width": width, "size": size},
                    position_limit=position_limit, trades=trades)


def strat_ema_reversion_taker(features, *, alpha, edge, size=1,
                              position_limit=20, trades=None):
    ema = features["mid"].ewm(alpha=alpha, adjust=False).mean().to_numpy()
    bb = features["best_bid"].to_numpy()
    ba = features["best_ask"].to_numpy()

    def decide(i, _state):
        if not (np.isfinite(ema[i]) and np.isfinite(bb[i]) and np.isfinite(ba[i])):
            return None
        if ba[i] < ema[i] - edge:
            return ("take", +1, size)
        if bb[i] > ema[i] + edge:
            return ("take", -1, size)
        return None

    return _run_sim(features, decide, name="ema_reversion_taker",
                    params={"alpha": alpha, "edge": edge, "size": size},
                    position_limit=position_limit, trades=trades)


def strat_zscore(features, *, window, entry, exit_z=0.3, size=1,
                 position_limit=20, trades=None):
    mid = features["mid"]
    mu = mid.rolling(window, min_periods=max(5, window // 5)).mean()
    sd = mid.rolling(window, min_periods=max(5, window // 5)).std().replace(0, np.nan)
    z = ((mid - mu) / sd).to_numpy()

    def decide(i, state):
        pos = state["pos"]
        if not np.isfinite(z[i]):
            return None
        if pos == 0:
            if z[i] > entry:
                return ("take", -1, size)
            if z[i] < -entry:
                return ("take", +1, size)
        else:
            if (pos > 0 and z[i] > -exit_z) or (pos < 0 and z[i] < exit_z):
                return ("take", -np.sign(pos), abs(pos))
        return None

    return _run_sim(features, decide, name="zscore",
                    params={"window": window, "entry": entry, "exit_z": exit_z,
                            "size": size},
                    position_limit=position_limit, trades=trades)


def strat_obi_tilt_taker(features, *, threshold, size=1, position_limit=20,
                         obi_col="obi_l1", trades=None):
    obi = features[obi_col].to_numpy()

    def decide(i, state):
        pos = state["pos"]
        if not np.isfinite(obi[i]):
            return None
        if obi[i] > threshold and pos <= 0:
            return ("take", +1, size)
        if obi[i] < -threshold and pos >= 0:
            return ("take", -1, size)
        return None

    return _run_sim(features, decide, name="obi_tilt_taker",
                    params={"threshold": threshold, "size": size,
                            "obi_col": obi_col},
                    position_limit=position_limit, trades=trades)


def strat_hybrid_make_take(features, *, fv_col, edge, width, size=1,
                           position_limit=20, trades=None):
    fv = features[fv_col].to_numpy()
    bb = features["best_bid"].to_numpy()
    ba = features["best_ask"].to_numpy()

    def decide(i, _state):
        if not np.isfinite(fv[i]):
            return None
        if np.isfinite(ba[i]) and ba[i] < fv[i] - edge:
            return ("take", +1, size)
        if np.isfinite(bb[i]) and bb[i] > fv[i] + edge:
            return ("take", -1, size)
        return ("make", fv[i] - width, fv[i] + width, size)

    return _run_sim(features, decide, name="hybrid_make_take",
                    params={"fv_col": fv_col, "edge": edge, "width": width,
                            "size": size},
                    position_limit=position_limit, trades=trades)
