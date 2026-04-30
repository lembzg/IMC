import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
PRODUCT = "HYDROGEL_PACK"
LIMIT = 200


@dataclass(frozen=True)
class Candidate:
    indicator: str
    lookback: int
    entry: float
    exit: float
    target: int


def row_levels(row: pd.Series, side: str) -> list[tuple[int, int]]:
    levels = []
    for i in (1, 2, 3):
        price = row.get(f"{side}_price_{i}")
        volume = row.get(f"{side}_volume_{i}")
        if not pd.isna(price) and not pd.isna(volume):
            levels.append((int(price), int(abs(volume))))
    return levels


def load_days(data_dir: Path, days: list[int]) -> dict[int, pd.DataFrame]:
    out = {}
    for day in days:
        path = data_dir / f"prices_round_4_day_{day}.csv"
        df = pd.read_csv(path, sep=";")
        df = df[df["product"] == PRODUCT].sort_values("timestamp").reset_index(drop=True)
        numeric = [c for c in df.columns if c != "product"]
        df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")
        out[day] = df
    return out


def add_signal(df: pd.DataFrame, indicator: str, lookback: int) -> pd.Series:
    mid = df["mid_price"].astype(float)
    prior = mid.shift(1)

    if indicator == "rolling_z":
        mean = prior.rolling(lookback, min_periods=lookback).mean()
        std = prior.rolling(lookback, min_periods=lookback).std(ddof=0)
        return ((mid - mean) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    if indicator == "ema_z":
        ema = prior.ewm(span=lookback, adjust=False, min_periods=lookback).mean()
        resid = prior - ema
        std = resid.rolling(lookback, min_periods=lookback).std(ddof=0)
        return ((mid - ema) / std).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    if indicator == "median_mad_z":
        med = prior.rolling(lookback, min_periods=lookback).median()
        mad = (prior - med).abs().rolling(lookback, min_periods=lookback).median()
        return ((mid - med) / (1.4826 * mad)).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    if indicator == "trend_resid_z":
        x = np.arange(lookback, dtype=float)
        x_mean = x.mean()
        x_var = ((x - x_mean) ** 2).sum()

        def resid(values: np.ndarray) -> float:
            y = values[:-1]
            current = values[-1]
            y_mean = y.mean()
            slope = ((x - x_mean) * (y - y_mean)).sum() / x_var
            intercept = y_mean - slope * x_mean
            predicted = intercept + slope * lookback
            err = y - (intercept + slope * x)
            std = err.std()
            return 0.0 if std == 0 else (current - predicted) / std

        return mid.rolling(lookback + 1, min_periods=lookback + 1).apply(resid, raw=True).fillna(0.0)

    raise ValueError(f"unknown indicator: {indicator}")


def cross_to(bids: list[tuple[int, int]], asks: list[tuple[int, int]], cash: float, pos: int, target: int):
    traded = 0
    if target > pos:
        need = min(target - pos, LIMIT - pos)
        for price, volume in asks:
            qty = min(need, volume)
            if qty <= 0:
                continue
            cash -= qty * price
            pos += qty
            traded += qty
            need -= qty
            if need <= 0:
                break
    elif target < pos:
        need = min(pos - target, LIMIT + pos)
        for price, volume in bids:
            qty = min(need, volume)
            if qty <= 0:
                continue
            cash += qty * price
            pos -= qty
            traded += qty
            need -= qty
            if need <= 0:
                break
    return cash, pos, traded


def simulate(
    bids: list[list[tuple[int, int]]],
    asks: list[list[tuple[int, int]]],
    mids: np.ndarray,
    signal: pd.Series,
    candidate: Candidate,
) -> tuple[float, int, int]:
    sig = signal.to_numpy()
    cash = 0.0
    pos = 0
    turnover = 0
    trades = 0

    for i, mid in enumerate(mids):
        z = sig[i]
        target = pos
        if z >= candidate.entry:
            target = -candidate.target
        elif z <= -candidate.entry:
            target = candidate.target
        elif abs(z) <= candidate.exit:
            target = 0

        cash, new_pos, traded = cross_to(bids[i], asks[i], cash, pos, target)
        if traded:
            trades += 1
        pos = new_pos
        turnover += traded
        pnl = cash + pos * mid

    return cash + pos * mids[-1], turnover, trades


def build_grid() -> list[Candidate]:
    grid = []
    for indicator in ("rolling_z", "ema_z", "median_mad_z"):
        for lookback in (500, 650, 800, 1000, 1200, 1500, 1800, 2000):
            for entry in (2.0, 2.25, 2.5, 2.75, 3.0, 3.25):
                for exit_value in (0.0, 0.5):
                    if exit_value < entry:
                        for target in (50, 100, 150, 200):
                            grid.append(Candidate(indicator, lookback, entry, exit_value, target))
    return grid


def score_row(day_pnl: dict[int, float], turnover: int) -> float:
    values = list(day_pnl.values())
    return min(values) + 0.25 * sum(values) - 0.002 * turnover


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "data/prices")
    parser.add_argument("--days", nargs="+", type=int, default=[1, 2, 3])
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--out", type=Path, default=ROOT / "hydro_mean_reversion_results.csv")
    args = parser.parse_args()

    days = load_days(args.data, args.days)
    books = {
        day: (
            [row_levels(row, "bid") for _, row in df.iterrows()],
            [row_levels(row, "ask") for _, row in df.iterrows()],
            df["mid_price"].astype(float).to_numpy(),
        )
        for day, df in days.items()
    }
    grid = build_grid()
    needed = sorted({(c.indicator, c.lookback) for c in grid})
    signals = {
        (day, indicator, lookback): add_signal(df, indicator, lookback)
        for day, df in days.items()
        for indicator, lookback in needed
    }

    rows = []
    for candidate in grid:
        day_pnl = {}
        turnover = 0
        trades = 0
        for day, df in days.items():
            bids, asks, mids = books[day]
            pnl, day_turnover, day_trades = simulate(
                bids, asks, mids, signals[(day, candidate.indicator, candidate.lookback)], candidate
            )
            day_pnl[day] = pnl
            turnover += day_turnover
            trades += day_trades
        rows.append({
            "candidate": candidate,
            "total": sum(day_pnl.values()),
            "worst_day": min(day_pnl.values()),
            "score": score_row(day_pnl, turnover),
            "turnover": turnover,
            "trades": trades,
            "day_pnl": day_pnl,
        })

    rows.sort(key=lambda r: (r["score"], r["worst_day"], r["total"]), reverse=True)
    with args.out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "indicator", "lookback", "entry", "exit", "target", "score",
            "total", "worst_day", "turnover", "trades", *[f"day_{d}" for d in args.days],
        ])
        for rank, row in enumerate(rows, 1):
            c = row["candidate"]
            writer.writerow([
                rank, c.indicator, c.lookback, c.entry, c.exit, c.target,
                round(row["score"], 2), round(row["total"], 2), round(row["worst_day"], 2),
                row["turnover"], row["trades"], *[round(row["day_pnl"][d], 2) for d in args.days],
            ])

    print("rank indicator       lb entry exit target score   total worst turnover trades days")
    for rank, row in enumerate(rows[:args.top], 1):
        c = row["candidate"]
        days_str = " ".join(f"d{d}={row['day_pnl'][d]:.0f}" for d in args.days)
        print(
            f"{rank:4d} {c.indicator:14s} {c.lookback:4d} {c.entry:5.2f} {c.exit:4.2f}"
            f" {c.target:6d} {row['score']:7.0f} {row['total']:7.0f}"
            f" {row['worst_day']:7.0f} {row['turnover']:8d} {row['trades']:6d} {days_str}"
        )
    print(f"\nWrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
