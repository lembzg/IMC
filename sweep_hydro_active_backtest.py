import argparse
import itertools
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PRODUCT = "HYDROGEL_PACK"


TRADER_TEMPLATE = r'''
from collections import defaultdict
import json
from datamodel import Order, TradingState

MODE = {mode!r}
LOOKBACK = {lookback}
ENTRY = {entry}
DIRECTION = {direction}
TARGET = {target}
POS_LIMIT = 200

class Logger:
    def __init__(self):
        self.logs = ""
    def flush(self, state: TradingState, orders: dict, conversions: int, trader_data: str):
        print(json.dumps([
            [
                state.timestamp,
                state.traderData,
                [[l.symbol, l.product, l.denomination] for l in state.listings.values()],
                {{s: [od.buy_orders, od.sell_orders] for s, od in state.order_depths.items()}},
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp] for trades in state.own_trades.values() for t in trades],
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp] for trades in state.market_trades.values() for t in trades],
                dict(state.position),
                [state.observations.plainValueObservations, {{
                    p: [o.bidPrice, o.askPrice, o.transportFees, o.exportTariff, o.importTariff, o.sugarPrice, o.sunlightIndex]
                    for p, o in state.observations.conversionObservations.items()
                }}],
            ],
            [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr],
            conversions,
            trader_data,
            self.logs,
        ], separators=(",", ":")))
        self.logs = ""

logger = Logger()

class Trader:
    def run(self, state: TradingState):
        result = defaultdict(list)
        conversions = 0
        shared = {{}}
        if state.traderData:
            try:
                shared = json.loads(state.traderData)
            except json.JSONDecodeError:
                pass
        result["HYDROGEL_PACK"], data = self.hydro(state, shared)
        trader_data = json.dumps(data)
        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data

    def hydro(self, state: TradingState, shared: dict):
        product = "HYDROGEL_PACK"
        orders = []
        if product not in state.order_depths:
            return orders, shared
        od = state.order_depths[product]
        bids = sorted(od.buy_orders.keys(), reverse=True)
        asks = sorted(od.sell_orders.keys())
        if not bids or not asks:
            return orders, shared

        mid = (bids[0] + asks[0]) / 2.0
        hist = shared.get("hydro_mid_hist", [])
        rets = shared.get("hydro_ret_hist", [])
        prev_mid = shared.get("hydro_prev_mid")
        if prev_mid is not None:
            rets.append(mid - prev_mid)
            rets = rets[-LOOKBACK:]

        signal = 0.0
        if MODE == "ema":
            alpha = 2.0 / (LOOKBACK + 1.0)
            ema = shared.get("hydro_ema")
            if ema is None:
                ema = mid
            else:
                signal = mid - ema
            shared["hydro_ema"] = alpha * mid + (1 - alpha) * ema
        elif len(hist) >= max(5, min(LOOKBACK, 20)):
            if MODE == "mid_z":
                window = hist[-LOOKBACK:]
                mean = sum(window) / len(window)
                var = sum((x - mean) ** 2 for x in window) / len(window)
                std = var ** 0.5
                signal = 0.0 if std == 0 else (mid - mean) / std
            elif MODE == "momentum" and len(hist) >= LOOKBACK and len(rets) >= max(5, min(LOOKBACK, 20)):
                move = mid - hist[-LOOKBACK]
                mean_ret = sum(rets) / len(rets)
                var = sum((x - mean_ret) ** 2 for x in rets) / len(rets)
                std = var ** 0.5
                signal = 0.0 if std == 0 else move / std

        pos = state.position.get(product, 0)
        target = pos
        directed = DIRECTION * signal
        if directed >= ENTRY:
            target = TARGET
        elif directed <= -ENTRY:
            target = -TARGET

        target = max(-POS_LIMIT, min(POS_LIMIT, target))
        if target > pos:
            need = min(target - pos, POS_LIMIT - pos)
            for ask in asks:
                available = -od.sell_orders[ask]
                qty = min(need, available)
                if qty > 0:
                    orders.append(Order(product, ask, qty))
                    need -= qty
                if need <= 0:
                    break
        elif target < pos:
            need = min(pos - target, POS_LIMIT + pos)
            for bid in bids:
                available = od.buy_orders[bid]
                qty = min(need, available)
                if qty > 0:
                    orders.append(Order(product, bid, -qty))
                    need -= qty
                if need <= 0:
                    break

        hist.append(mid)
        shared["hydro_mid_hist"] = hist[-LOOKBACK:]
        shared["hydro_ret_hist"] = rets
        shared["hydro_prev_mid"] = mid
        return orders, shared
'''


@dataclass(frozen=True)
class Params:
    mode: str
    lookback: int
    entry: float
    direction: int
    target: int = 200


def parse_pnl(output: str):
    match = re.findall(rf"^{PRODUCT}:\s*(-?[\d,]+)$", output, re.MULTILINE)
    if not match:
        return None
    return int(match[-1].replace(",", ""))


def run_one(params: Params, day: str, data_dir: Path):
    source = TRADER_TEMPLATE.format(**params.__dict__)
    with tempfile.NamedTemporaryFile("w", suffix=".py", prefix="hydro_active_", delete=False) as f:
        f.write(source)
        trader_path = Path(f.name)
    try:
        proc = subprocess.run(
            ["prosperity4btest", str(trader_path), day, "--data", str(data_dir), "--no-out", "--no-progress"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        output = proc.stdout + proc.stderr
        if proc.returncode != 0:
            return None, output.strip()
        return parse_pnl(output), None
    finally:
        trader_path.unlink(missing_ok=True)


def build_grid():
    grid = [
        Params("ema", 50, entry, direction)
        for entry, direction in itertools.product([2.0, 5.0, 8.0], [1, -1])
    ]
    grid += [
        Params("ema", 100, entry, direction)
        for entry, direction in itertools.product([2.0, 5.0], [1, -1])
    ]
    grid += [Params("ema", 500, entry, -1) for entry in [8.0, 12.0, 16.0]]

    grid += [
        Params("mid_z", 50, entry, direction)
        for entry, direction in itertools.product([1.25, 1.5, 2.0], [1, -1])
    ]
    grid += [Params("mid_z", 100, entry, 1) for entry in [0.75, 1.0, 1.5]]
    grid += [Params("mid_z", 500, entry, -1) for entry in [1.25, 1.5, 2.0, 2.5, 3.0]]

    grid += [
        Params("momentum", 50, entry, direction)
        for entry, direction in itertools.product([4.0, 8.0, 12.0, 16.0, 20.0], [1, -1])
    ]
    return grid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", nargs="+", default=["3-0", "3-1", "3-2"])
    parser.add_argument("--data", type=Path, default=ROOT / "data_bt")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--out", type=Path, default=ROOT / "hydro_active_backtest_results.json")
    args = parser.parse_args()

    results = []
    grid = build_grid()
    for i, params in enumerate(grid, 1):
        day_pnl = {}
        failed = None
        for day in args.days:
            pnl, err = run_one(params, day, args.data)
            if err is not None or pnl is None:
                failed = err or "could not parse pnl"
                break
            day_pnl[day] = pnl
        if failed:
            print(f"[{i}/{len(grid)}] FAIL {params}: {failed[:120]}")
            continue
        total = sum(day_pnl.values())
        row = {"params": params.__dict__, "day_pnl": day_pnl, "total_pnl": total}
        results.append(row)
        print(f"[{i}/{len(grid)}] {params} total={total}", flush=True)

    results.sort(key=lambda r: r["total_pnl"], reverse=True)
    args.out.write_text(json.dumps(results, indent=2))

    print("\nTOP")
    for rank, row in enumerate(results[:args.top], 1):
        p = row["params"]
        print(
            f"{rank:2d} {p['mode']:8s} lb={p['lookback']:3d} entry={p['entry']:4.2f} "
            f"dir={p['direction']:2d} target={p['target']:3d} total={row['total_pnl']:8d} days={row['day_pnl']}"
        )
    print(f"\nWrote {len(results)} results to {args.out}")


if __name__ == "__main__":
    main()
