"""
sweeps.py
---------
Parameter-grid runners for each benchmark family.

Inputs:  features DF.
Outputs: DataFrame of {strategy, params..., total_pnl, n_fills, ...}.

Trading decision informed: ranks parameter settings by PnL and (critically)
exposes plateaus vs spikes via the resulting table — a single lucky point is
not robust.
"""
from __future__ import annotations

import itertools
from typing import Dict, List

import pandas as pd

from . import strategies as S


def sweep_fv_taker(features: pd.DataFrame, fv_cols: List[str], edges: List[float],
                   position_limit: int = 20) -> pd.DataFrame:
    rows = []
    for fv, e in itertools.product(fv_cols, edges):
        if fv not in features:
            continue
        res = S.strat_fv_taker(features, fv_col=fv, edge=e, position_limit=position_limit)
        rows.append(res.as_row())
    return pd.DataFrame(rows)


def sweep_fv_maker(features: pd.DataFrame, fv_cols: List[str], widths: List[float],
                   position_limit: int = 20) -> pd.DataFrame:
    rows = []
    for fv, w in itertools.product(fv_cols, widths):
        if fv not in features:
            continue
        res = S.strat_fv_maker(features, fv_col=fv, width=w, position_limit=position_limit)
        rows.append(res.as_row())
    return pd.DataFrame(rows)


def sweep_ema_reversion(features: pd.DataFrame, alphas: List[float], edges: List[float],
                        position_limit: int = 20) -> pd.DataFrame:
    rows = []
    for a, e in itertools.product(alphas, edges):
        res = S.strat_ema_reversion_taker(features, alpha=a, edge=e, position_limit=position_limit)
        rows.append(res.as_row())
    return pd.DataFrame(rows)


def sweep_zscore(features: pd.DataFrame, windows: List[int], entries: List[float],
                 exits: List[float], position_limit: int = 20) -> pd.DataFrame:
    rows = []
    for w, entry, ex in itertools.product(windows, entries, exits):
        if ex >= entry:
            continue
        res = S.strat_zscore(features, window=w, entry=entry, exit_z=ex,
                             position_limit=position_limit)
        rows.append(res.as_row())
    return pd.DataFrame(rows)


def sweep_obi(features: pd.DataFrame, thresholds: List[float],
              position_limit: int = 20) -> pd.DataFrame:
    rows = []
    for thr in thresholds:
        res = S.strat_obi_tilt_taker(features, threshold=thr, position_limit=position_limit)
        rows.append(res.as_row())
    return pd.DataFrame(rows)


def sweep_hybrid(features: pd.DataFrame, fv_cols: List[str], edges: List[float],
                 widths: List[float], position_limit: int = 20) -> pd.DataFrame:
    rows = []
    for fv, e, w in itertools.product(fv_cols, edges, widths):
        if fv not in features or w >= e:
            continue
        res = S.strat_hybrid_make_take(features, fv_col=fv, edge=e, width=w,
                                       position_limit=position_limit)
        rows.append(res.as_row())
    return pd.DataFrame(rows)


def run_all_sweeps(
    features: pd.DataFrame,
    *,
    fv_cols: List[str],
    edges: List[float],
    widths: List[float],
    ema_alphas: List[float],
    z_windows: List[int],
    z_entries: List[float],
    z_exits: List[float],
    obi_thresholds: List[float],
    position_limit: int,
) -> Dict[str, pd.DataFrame]:
    return {
        "fv_taker": sweep_fv_taker(features, fv_cols, edges, position_limit),
        "fv_maker": sweep_fv_maker(features, fv_cols, widths, position_limit),
        "ema_reversion": sweep_ema_reversion(features, ema_alphas, edges, position_limit),
        "zscore": sweep_zscore(features, z_windows, z_entries, z_exits, position_limit),
        "obi_tilt": sweep_obi(features, obi_thresholds, position_limit),
        "hybrid_make_take": sweep_hybrid(features, fv_cols, edges, widths, position_limit),
    }
