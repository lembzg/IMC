"""
Empirical level-based microstructure analysis for ASH_COATED_OSMIUM.
Checks whether specific ask/bid levels show repeatable snap-back behaviour.
"""
import pandas as pd
import numpy as np
from collections import defaultdict

# ── load data ──────────────────────────────────────────────────────────────────
DATA = "/home/j39233pt/Desktop/IMC/data"
days = [-1, 0, 1]

price_frames = []
for d in days:
    df = pd.read_csv(f"{DATA}/prices/prices_round_2_day_{d}.csv", sep=";")
    df["day"] = d
    price_frames.append(df)
prices = pd.concat(price_frames, ignore_index=True)
prices = prices[prices["product"] == "ASH_COATED_OSMIUM"].copy()
prices = prices.sort_values(["day", "timestamp"]).reset_index(drop=True)

trade_frames = []
for d in days:
    df = pd.read_csv(f"{DATA}/trades/trades_round_2_day_{d}.csv", sep=";")
    df["day"] = d
    trade_frames.append(df)
trades = pd.concat(trade_frames, ignore_index=True)
trades = trades[trades["symbol"] == "ASH_COATED_OSMIUM"].copy()
trades = trades.sort_values(["day", "timestamp"]).reset_index(drop=True)

print(f"Loaded {len(prices)} price snapshots, {len(trades)} trades for ASH_COATED_OSMIUM\n")

# ── basic stats ────────────────────────────────────────────────────────────────
print("=== BASIC PRICE STATS ===")
print(prices[["bid_price_1","ask_price_1","mid_price"]].describe().round(2))
print()

# ── spread distribution ────────────────────────────────────────────────────────
prices["spread"] = prices["ask_price_1"] - prices["bid_price_1"]
print("=== SPREAD DISTRIBUTION ===")
print(prices["spread"].value_counts().sort_index().head(20))
print()

# ── ask level frequency ────────────────────────────────────────────────────────
print("=== BEST ASK LEVEL FREQUENCY (top 20) ===")
ask_counts = prices["ask_price_1"].value_counts().sort_index()
total = len(prices)
for lvl, cnt in ask_counts.items():
    print(f"  ask={lvl:>7.1f}  count={cnt:>5}  ({100*cnt/total:.1f}%)")
print()

print("=== BEST BID LEVEL FREQUENCY (top 20) ===")
bid_counts = prices["bid_price_1"].value_counts().sort_index()
for lvl, cnt in bid_counts.items():
    print(f"  bid={lvl:>7.1f}  count={cnt:>5}  ({100*cnt/total:.1f}%)")
print()

# ── CORE ANALYSIS: snap-back after level touch ────────────────────────────────
# For each row, look N ticks forward and measure ask/bid/mid change.
FORWARD_TICKS = [1, 2, 3, 5, 10]
MAX_FWD = max(FORWARD_TICKS)

# Precompute global index so forward lookup is O(1)
ask = prices["ask_price_1"].values
bid = prices["bid_price_1"].values
mid = prices["mid_price"].values
N = len(prices)

def analyze_level_touch(touch_mask, side, level):
    """
    For rows where touch_mask is True, measure what happens to mid_price
    over the next FORWARD_TICKS ticks (within same day).
    side: 'ask' → we're buying, want mid to rise
          'bid' → we're selling, want mid to fall
    """
    rows = np.where(touch_mask)[0]
    if len(rows) == 0:
        return None

    results = {k: [] for k in FORWARD_TICKS}
    day_vals = prices["day"].values

    for i in rows:
        mid_now = mid[i]
        day_now = day_vals[i]
        for fwd in FORWARD_TICKS:
            j = i + fwd
            if j < N and day_vals[j] == day_now:
                delta = mid[j] - mid_now
                if side == "bid":  # short side — we want negative delta
                    delta = -delta
                results[fwd].append(delta)

    out = {"level": level, "side": side, "touches": len(rows)}
    for fwd in FORWARD_TICKS:
        arr = np.array(results[fwd])
        if len(arr) > 0:
            out[f"mean_{fwd}"] = round(arr.mean(), 3)
            out[f"pct_fav_{fwd}"] = round(100 * (arr > 0).mean(), 1)
            out[f"pct_adv_{fwd}"] = round(100 * (arr < 0).mean(), 1)
    return out

# ── LONG SIDE: ask dips to level → expect snap back up ────────────────────────
LONG_LEVELS = [10000, 10001, 10002, 10003, 10004, 10005]
SHORT_LEVELS = [10003, 10004, 10005, 10006, 10007, 10008]

print("=" * 70)
print("LONG-SIDE ANALYSIS: best ask touches level → what does mid do?")
print("  positive mean = mid rose after touch (favourable for buyer)")
print("=" * 70)
for lvl in LONG_LEVELS:
    mask = (ask == lvl)
    res = analyze_level_touch(mask, "ask", lvl)
    if res:
        print(f"\nask={lvl}  touches={res['touches']}")
        hdr = f"  {'fwd':>5}  {'mean_Δmid':>10}  {'%fav':>6}  {'%adv':>6}"
        print(hdr)
        for fwd in FORWARD_TICKS:
            k = f"mean_{fwd}"
            if k in res:
                print(f"  {fwd:>5}  {res[k]:>10.3f}  {res[f'pct_fav_{fwd}']:>5.1f}%  {res[f'pct_adv_{fwd}']:>5.1f}%")

print()
print("=" * 70)
print("SHORT-SIDE ANALYSIS: best bid touches level → what does mid do?")
print("  positive mean = mid fell after touch (favourable for seller)")
print("=" * 70)
for lvl in SHORT_LEVELS:
    mask = (bid == lvl)
    res = analyze_level_touch(mask, "bid", lvl)
    if res:
        print(f"\nbid={lvl}  touches={res['touches']}")
        hdr = f"  {'fwd':>5}  {'mean_Δmid':>10}  {'%fav':>6}  {'%adv':>6}"
        print(hdr)
        for fwd in FORWARD_TICKS:
            k = f"mean_{fwd}"
            if k in res:
                print(f"  {fwd:>5}  {res[k]:>10.3f}  {res[f'pct_fav_{fwd}']:>5.1f}%  {res[f'pct_adv_{fwd}']:>5.1f}%")

# ── TRANSITION ANALYSIS: after ask=L, how quickly does ask leave that level? ──
print()
print("=" * 70)
print("ASK LEVEL STICKINESS: how many consecutive ticks does ask stay at level?")
print("=" * 70)

day_vals = prices["day"].values
for lvl in LONG_LEVELS:
    durations = []
    i = 0
    while i < N:
        if ask[i] == lvl:
            run = 0
            j = i
            while j < N and ask[j] == lvl and day_vals[j] == day_vals[i]:
                run += 1
                j += 1
            durations.append(run)
            i = j
        else:
            i += 1
    if durations:
        arr = np.array(durations)
        print(f"  ask={lvl}  episodes={len(arr)}  median_len={np.median(arr):.0f}  mean={arr.mean():.1f}  p90={np.percentile(arr,90):.0f}")

print()
print("=" * 70)
print("BID LEVEL STICKINESS: how many consecutive ticks does bid stay at level?")
print("=" * 70)
for lvl in SHORT_LEVELS:
    durations = []
    i = 0
    while i < N:
        if bid[i] == lvl:
            run = 0
            j = i
            while j < N and bid[j] == lvl and day_vals[j] == day_vals[i]:
                run += 1
                j += 1
            durations.append(run)
            i = j
        else:
            i += 1
    if durations:
        arr = np.array(durations)
        print(f"  bid={lvl}  episodes={len(arr)}  median_len={np.median(arr):.0f}  mean={arr.mean():.1f}  p90={np.percentile(arr,90):.0f}")

# ── TRADE PRICE DISTRIBUTION ───────────────────────────────────────────────────
print()
print("=" * 70)
print("TRADE PRICE DISTRIBUTION (round prices)")
print("=" * 70)
trade_counts = trades["price"].apply(lambda x: round(x)).value_counts().sort_index()
for p, cnt in trade_counts.items():
    print(f"  price={p:>7}  trades={cnt:>5}")

# ── AFTER TOUCH: did a trade happen at that level? ────────────────────────────
print()
print("=" * 70)
print("ASK LEVEL: after best_ask touches level, does a trade execute there?")
print("=" * 70)
# Build trade lookup: (day, ts_bucket) → list of trade prices
trade_lookup = defaultdict(list)
for _, row in trades.iterrows():
    # snap trades to nearest 100ms bucket
    bucket = int(row["timestamp"] / 100) * 100
    trade_lookup[(row["day"], bucket)].append(row["price"])

for lvl in LONG_LEVELS:
    mask = np.where(ask == lvl)[0]
    hits = 0
    for i in mask:
        ts = prices["timestamp"].values[i]
        d = day_vals[i]
        bucket = int(ts / 100) * 100
        for tb in [bucket, bucket+100, bucket+200]:
            tprices = trade_lookup.get((d, tb), [])
            if any(abs(tp - lvl) <= 1 for tp in tprices):
                hits += 1
                break
    pct = 100*hits/len(mask) if len(mask) else 0
    print(f"  ask={lvl}  snaps_with_trade={hits}/{len(mask)} ({pct:.1f}%)")

print()
print("Done.")
