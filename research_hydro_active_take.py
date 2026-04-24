import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


PRODUCT = "HYDROGEL_PACK"
ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Candidate:
    name: str
    family: str
    lookback: int
    entry: float
    exit: float
    direction: int
    target: int


@dataclass
class DayData:
    df: pd.DataFrame
    mids: list[float]
    bid_levels: list[list[tuple[int, int]]]
    ask_levels: list[list[tuple[int, int]]]
    signals: dict[tuple[str, int], list[float]]


@dataclass
class Result:
    candidate: Candidate
    total_pnl: float
    day_pnl: dict[int, float]
    max_abs_pos: int
    turnover: int
    fills: int
    time_at_limit: int
    steps: int


def read_day(data_dir: Path, day: int, lookbacks: set[int]) -> DayData:
    path = data_dir / "round3" / f"prices_round_3_day_{day}.csv"
    df = pd.read_csv(path, sep=";")
    df = df[df["product"] == PRODUCT].sort_values("timestamp").reset_index(drop=True)
    numeric_cols = [col for col in df.columns if col != "product"]
    df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")

    bid_vol = sum(df.get(f"bid_volume_{i}", 0).fillna(0).abs() for i in (1, 2, 3))
    ask_vol = sum(df.get(f"ask_volume_{i}", 0).fillna(0).abs() for i in (1, 2, 3))
    denom = (bid_vol + ask_vol).replace(0, pd.NA)
    imbalance = ((bid_vol - ask_vol) / denom).fillna(0.0)
    mid = df["mid_price"].astype(float)
    ret = mid.diff()

    signals: dict[tuple[str, int], list[float]] = {}
    signals[("imbalance", 1)] = imbalance.fillna(0.0).tolist()

    for lookback in lookbacks:
        prior_mid = mid.shift(1)
        rolling_mean = prior_mid.rolling(lookback, min_periods=max(5, min(lookback, 20))).mean()
        rolling_std = prior_mid.rolling(lookback, min_periods=max(5, min(lookback, 20))).std()
        signals[("mid_z", lookback)] = ((mid - rolling_mean) / rolling_std).replace([float("inf"), -float("inf")], 0).fillna(0.0).tolist()

        ema = prior_mid.ewm(span=lookback, adjust=False, min_periods=max(5, min(lookback, 20))).mean()
        signals[("ema_diff", lookback)] = (mid - ema).fillna(0.0).tolist()

        vol = ret.shift(1).rolling(lookback, min_periods=max(5, min(lookback, 20))).std()
        signals[("momentum", lookback)] = ((mid - mid.shift(lookback)) / vol).replace([float("inf"), -float("inf")], 0).fillna(0.0).tolist()

        imb_mean = imbalance.shift(1).rolling(lookback, min_periods=max(5, min(lookback, 20))).mean()
        imb_std = imbalance.shift(1).rolling(lookback, min_periods=max(5, min(lookback, 20))).std()
        signals[("imbalance_z", lookback)] = ((imbalance - imb_mean) / imb_std).replace([float("inf"), -float("inf")], 0).fillna(0.0).tolist()

    bid_levels = [row_levels(row, "bid") for _, row in df.iterrows()]
    ask_levels = [row_levels(row, "ask") for _, row in df.iterrows()]
    return DayData(
        df=df,
        mids=mid.tolist(),
        bid_levels=bid_levels,
        ask_levels=ask_levels,
        signals=signals,
    )


def row_levels(row, side):
    out = []
    for level in (1, 2, 3):
        price = row.get(f"{side}_price_{level}")
        volume = row.get(f"{side}_volume_{level}")
        if pd.isna(price) or pd.isna(volume):
            continue
        out.append((int(price), int(abs(volume))))
    return out


def cross_to(bid_levels, ask_levels, cash, pos, target):
    traded = 0
    fills = 0
    if target > pos:
        need = target - pos
        for price, volume in ask_levels:
            qty = min(need, volume)
            if qty <= 0:
                continue
            cash -= qty * price
            pos += qty
            traded += qty
            fills += 1
            need -= qty
            if need == 0:
                break
    elif target < pos:
        need = pos - target
        for price, volume in bid_levels:
            qty = min(need, volume)
            if qty <= 0:
                continue
            cash += qty * price
            pos -= qty
            traded += qty
            fills += 1
            need -= qty
            if need == 0:
                break
    return cash, pos, traded, fills


def desired_position(candidate: Candidate, raw_signal: float, pos: int):
    signal = raw_signal * candidate.direction
    if signal >= candidate.entry:
        return candidate.target
    if signal <= -candidate.entry:
        return -candidate.target
    if abs(signal) <= candidate.exit:
        return 0
    return pos


def simulate_day(data: DayData, candidate: Candidate):
    key = (candidate.family, 1 if candidate.family == "imbalance" else candidate.lookback)
    signal = data.signals[key]
    cash = 0.0
    pos = 0
    max_abs_pos = 0
    turnover = 0
    fills = 0
    time_at_limit = 0
    pnl = 0.0

    for i, mid in enumerate(data.mids):
        target = desired_position(candidate, signal[i], pos)
        cash, pos, traded, fill_count = cross_to(data.bid_levels[i], data.ask_levels[i], cash, pos, target)
        turnover += traded
        fills += fill_count
        max_abs_pos = max(max_abs_pos, abs(pos))
        if abs(pos) >= candidate.target:
            time_at_limit += 1
        pnl = cash + pos * mid

    if pos:
        cash, pos, traded, fill_count = cross_to(data.bid_levels[-1], data.ask_levels[-1], cash, pos, 0)
        turnover += traded
        fills += fill_count
        pnl = cash

    return pnl, max_abs_pos, turnover, fills, time_at_limit, len(data.df)


def build_candidates(targets):
    candidates = []
    for target in targets:
        for lookback in (10, 20, 50, 100, 200, 500):
            for entry in (0.75, 1.0, 1.25, 1.5, 2.0):
                for exit_value in (0.0, 0.25, 0.5):
                    candidates.append(Candidate("mid_z_revert", "mid_z", lookback, entry, exit_value, -1, target))
                    candidates.append(Candidate("mid_z_trend", "mid_z", lookback, entry, exit_value, 1, target))
            for entry_ticks in (1.0, 2.0, 3.0, 5.0, 8.0):
                candidates.append(Candidate("ema_diff_revert", "ema_diff", lookback, entry_ticks, 0.0, -1, target))
                candidates.append(Candidate("ema_diff_trend", "ema_diff", lookback, entry_ticks, 0.0, 1, target))
            for entry in (2.0, 4.0, 6.0, 8.0, 12.0):
                candidates.append(Candidate("momentum_revert", "momentum", lookback, entry, 0.0, -1, target))
                candidates.append(Candidate("momentum_trend", "momentum", lookback, entry, 0.0, 1, target))
        for entry in (0.05, 0.10, 0.15, 0.20, 0.30):
            candidates.append(Candidate("imbalance_revert", "imbalance", 1, entry, 0.0, -1, target))
            candidates.append(Candidate("imbalance_trend", "imbalance", 1, entry, 0.0, 1, target))
        for lookback in (20, 50, 100, 200):
            for entry in (0.75, 1.0, 1.5, 2.0):
                candidates.append(Candidate("imbalance_z_revert", "imbalance_z", lookback, entry, 0.0, -1, target))
                candidates.append(Candidate("imbalance_z_trend", "imbalance_z", lookback, entry, 0.0, 1, target))
    return candidates


def evaluate(data_by_day, candidate):
    day_pnl = {}
    max_abs_pos = 0
    turnover = 0
    fills = 0
    time_at_limit = 0
    steps = 0
    for day, data in data_by_day.items():
        pnl, day_max, day_turnover, day_fills, day_limit, day_steps = simulate_day(data, candidate)
        day_pnl[day] = pnl
        max_abs_pos = max(max_abs_pos, day_max)
        turnover += day_turnover
        fills += day_fills
        time_at_limit += day_limit
        steps += day_steps
    return Result(candidate, sum(day_pnl.values()), day_pnl, max_abs_pos, turnover, fills, time_at_limit, steps)


def write_results(results, path):
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "name", "family", "lookback", "entry", "exit", "direction",
            "target", "total_pnl", "day0", "day1", "day2", "max_abs_pos",
            "turnover", "fills", "time_at_limit_pct",
        ])
        for rank, result in enumerate(results, 1):
            c = result.candidate
            writer.writerow([
                rank, c.name, c.family, c.lookback, c.entry, c.exit, c.direction,
                c.target, round(result.total_pnl, 2),
                round(result.day_pnl.get(0, 0.0), 2),
                round(result.day_pnl.get(1, 0.0), 2),
                round(result.day_pnl.get(2, 0.0), 2),
                result.max_abs_pos, result.turnover, result.fills,
                round(100.0 * result.time_at_limit / result.steps, 2) if result.steps else 0.0,
            ])


def format_result(rank, result):
    c = result.candidate
    limit_pct = 100.0 * result.time_at_limit / result.steps if result.steps else 0.0
    return (
        f"{rank:4d} {c.name:20s} {c.target:6d} {c.lookback:8d} "
        f"{c.entry:5.2f} {c.exit:4.2f} {c.direction:3d} "
        f"{result.total_pnl:9.0f} {result.day_pnl.get(0, 0):7.0f} "
        f"{result.day_pnl.get(1, 0):7.0f} {result.day_pnl.get(2, 0):7.0f} "
        f"{result.max_abs_pos:7d} {limit_pct:6.2f} {result.turnover:9d}"
    )


def print_table(results, limit):
    print("rank name                 target lookback entry exit dir total_pnl    day0    day1    day2 max_pos limit%  turnover")
    for rank, result in enumerate(results[:limit], 1):
        print(format_result(rank, result))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=ROOT / "data_bt")
    parser.add_argument("--days", nargs="+", type=int, default=[0, 1, 2])
    parser.add_argument("--targets", nargs="+", type=int, default=[50, 100, 150, 200])
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--out", type=Path, default=ROOT / "hydro_active_take_results.csv")
    args = parser.parse_args()

    candidates = build_candidates(args.targets)
    lookbacks = {c.lookback for c in candidates if c.lookback > 1}
    data_by_day = {day: read_day(args.data, day, lookbacks) for day in args.days}

    results = [evaluate(data_by_day, candidate) for candidate in candidates]
    results.sort(key=lambda result: result.total_pnl, reverse=True)
    write_results(results, args.out)

    print_table(results, args.top)
    print(f"\nWrote {len(results)} results to {args.out}")

    print("\nBest by candidate type")
    seen = set()
    best_by_type = []
    for result in results:
        if result.candidate.name in seen:
            continue
        seen.add(result.candidate.name)
        best_by_type.append(result)
    print_table(best_by_type, len(best_by_type))


if __name__ == "__main__":
    main()
