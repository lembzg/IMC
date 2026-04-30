"""
Find a useful signal for SNACKPACK_VANILLA by scanning correlations.

Day 4 PnL is essentially flat (-44) despite Day 2/3 being decent. This script:
  1. Computes correlation of VANILLA mid with all other products' mids,
     in levels and in returns, per-day and overall.
  2. Finds the strongest stable signals (correlation consistent across days).
  3. Tests cluster-mean (snackpack) signal vs individual product signals.
  4. Suggests a strategy: predict VANILLA from signal, trade deviations.
"""

import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path("data/round5")
DAYS = [2, 3, 4]
TARGET = "SNACKPACK_VANILLA"
SNACKPACK = ["SNACKPACK_CHOCOLATE", "SNACKPACK_PISTACHIO", "SNACKPACK_RASPBERRY",
             "SNACKPACK_STRAWBERRY", "SNACKPACK_VANILLA"]


def load_data():
    frames = [pd.read_csv(DATA_DIR / f"prices_round_5_day_{d}.csv", sep=";") for d in DAYS]
    df = pd.concat(frames, ignore_index=True)
    pivot = df.pivot_table(index=["day", "timestamp"], columns="product", values="mid_price")
    return pivot.sort_index()


def stable_corr(pivot, target):
    """For each product, return per-day corrs + overall + min(abs)."""
    rows = []
    other_cols = [c for c in pivot.columns if c != target]
    for col in other_cols:
        per_day = []
        per_day_ret = []
        for d in DAYS:
            sub = pivot.xs(d, level="day")
            t = sub[target].dropna()
            o = sub[col].dropna()
            common = t.index.intersection(o.index)
            if len(common) < 100:
                per_day.append(np.nan); per_day_ret.append(np.nan); continue
            per_day.append(t.loc[common].corr(o.loc[common]))
            per_day_ret.append(t.loc[common].diff().corr(o.loc[common].diff()))
        if all(pd.notna(c) for c in per_day):
            min_abs = min(abs(c) for c in per_day)
            sign_consistent = all(c > 0 for c in per_day) or all(c < 0 for c in per_day)
            mean_corr = np.mean(per_day)
            mean_ret = np.mean(per_day_ret)
            rows.append({
                "product": col,
                "d2": per_day[0], "d3": per_day[1], "d4": per_day[2],
                "mean_lvl": mean_corr,
                "min_abs_lvl": min_abs,
                "sign_ok": sign_consistent,
                "ret_d2": per_day_ret[0], "ret_d3": per_day_ret[1], "ret_d4": per_day_ret[2],
                "mean_ret": mean_ret,
            })
    return pd.DataFrame(rows).sort_values("min_abs_lvl", ascending=False)


def test_cluster_signal(pivot):
    """VANILLA vs cluster-mean of other snackpacks."""
    others = [p for p in SNACKPACK if p != TARGET]
    cluster = pivot[others].mean(axis=1)
    print(f"\n=== Snackpack cluster (mean of 4 others) signal ===")
    for d in DAYS:
        sub = pivot.xs(d, level="day")
        t = sub[TARGET]
        c = cluster.xs(d, level="day")
        common = t.index.intersection(c.index)
        c_lvl = t.loc[common].corr(c.loc[common])
        c_ret = t.loc[common].diff().corr(c.loc[common].diff())
        print(f"  Day {d}: lvl_corr={c_lvl:.3f}  ret_corr={c_ret:.3f}")


def simulate_signal_strategy(pivot, signal_col, window=200, entry_z=1.5, exit_z=0.3, size=10, half_spread=1):
    """Trade VANILLA against deviation from regression on signal."""
    rows = []
    for d in DAYS:
        sub = pivot.xs(d, level="day").dropna(subset=[TARGET, signal_col])
        if len(sub) < window + 10:
            rows.append((d, 0.0, 0))
            continue

        # Use rolling regression: VANILLA_predicted = a + b * signal
        # Compute residual = VANILLA - predicted, z-score residual
        t = sub[TARGET].values
        s = sub[signal_col].values

        beta = np.full(len(t), np.nan)
        alpha = np.full(len(t), np.nan)
        # Rolling beta: use last `window` points
        for i in range(window, len(t)):
            ts = t[i-window:i]; ss = s[i-window:i]
            cov = np.cov(ts, ss)[0, 1]
            var_s = np.var(ss)
            if var_s > 1e-9:
                b = cov / var_s
                a = np.mean(ts) - b * np.mean(ss)
                beta[i] = b; alpha[i] = a

        residual = t - (alpha + beta * s)
        # rolling z of residual
        rmean = pd.Series(residual).rolling(window, min_periods=window).mean()
        rstd = pd.Series(residual).rolling(window, min_periods=window).std().clip(lower=0.1)
        z = (residual - rmean.values) / rstd.values

        pos = 0
        pnl = 0.0
        trades = 0
        for i in range(len(t) - 1):
            zi = z[i]
            if pd.isna(zi):
                continue
            target = pos
            if zi > entry_z:
                target = -size  # VANILLA expensive vs predicted → short
            elif zi < -entry_z:
                target = size
            elif abs(zi) < exit_z:
                target = 0
            d_pos = target - pos
            if d_pos != 0:
                pnl -= abs(d_pos) * half_spread
                trades += 1
                pos = target
            pnl += pos * (t[i+1] - t[i])
        rows.append((d, pnl, trades))
    return rows


if __name__ == "__main__":
    pivot = load_data()
    print(f"Loaded {len(pivot)} rows, {len(pivot.columns)} products")

    print(f"\n=== Top correlations with {TARGET} (level, sorted by min_abs across days) ===")
    df = stable_corr(pivot, TARGET)
    df_top = df.head(15)
    print(df_top[["product", "d2", "d3", "d4", "mean_lvl", "min_abs_lvl", "sign_ok", "mean_ret"]].to_string(index=False))

    print(f"\n=== Top sign-consistent (level corr same sign all 3 days) ===")
    df_consistent = df[df["sign_ok"]].sort_values("min_abs_lvl", ascending=False).head(15)
    print(df_consistent[["product", "d2", "d3", "d4", "mean_lvl", "min_abs_lvl", "mean_ret"]].to_string(index=False))

    print(f"\n=== Top by RETURN correlation (per-day mean) ===")
    df_ret = df.copy()
    df_ret["ret_min_abs"] = df_ret[["ret_d2", "ret_d3", "ret_d4"]].abs().min(axis=1)
    df_ret = df_ret.sort_values("ret_min_abs", ascending=False).head(15)
    print(df_ret[["product", "ret_d2", "ret_d3", "ret_d4", "mean_ret", "ret_min_abs"]].to_string(index=False))

    test_cluster_signal(pivot)

    # Test best signals as strategies
    print(f"\n=== Strategy backtest: VANILLA residual z-score on top signals ===")
    if len(df_consistent) > 0:
        candidates = df_consistent["product"].head(5).tolist()
    else:
        candidates = df.head(5)["product"].tolist()
    candidates += [c for c in ["SNACKPACK_PISTACHIO", "SNACKPACK_CHOCOLATE", "SNACKPACK_RASPBERRY", "SNACKPACK_STRAWBERRY"] if c in pivot.columns and c not in candidates]

    print(f"\n{'signal':<35} {'D2':>8} {'D3':>8} {'D4':>8} {'Total':>10} {'Trades':>8}")
    for sig in candidates:
        for entry_z in [1.0, 1.5, 2.0]:
            res = simulate_signal_strategy(pivot, sig, window=200, entry_z=entry_z, exit_z=0.3)
            total = sum(r[1] for r in res)
            trades = sum(r[2] for r in res)
            label = f"{sig}@z={entry_z}"
            print(f"{label:<35} {res[0][1]:>8.0f} {res[1][1]:>8.0f} {res[2][1]:>8.0f} {total:>10.0f} {trades:>8}")
