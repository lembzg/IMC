"""
sweeps.py
---------
Parameter-grid runners for each benchmark family. Every sweep threads the
trades tape through so maker-style strategies use realistic passive-fill
rules (see strategies._run_sim).
"""
from __future__ import annotations

import itertools
from typing import Dict, List, Optional

import pandas as pd

from . import strategies as S


def sweep_fv_taker(features, fv_cols, edges, position_limit=20, trades=None):
    rows = []
    for fv, e in itertools.product(fv_cols, edges):
        if fv not in features:
            continue
        res = S.strat_fv_taker(features, fv_col=fv, edge=e,
                               position_limit=position_limit, trades=trades)
        rows.append(res.as_row())
    return pd.DataFrame(rows)


def sweep_fv_maker(features, fv_cols, widths, position_limit=20, trades=None):
    rows = []
    for fv, w in itertools.product(fv_cols, widths):
        if fv not in features:
            continue
        res = S.strat_fv_maker(features, fv_col=fv, width=w,
                               position_limit=position_limit, trades=trades)
        rows.append(res.as_row())
    return pd.DataFrame(rows)


def sweep_ema_reversion(features, alphas, edges, position_limit=20, trades=None):
    rows = []
    for a, e in itertools.product(alphas, edges):
        res = S.strat_ema_reversion_taker(features, alpha=a, edge=e,
                                          position_limit=position_limit,
                                          trades=trades)
        rows.append(res.as_row())
    return pd.DataFrame(rows)


def sweep_zscore(features, windows, entries, exits, position_limit=20,
                 trades=None):
    rows = []
    for w, entry, ex in itertools.product(windows, entries, exits):
        if ex >= entry:
            continue
        res = S.strat_zscore(features, window=w, entry=entry, exit_z=ex,
                             position_limit=position_limit, trades=trades)
        rows.append(res.as_row())
    return pd.DataFrame(rows)


def sweep_obi(features, thresholds, position_limit=20, trades=None):
    rows = []
    for thr in thresholds:
        res = S.strat_obi_tilt_taker(features, threshold=thr,
                                     position_limit=position_limit,
                                     trades=trades)
        rows.append(res.as_row())
    return pd.DataFrame(rows)


def sweep_hybrid(features, fv_cols, edges, widths, position_limit=20,
                 trades=None):
    rows = []
    for fv, e, w in itertools.product(fv_cols, edges, widths):
        if fv not in features or w >= e:
            continue
        res = S.strat_hybrid_make_take(features, fv_col=fv, edge=e, width=w,
                                       position_limit=position_limit,
                                       trades=trades)
        rows.append(res.as_row())
    return pd.DataFrame(rows)


def run_all_sweeps(
    features, *, fv_cols, edges, widths, ema_alphas, z_windows, z_entries,
    z_exits, obi_thresholds, position_limit, trades: Optional[pd.DataFrame] = None,
) -> Dict[str, pd.DataFrame]:
    return {
        "fv_taker": sweep_fv_taker(features, fv_cols, edges, position_limit, trades),
        "fv_maker": sweep_fv_maker(features, fv_cols, widths, position_limit, trades),
        "ema_reversion": sweep_ema_reversion(features, ema_alphas, edges,
                                             position_limit, trades),
        "zscore": sweep_zscore(features, z_windows, z_entries, z_exits,
                               position_limit, trades),
        "obi_tilt": sweep_obi(features, obi_thresholds, position_limit, trades),
        "hybrid_make_take": sweep_hybrid(features, fv_cols, edges, widths,
                                         position_limit, trades),
    }
