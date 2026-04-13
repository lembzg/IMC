"""
regime.py
---------
Phase 2 stub for rolling-feature regime classification.

Planned inputs:  features DF with rolling vol, spread, OBI strength, FV error.
Planned outputs: regime-label series (e.g. low_vol / high_vol / unstable).

Trading decision informed: switch strategy family dynamically — e.g. make in
tight-spread low-vol regime; take or sit out in wide-spread high-vol regime.

Current implementation: simple two-state vol regime based on rolling vol
quantiles, so the pipeline can consume it today and be upgraded later.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def label_vol_regime(features: pd.DataFrame, q_low: float = 0.33, q_high: float = 0.67) -> pd.Series:
    v = features["realized_vol"]
    lo = v.quantile(q_low)
    hi = v.quantile(q_high)
    out = pd.Series(np.where(v <= lo, "low_vol",
                             np.where(v >= hi, "high_vol", "mid_vol")),
                    index=features.index, name="vol_regime")
    return out
