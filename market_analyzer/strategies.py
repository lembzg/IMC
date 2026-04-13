"""
strategies.py
-------------
Benchmark strategy families with a unified simulator.

Inputs:  features DF (with best_bid/ask/mid and any FV columns).
Outputs: SimResult (pnl series, fills list, summary dict).

Trading decision informed: a strategy family is worth pursuing if its
benchmark achieves positive PnL with reasonable turnover AND that PnL is
robust to parameter perturbations (see sweeps.py).

Simulator assumptions (explicit — kept simple and conservative):
  * 1 "lot" = 1 unit; position limit bounded; orders at most hit L1 volume.
  * Taker: cross at best_ask (buy) or best_bid (sell) immediately; fill fully
    up to ``size`` (assumes L1 depth >= size). Mark-to-mid each tick.
  * Maker: quote at best_bid or best_ask (or one tick inside if width=0).
    Fill happens if next-tick trade price reaches our quote. This is a
    proxy; real queue position is unknown. It is an optimistic but standard
    benchmark — interpret results accordingly.
  * Exit: positions are flattened at mid on the last tick.
  * Fees / slippage beyond the spread cross are zero.
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
        row = {"strategy": self.name, **self.params, **self.summary}
        return row


# -- Core simulator ---------------------------------------------------------

def _run_sim(
    features: pd.DataFrame,
    decide: Callable[[int, Dict], Optional[tuple]],
    *,
    name: str,
    params: Dict,
    position_limit: int,
) -> SimResult:
    """Generic tick-by-tick simulator.

    ``decide(i, state)`` returns one of:
        None                               -> do nothing
        ("take", side, size)               -> market order (side = +1 buy / -1 sell)
        ("make", bid_px, ask_px, size)     -> post passive quotes for this tick

    Fills for "make" orders are evaluated by comparing the next tick's
    (best_bid, best_ask) crossing our quote — a standard optimistic proxy.
    """
    n = len(features)
    mid = features["mid"].to_numpy()
    bb = features["best_bid"].to_numpy()
    ba = features["best_ask"].to_numpy()

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
                # respect position limit
                room = position_limit - pos if side > 0 else position_limit + pos
                size = max(0, min(size, room))
                if size > 0 and np.isfinite(ba[i]) and np.isfinite(bb[i]):
                    px = ba[i] if side > 0 else bb[i]
                    pos += side * size
                    cash -= side * size * px
                    fills.append({"i": i, "ts": features["timestamp"].iat[i],
                                  "kind": "take", "side": side, "size": size, "price": px})
            elif kind == "make":
                _, bid_px, ask_px, size = action
                size = int(size)
                # Fill on next tick if opposite side crosses our quote.
                nb, na = bb[i + 1], ba[i + 1]
                if bid_px is not None and np.isfinite(bid_px) and np.isfinite(na) and na <= bid_px:
                    room = position_limit - pos
                    s = max(0, min(size, room))
                    if s > 0:
                        pos += s
                        cash -= s * bid_px
                        fills.append({"i": i + 1, "ts": features["timestamp"].iat[i + 1],
                                      "kind": "make", "side": +1, "size": s, "price": float(bid_px)})
                if ask_px is not None and np.isfinite(ask_px) and np.isfinite(nb) and nb >= ask_px:
                    room = position_limit + pos
                    s = max(0, min(size, room))
                    if s > 0:
                        pos -= s
                        cash += s * ask_px
                        fills.append({"i": i + 1, "ts": features["timestamp"].iat[i + 1],
                                      "kind": "make", "side": -1, "size": s, "price": float(ask_px)})
        pos_arr[i] = pos
        m = mid[i] if np.isfinite(mid[i]) else (mid[i - 1] if i > 0 else 0.0)
        pnl_arr[i] = cash + pos * m

    # flatten at last mid
    m_last = mid[-1] if np.isfinite(mid[-1]) else mid[~np.isnan(mid)][-1]
    cash += pos * m_last
    pos = 0
    pos_arr[-1] = 0
    pnl_arr[-1] = cash

    ts = features["timestamp"].to_numpy()
    pnl_series = pd.Series(pnl_arr, index=ts, name="pnl")
    pos_series = pd.Series(pos_arr, index=ts, name="position")
    fills_df = pd.DataFrame(fills)

    total_pnl = float(pnl_arr[-1])
    n_fills = int(len(fills_df))
    avg_trade_pnl = total_pnl / n_fills if n_fills else 0.0
    running_max = np.maximum.accumulate(pnl_arr)
    dd = float((pnl_arr - running_max).min())
    summary = {
        "total_pnl": total_pnl,
        "n_fills": n_fills,
        "avg_trade_pnl": avg_trade_pnl,
        "max_position": int(np.max(np.abs(pos_arr))),
        "max_drawdown": dd,
    }
    return SimResult(name=name, params=dict(params), pnl_series=pnl_series,
                     position_series=pos_series, fills=fills_df, summary=summary)


# -- Strategy factories -----------------------------------------------------

def strat_fv_taker(features: pd.DataFrame, *, fv_col: str, edge: float,
                   size: int = 1, position_limit: int = 20) -> SimResult:
    """Take when ask < FV - edge (buy) or bid > FV + edge (sell)."""
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
                    position_limit=position_limit)


def strat_fv_maker(features: pd.DataFrame, *, fv_col: str, width: float,
                   size: int = 1, position_limit: int = 20) -> SimResult:
    """Quote bid=FV-width, ask=FV+width."""
    fv = features[fv_col].to_numpy()

    def decide(i, _state):
        if not np.isfinite(fv[i]):
            return None
        return ("make", fv[i] - width, fv[i] + width, size)

    return _run_sim(features, decide, name="fv_maker",
                    params={"fv_col": fv_col, "width": width, "size": size},
                    position_limit=position_limit)


def strat_ema_reversion_taker(features: pd.DataFrame, *, alpha: float, edge: float,
                              size: int = 1, position_limit: int = 20) -> SimResult:
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
                    position_limit=position_limit)


def strat_zscore(features: pd.DataFrame, *, window: int, entry: float,
                 exit_z: float = 0.3, size: int = 1, position_limit: int = 20) -> SimResult:
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
                return ("take", -1, size)    # short: expect reversion down
            if z[i] < -entry:
                return ("take", +1, size)    # long: expect reversion up
        else:
            # Close when z has reverted near zero.
            if (pos > 0 and z[i] > -exit_z) or (pos < 0 and z[i] < exit_z):
                return ("take", -np.sign(pos), abs(pos))
        return None

    return _run_sim(features, decide, name="zscore",
                    params={"window": window, "entry": entry, "exit_z": exit_z, "size": size},
                    position_limit=position_limit)


def strat_obi_tilt_taker(features: pd.DataFrame, *, threshold: float,
                         size: int = 1, position_limit: int = 20,
                         obi_col: str = "obi_l1") -> SimResult:
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
                    params={"threshold": threshold, "size": size, "obi_col": obi_col},
                    position_limit=position_limit)


def strat_hybrid_make_take(features: pd.DataFrame, *, fv_col: str, edge: float,
                           width: float, size: int = 1, position_limit: int = 20) -> SimResult:
    """Take when mis-priced beyond ``edge``; otherwise make at FV±width."""
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
                    params={"fv_col": fv_col, "edge": edge, "width": width, "size": size},
                    position_limit=position_limit)
