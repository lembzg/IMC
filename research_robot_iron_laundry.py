"""
ROBOT_IRONING and ROBOT_LAUNDRY signal hunt.

Goal: find a stable, robust signal that gives ≥20k PnL on each individually,
consistent across days 2/3/4.

Approach:
  1. Scan all products for level/return correlation with IRONING and LAUNDRY.
  2. Identify sign-consistent strong signals across the 3 days.
  3. Backtest residual z-score strategies on top candidates.
  4. Test pair-sum and pair-diff strategies.
"""

import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path("data/round5")
DAYS = [2, 3, 4]
TARGETS = ["ROBOT_IRONING", "ROBOT_LAUNDRY"]
HALF_SPREAD = 1


def load_data():
    frames = [pd.read_csv(DATA_DIR / f"prices_round_5_day_{d}.csv", sep=";") for d in DAYS]
    df = pd.concat(frames, ignore_index=True)
    pivot = df.pivot_table(index=["day", "timestamp"], columns="product", values="mid_price")
    return pivot.sort_index()


def stable_corr(pivot, target):
    rows = []
    for col in pivot.columns:
        if col == target:
            continue
        per_lvl = []; per_ret = []
        for d in DAYS:
            sub = pivot.xs(d, level="day")
            t = sub[target].dropna(); o = sub[col].dropna()
            common = t.index.intersection(o.index)
            if len(common) < 100:
                per_lvl.append(np.nan); per_ret.append(np.nan); continue
            per_lvl.append(t.loc[common].corr(o.loc[common]))
            per_ret.append(t.loc[common].diff().corr(o.loc[common].diff()))
        if all(pd.notna(c) for c in per_lvl):
            rows.append({
                "product": col,
                "lvl_d2": per_lvl[0], "lvl_d3": per_lvl[1], "lvl_d4": per_lvl[2],
                "ret_d2": per_ret[0], "ret_d3": per_ret[1], "ret_d4": per_ret[2],
                "lvl_min_abs": min(abs(c) for c in per_lvl),
                "ret_min_abs": min(abs(c) for c in per_ret),
                "lvl_sign_ok": all(c > 0 for c in per_lvl) or all(c < 0 for c in per_lvl),
                "ret_sign_ok": all(c > 0 for c in per_ret) or all(c < 0 for c in per_ret),
            })
    return pd.DataFrame(rows)


def backtest_residual(pivot, target, signal, window=400, entry=10, exit=3, size=10, hs=HALF_SPREAD):
    """Predict target from signal via rolling regression, trade z-score of residual."""
    rows = []
    for d in DAYS:
        sub = pivot.xs(d, level="day").dropna(subset=[target, signal])
        if len(sub) < window + 10:
            rows.append((d, 0.0, 0)); continue
        t = sub[target].values; s = sub[signal].values
        beta = np.full(len(t), np.nan); alpha = np.full(len(t), np.nan)
        for i in range(window, len(t)):
            ts = t[i-window:i]; ss = s[i-window:i]
            var_s = np.var(ss)
            if var_s > 1e-9:
                b = np.cov(ts, ss)[0, 1] / var_s
                beta[i] = b; alpha[i] = np.mean(ts) - b * np.mean(ss)
        residual = t - (alpha + beta * s)
        rmean = pd.Series(residual).rolling(window, min_periods=window).mean().values
        rstd = pd.Series(residual).rolling(window, min_periods=window).std().clip(lower=0.1).values
        z = (residual - rmean) / rstd

        pos = 0; pnl = 0.0; trades = 0
        for i in range(len(t) - 1):
            zi = z[i]
            if pd.isna(zi): continue
            target_pos = pos
            if zi > entry: target_pos = -size
            elif zi < -entry: target_pos = size
            elif abs(zi) < exit: target_pos = 0
            d_pos = target_pos - pos
            if d_pos != 0:
                pnl -= abs(d_pos) * hs; trades += 1; pos = target_pos
            pnl += pos * (t[i+1] - t[i])
        rows.append((d, pnl, trades))
    return rows


def backtest_pair_sum(pivot, p1, p2, window=400, entry_z=1.0, exit_z=0.3, size=10, hs=HALF_SPREAD):
    """Trade SUM of two products on z-score (when anti-correlated, sum is stable)."""
    rows = []
    for d in DAYS:
        sub = pivot.xs(d, level="day").dropna(subset=[p1, p2])
        if len(sub) < window + 10:
            rows.append((d, 0.0, 0)); continue
        a = sub[p1].values; b = sub[p2].values
        s = a + b
        sm = pd.Series(s).rolling(window, min_periods=window).mean().values
        sstd = pd.Series(s).rolling(window, min_periods=window).std().clip(lower=0.1).values
        z = (s - sm) / sstd
        pos_a = 0; pos_b = 0; pnl = 0.0; trades = 0
        for i in range(len(s) - 1):
            zi = z[i]
            if pd.isna(zi): continue
            ta = pos_a; tb = pos_b
            if zi > entry_z: ta = -size; tb = -size
            elif zi < -entry_z: ta = size; tb = size
            elif abs(zi) < exit_z: ta = 0; tb = 0
            d_a = ta - pos_a; d_b = tb - pos_b
            if d_a != 0: pnl -= abs(d_a) * hs; trades += 1; pos_a = ta
            if d_b != 0: pnl -= abs(d_b) * hs; trades += 1; pos_b = tb
            pnl += pos_a * (a[i+1] - a[i]) + pos_b * (b[i+1] - b[i])
        rows.append((d, pnl, trades))
    return rows


def backtest_pair_diff(pivot, p1, p2, window=400, entry_z=1.0, exit_z=0.3, size=10, hs=HALF_SPREAD):
    """Trade DIFF of two products on z-score (when positively correlated, diff is stable)."""
    rows = []
    for d in DAYS:
        sub = pivot.xs(d, level="day").dropna(subset=[p1, p2])
        if len(sub) < window + 10:
            rows.append((d, 0.0, 0)); continue
        a = sub[p1].values; b = sub[p2].values
        s = a - b
        sm = pd.Series(s).rolling(window, min_periods=window).mean().values
        sstd = pd.Series(s).rolling(window, min_periods=window).std().clip(lower=0.1).values
        z = (s - sm) / sstd
        pos_a = 0; pos_b = 0; pnl = 0.0; trades = 0
        for i in range(len(s) - 1):
            zi = z[i]
            if pd.isna(zi): continue
            ta = pos_a; tb = pos_b
            if zi > entry_z: ta = -size; tb = size
            elif zi < -entry_z: ta = size; tb = -size
            elif abs(zi) < exit_z: ta = 0; tb = 0
            d_a = ta - pos_a; d_b = tb - pos_b
            if d_a != 0: pnl -= abs(d_a) * hs; trades += 1; pos_a = ta
            if d_b != 0: pnl -= abs(d_b) * hs; trades += 1; pos_b = tb
            pnl += pos_a * (a[i+1] - a[i]) + pos_b * (b[i+1] - b[i])
        rows.append((d, pnl, trades))
    return rows


if __name__ == "__main__":
    pivot = load_data()
    print(f"Loaded {len(pivot)} ticks, {len(pivot.columns)} products")

    for tgt in TARGETS:
        print(f"\n{'='*70}\nTarget: {tgt}\n{'='*70}")
        df = stable_corr(pivot, tgt)
        df_sorted = df.sort_values("lvl_min_abs", ascending=False)
        print(f"\n--- Top 10 by min|level corr| (consistent strength across days) ---")
        print(df_sorted.head(10)[["product", "lvl_d2", "lvl_d3", "lvl_d4", "lvl_min_abs", "lvl_sign_ok"]].to_string(index=False))
        print(f"\n--- Top 10 by min|return corr| ---")
        df_ret = df.sort_values("ret_min_abs", ascending=False)
        print(df_ret.head(10)[["product", "ret_d2", "ret_d3", "ret_d4", "ret_min_abs", "ret_sign_ok"]].to_string(index=False))

        print(f"\n--- Sign-consistent (top 8) ---")
        cons = df[df["lvl_sign_ok"]].sort_values("lvl_min_abs", ascending=False).head(8)
        print(cons[["product", "lvl_d2", "lvl_d3", "lvl_d4", "lvl_min_abs", "ret_min_abs"]].to_string(index=False))

    # Test signals for each target
    for tgt in TARGETS:
        print(f"\n\n{'='*70}\nResidual z-score backtests for {tgt}\n{'='*70}")
        # Use top sign-consistent products + a few key candidates
        df = stable_corr(pivot, tgt)
        cons = df[df["lvl_sign_ok"]].sort_values("lvl_min_abs", ascending=False).head(6)
        cands = list(cons["product"]) + ["ROBOT_DISHES", "ROBOT_MOPPING", "ROBOT_VACUUMING", "PEBBLES_S"]
        cands = [c for c in dict.fromkeys(cands) if c in pivot.columns and c != tgt]

        print(f"\n{'signal':<35} {'window':>7} {'entry':>6} {'exit':>5} {'D2':>7} {'D3':>7} {'D4':>7} {'Total':>8} {'Trades':>7}")
        for sig in cands:
            for w in [200, 400, 800]:
                for e in [1.0, 1.5, 2.0]:
                    for x in [0.3, 0.5]:
                        # Use residual z-score with these as z-thresholds... wait, residual band
                        pass
                # use the simpler residual entry/exit thresholds (in price units)
                for en in [10, 20, 40]:
                    for ex in [3, 10]:
                        if ex >= en: continue
                        res = backtest_residual(pivot, tgt, sig, window=w, entry=en, exit=ex)
                        t = sum(r[1] for r in res); n = sum(r[2] for r in res)
                        if t > 8000 and all(r[1] > -2000 for r in res):  # filter for promising
                            print(f"{sig:<35} {w:>7} {en:>6} {ex:>5} {res[0][1]:>7.0f} {res[1][1]:>7.0f} {res[2][1]:>7.0f} {t:>8.0f} {n:>7}")

    # Pair sum/diff with each ROBOT and key candidates
    print(f"\n\n{'='*70}\nPair-SUM and Pair-DIFF tests\n{'='*70}")
    candidate_pairs = [
        ("ROBOT_IRONING", "ROBOT_LAUNDRY"),
        ("ROBOT_IRONING", "ROBOT_DISHES"),
        ("ROBOT_IRONING", "ROBOT_MOPPING"),
        ("ROBOT_IRONING", "ROBOT_VACUUMING"),
        ("ROBOT_IRONING", "PEBBLES_S"),
        ("ROBOT_LAUNDRY", "ROBOT_DISHES"),
        ("ROBOT_LAUNDRY", "ROBOT_MOPPING"),
        ("ROBOT_LAUNDRY", "ROBOT_VACUUMING"),
        ("ROBOT_LAUNDRY", "PEBBLES_S"),
    ]
    print(f"\n{'Pair':<40} {'mode':>5} {'window':>7} {'ez':>4} {'xz':>4} {'D2':>7} {'D3':>7} {'D4':>7} {'Total':>8}")
    for p1, p2 in candidate_pairs:
        for mode in ["sum", "diff"]:
            fn = backtest_pair_sum if mode == "sum" else backtest_pair_diff
            for w in [200, 400, 800]:
                for ez in [1.0, 1.5, 2.0]:
                    for xz in [0.3, 0.5]:
                        res = fn(pivot, p1, p2, window=w, entry_z=ez, exit_z=xz)
                        t = sum(r[1] for r in res)
                        if t > 15000 and all(r[1] > 2000 for r in res):
                            print(f"{p1[:20]+'-'+p2[:18]:<40} {mode:>5} {w:>7} {ez:>4} {xz:>4} {res[0][1]:>7.0f} {res[1][1]:>7.0f} {res[2][1]:>7.0f} {t:>8.0f}")
