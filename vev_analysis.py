"""
VEV Options Analysis  —  offline exploration using py_vollib
=============================================================
Run:  python vev_analysis.py

Sections:
  1. IV surface over time (per strike, all 3 days)
  2. Volatility smile shape at selected timestamps
  3. Lag-1 autocorrelation of IV changes per option
  4. Spot return autocorrelation
  5. Price deviation from BS fair value (using py_vollib)
  6. Top mispricing moments per option
"""

import csv
import math
from collections import defaultdict

import numpy as np
import pandas as pd

from py_vollib.black_scholes          import black_scholes
from py_vollib.black_scholes.greeks.analytical import delta, gamma, vega, theta
from py_vollib.black_scholes.implied_volatility import implied_volatility

# ── Config ─────────────────────────────────────────────────────────────────────
DATA_DIR    = "data_bt/round3"
ROUND_DAYS  = 3
STEPS_PER_DAY = 10_000
T_MAX       = 0.10   # "years" at start of round
T_MIN       = 0.001
FLAG        = "c"    # European call
RATE        = 0.0    # risk-free rate

OPTS = [
    "VEV_4000", "VEV_4500",
    "VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300",
    "VEV_5400", "VEV_5500", "VEV_6000", "VEV_6500",
]
STRIKES = {o: int(o.split("_")[1]) for o in OPTS}


# ── Load price data ────────────────────────────────────────────────────────────
def load_prices():
    """Returns dict: product → list of (day, timestamp, step, bid, ask, mid)"""
    records = defaultdict(list)
    step = 0
    for day in range(ROUND_DAYS):
        path = f"{DATA_DIR}/prices_round_3_day_{day}.csv"
        rows_by_ts = defaultdict(dict)
        with open(path) as f:
            for row in csv.DictReader(f, delimiter=";"):
                rows_by_ts[int(row["timestamp"])][row["product"]] = row
        for ts in sorted(rows_by_ts):
            step += 1
            data = rows_by_ts[ts]
            for prod in ["VELVETFRUIT_EXTRACT"] + OPTS:
                if prod not in data:
                    continue
                r = data[prod]
                bid = float(r["bid_price_1"]) if r["bid_price_1"] else None
                ask = float(r["ask_price_1"]) if r["ask_price_1"] else None
                mid = float(r["mid_price"])
                records[prod].append((day, ts, step, bid, ask, mid))
    return records


def tte(step):
    """Time to expiry in years given accumulated step number."""
    return max(T_MIN, T_MAX * (1 - step / (ROUND_DAYS * STEPS_PER_DAY)))


# ── Compute IV via py_vollib ───────────────────────────────────────────────────
def compute_iv(S, K, T, price):
    """Implied vol via py_vollib (LetsBeRational). Returns None on failure."""
    intrinsic = max(0.0, S - K)
    if price <= intrinsic + 0.5 or price <= 0 or S <= 0 or T <= 0:
        return None
    try:
        iv = implied_volatility(price, S, K, T, RATE, FLAG)
        return iv if 0.001 < iv < 20.0 else None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — IV surface over time
# ═══════════════════════════════════════════════════════════════════════════════
def section1(records):
    print("\n" + "═" * 70)
    print("SECTION 1 — IV surface: mean / std / min / max per option")
    print("═" * 70)

    spot_series = {(d, ts, s): m for d, ts, s, b, a, m in records["VELVETFRUIT_EXTRACT"]}

    rows = []
    for prod in OPTS:
        ivs = []
        for d, ts, step, bid, ask, mid in records[prod]:
            S = spot_series.get((d, ts, step))
            if not S:
                continue
            K = STRIKES[prod]
            T = tte(step)
            iv = compute_iv(S, K, T, mid)
            if iv:
                ivs.append(iv)
        if not ivs:
            continue
        rows.append({
            "Product": prod,
            "n":       len(ivs),
            "mean IV": f"{np.mean(ivs):.4f}",
            "std IV":  f"{np.std(ivs):.4f}",
            "min IV":  f"{np.min(ivs):.4f}",
            "p50 IV":  f"{np.median(ivs):.4f}",
            "max IV":  f"{np.max(ivs):.4f}",
        })

    print(pd.DataFrame(rows).to_string(index=False))


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Volatility smile at selected timestamps
# ═══════════════════════════════════════════════════════════════════════════════
def section2(records):
    print("\n" + "═" * 70)
    print("SECTION 2 — Vol smile shape at 3 timestamps")
    print("═" * 70)

    spot_map = {(d, ts, s): m for d, ts, s, b, a, m in records["VELVETFRUIT_EXTRACT"]}
    # bucket by (day, ts)
    opt_map = defaultdict(dict)
    for prod in OPTS:
        for d, ts, step, bid, ask, mid in records[prod]:
            opt_map[(d, ts, step)][prod] = (bid, ask, mid)

    # Pick early / mid / late ticks
    all_keys = sorted(opt_map.keys())
    picks = [
        all_keys[0],
        all_keys[len(all_keys) // 2],
        all_keys[-1],
    ]

    for key in picks:
        d, ts, step = key
        S = spot_map.get(key)
        if not S:
            continue
        T = tte(step)
        label = f"Day {d}  t={ts:>7}  step={step:>6}  T={T:.4f}  S={S:.1f}"
        print(f"\n  {label}")
        print(f"  {'Strike':>7}  {'Moneyness':>10}  {'Mid':>6}  {'IV':>8}  {'Delta':>7}  {'Vega':>8}")
        for prod in OPTS:
            if prod not in opt_map[key]:
                continue
            K = STRIKES[prod]
            _, _, mid = opt_map[key][prod]
            m = math.log(K / S)
            iv = compute_iv(S, K, T, mid)
            if iv is None:
                print(f"  {K:>7}  {m:>10.4f}  {mid:>6.1f}  {'(none)':>8}")
                continue
            try:
                d_val = delta(FLAG, S, K, T, RATE, iv)
                v_val = vega(FLAG, S, K, T, RATE, iv)
            except Exception:
                d_val = v_val = float("nan")
            print(f"  {K:>7}  {m:>10.4f}  {mid:>6.1f}  {iv:>8.4f}  {d_val:>7.3f}  {v_val:>8.2f}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Lag-1 IV autocorrelation per option
# ═══════════════════════════════════════════════════════════════════════════════
def section3(records):
    print("\n" + "═" * 70)
    print("SECTION 3 — Lag-1 autocorrelation of IV changes per option")
    print("═" * 70)

    spot_map = {(d, ts, s): m for d, ts, s, b, a, m in records["VELVETFRUIT_EXTRACT"]}

    rows = []
    for prod in OPTS:
        iv_series = []
        for d, ts, step, bid, ask, mid in records[prod]:
            S = spot_map.get((d, ts, step))
            if not S:
                continue
            K = STRIKES[prod]
            T = tte(step)
            iv = compute_iv(S, K, T, mid)
            if iv:
                iv_series.append(iv)

        if len(iv_series) < 10:
            continue
        diffs = np.diff(iv_series)
        if len(diffs) < 3 or np.std(diffs) < 1e-9:
            continue
        acf1 = np.corrcoef(diffs[:-1], diffs[1:])[0, 1]

        rows.append({
            "Product":    prod,
            "n IV obs":   len(iv_series),
            "mean IV":    f"{np.mean(iv_series):.4f}",
            "std(ΔIV)":   f"{np.std(diffs):.5f}",
            "p90|ΔIV|":  f"{np.percentile(np.abs(diffs), 90):.5f}",
            "lag1 ACF":   f"{acf1:.4f}",
        })

    print(pd.DataFrame(rows).to_string(index=False))
    print("\n  → Lag-1 ACF near -0.5 confirms strong IV mean reversion (Frankfurt Hedgehogs finding)")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — Spot return autocorrelation
# ═══════════════════════════════════════════════════════════════════════════════
def section4(records):
    print("\n" + "═" * 70)
    print("SECTION 4 — Spot return autocorrelation")
    print("═" * 70)

    mids = [m for _, _, _, _, _, m in records["VELVETFRUIT_EXTRACT"]]
    rets = np.diff(mids)

    for lag in [1, 2, 3, 5]:
        if len(rets) > lag:
            acf = np.corrcoef(rets[:-lag], rets[lag:])[0, 1]
            print(f"  Lag-{lag} return ACF: {acf:+.4f}")

    print(f"\n  Spot range: {min(mids):.0f} – {max(mids):.0f}")
    print(f"  Spot std (tick returns): {np.std(rets):.4f}")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Price deviation from BS fair (spot_mid, current IV as ATM ref)
# ═══════════════════════════════════════════════════════════════════════════════
def section5(records):
    print("\n" + "═" * 70)
    print("SECTION 5 — Price deviation from BS fair per option (distribution)")
    print("  fair = bs_call(spot_mid, K, T, iv_atm) where iv_atm = mean IV of")
    print("  VEV_5200/VEV_5300 that tick")
    print("═" * 70)

    # Build per-tick lookup
    spot_map = {(d, ts, s): m for d, ts, s, b, a, m in records["VELVETFRUIT_EXTRACT"]}
    opt_rows = defaultdict(dict)
    for prod in OPTS:
        for d, ts, step, bid, ask, mid in records[prod]:
            opt_rows[(d, ts, step)][prod] = mid

    deviations = defaultdict(list)
    for key, opt_data in opt_rows.items():
        S = spot_map.get(key)
        if not S:
            continue
        _, _, step = key
        T = tte(step)

        # ATM IV estimate from VEV_5200 / VEV_5300
        atm_ivs = []
        for ref in ("VEV_5200", "VEV_5300"):
            if ref not in opt_data:
                continue
            iv = compute_iv(S, STRIKES[ref], T, opt_data[ref])
            if iv:
                atm_ivs.append(iv)
        if not atm_ivs:
            continue
        iv_ref = np.mean(atm_ivs)

        for prod in OPTS:
            if prod not in opt_data:
                continue
            K = STRIKES[prod]
            mid = opt_data[prod]
            try:
                fair = black_scholes(FLAG, S, K, T, RATE, iv_ref)
            except Exception:
                continue
            dev = mid - fair
            deviations[prod].append(dev)

    rows = []
    for prod in OPTS:
        d = deviations[prod]
        if not d:
            continue
        d = np.array(d)
        rows.append({
            "Product":   prod,
            "n":         len(d),
            "mean dev":  f"{np.mean(d):+.2f}",
            "std dev":   f"{np.std(d):.2f}",
            "p10 dev":   f"{np.percentile(d, 10):+.2f}",
            "p90 dev":   f"{np.percentile(d, 90):+.2f}",
            "max |dev|": f"{np.max(np.abs(d)):.2f}",
        })

    print(pd.DataFrame(rows).to_string(index=False))
    print("\n  → Persistent positive mean deviation = structurally expensive vs ATM ref")
    print("    Persistent negative = structurally cheap")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Top mispricing moments (largest |price - fair|)
# ═══════════════════════════════════════════════════════════════════════════════
def section6(records):
    print("\n" + "═" * 70)
    print("SECTION 6 — Top 20 largest |price - BS fair| moments")
    print("═" * 70)

    spot_map = {(d, ts, s): m for d, ts, s, b, a, m in records["VELVETFRUIT_EXTRACT"]}
    opt_rows = defaultdict(dict)
    for prod in OPTS:
        for d, ts, step, bid, ask, mid in records[prod]:
            opt_rows[(d, ts, step)][prod] = (bid, ask, mid)

    events = []
    for key, opt_data in opt_rows.items():
        S = spot_map.get(key)
        if not S:
            continue
        day, ts, step = key
        T = tte(step)

        atm_ivs = []
        for ref in ("VEV_5200", "VEV_5300"):
            if ref not in opt_data:
                continue
            iv = compute_iv(S, STRIKES[ref], T, opt_data[ref][2])
            if iv:
                atm_ivs.append(iv)
        if not atm_ivs:
            continue
        iv_ref = np.mean(atm_ivs)

        for prod in OPTS:
            if prod not in opt_data:
                continue
            bid, ask, mid = opt_data[prod]
            K = STRIKES[prod]
            try:
                fair = black_scholes(FLAG, S, K, T, RATE, iv_ref)
            except Exception:
                continue
            dev = mid - fair
            if abs(dev) > 1.0:
                spread = (ask - bid) if (bid and ask) else None
                events.append((abs(dev), dev, day, ts, prod, mid, round(fair, 2),
                                spread, round(S, 1), round(iv_ref, 4)))

    events.sort(reverse=True)
    print(f"  {'|dev|':>6}  {'dev':>7}  d  {'ts':>7}  {'Product':<10}  "
          f"{'mid':>6}  {'fair':>6}  {'spread':>6}  {'S':>6}  {'iv_ref':>7}")
    for abs_d, dev, d, ts, prod, mid, fair, spread, S, iv_ref in events[:20]:
        sp_str = f"{spread:.0f}" if spread else "?"
        print(f"  {abs_d:>6.2f}  {dev:>+7.2f}  {d}  {ts:>7}  {prod:<10}  "
              f"{mid:>6.1f}  {fair:>6.2f}  {sp_str:>6}  {S:>6.1f}  {iv_ref:>7.4f}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Loading price data …")
    records = load_prices()
    print(f"Loaded {sum(len(v) for v in records.values()):,} rows across "
          f"{len(records)} products.")

    section1(records)
    section2(records)
    section3(records)
    section4(records)
    section5(records)
    section6(records)

    print("\n" + "═" * 70)
    print("Done.")
