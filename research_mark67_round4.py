import math
from pathlib import Path

import pandas as pd


PRODUCT = "VELVETFRUIT_EXTRACT"
OPTIONS = ["VEV_5000", "VEV_5100", "VEV_5200", "VEV_5300", "VEV_5400", "VEV_5500"]
DATA = Path("data/round4")


def load_day(day: int):
    prices = pd.read_csv(DATA / f"prices_round_4_day_{day}.csv", sep=";")
    trades = pd.read_csv(DATA / f"trades_round_4_day_{day}.csv", sep=";")
    return prices, trades


def summarize_forward(prices: pd.DataFrame, trades: pd.DataFrame, day: int):
    mids = prices[prices["product"] == PRODUCT][["timestamp", "mid_price"]].copy()
    mids = mids.sort_values("timestamp")
    events = trades[
        (trades["symbol"] == PRODUCT)
        & (trades["buyer"] == "Mark 67")
    ][["timestamp", "seller", "price", "quantity"]].copy()
    events = events.sort_values("timestamp")

    rows = []
    for _, ev in events.iterrows():
        base_row = mids[mids["timestamp"] >= ev.timestamp]
        if base_row.empty:
            continue
        base_ts = int(base_row.iloc[0].timestamp)
        base_mid = float(base_row.iloc[0].mid_price)
        rec = {
            "day": day,
            "timestamp": int(ev.timestamp),
            "base_ts": base_ts,
            "seller": ev.seller,
            "price": float(ev.price),
            "quantity": int(ev.quantity),
            "base_mid": base_mid,
        }
        for h in [1, 3, 5, 10, 20, 50, 100]:
            fwd = mids[mids["timestamp"] >= base_ts + h * 100]
            if not fwd.empty:
                adv = float(fwd.iloc[0].mid_price - base_mid)
                rec[f"adv_{h}"] = adv
        rows.append(rec)
    return pd.DataFrame(rows)


def summarize_option_forward(prices: pd.DataFrame, events: pd.DataFrame, day: int):
    out = []
    for symbol in OPTIONS:
        mids = prices[prices["product"] == symbol][["timestamp", "mid_price"]].sort_values("timestamp")
        for h in [5, 20, 50]:
            advs = []
            for _, ev in events.iterrows():
                base = mids[mids["timestamp"] >= ev.base_ts]
                fwd = mids[mids["timestamp"] >= ev.base_ts + h * 100]
                if not base.empty and not fwd.empty:
                    advs.append(float(fwd.iloc[0].mid_price - base.iloc[0].mid_price))
            if advs:
                s = pd.Series(advs)
                out.append({
                    "day": day,
                    "symbol": symbol,
                    "h": h,
                    "n": len(advs),
                    "mean": s.mean(),
                    "win": (s > 0).mean(),
                })
    return pd.DataFrame(out)


def main():
    all_events = []
    all_options = []
    for day in [1, 2, 3]:
        prices, trades = load_day(day)
        events = summarize_forward(prices, trades, day)
        all_events.append(events)
        all_options.append(summarize_option_forward(prices, events, day))

    events = pd.concat(all_events, ignore_index=True)
    print("Mark67 events by day")
    print(events.groupby("day").agg(n=("timestamp", "size"), qty=("quantity", "sum"), avg_qty=("quantity", "mean")).to_string())
    print()

    for group_name, group in [("all", events)] + [(f"seller={s}", g) for s, g in events.groupby("seller")]:
        print(group_name)
        cols = []
        for h in [1, 3, 5, 10, 20, 50, 100]:
            c = f"adv_{h}"
            if c in group:
                cols.append({
                    "h": h,
                    "n": group[c].count(),
                    "mean": group[c].mean(),
                    "win": (group[c] > 0).mean(),
                    "median": group[c].median(),
                })
        print(pd.DataFrame(cols).to_string(index=False))
        print()

    print("by quantity bucket, h=50")
    events["qty_bucket"] = pd.cut(events["quantity"], bins=[0, 7, 10, 15], labels=["1-7", "8-10", "11-15"])
    print(events.groupby("qty_bucket", observed=True)["adv_50"].agg(["count", "mean", "median", lambda x: (x > 0).mean()]).to_string())
    print()

    opt = pd.concat(all_options, ignore_index=True)
    print("option mid advance after Mark67")
    print(opt.groupby(["symbol", "h"]).agg(n=("n", "sum"), mean=("mean", "mean"), win=("win", "mean")).to_string())


if __name__ == "__main__":
    main()
