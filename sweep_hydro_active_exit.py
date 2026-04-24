import argparse
import itertools
import json
import re
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PRODUCT = "HYDROGEL_PACK"


TRADER_TEMPLATE = r'''
from collections import defaultdict
import json
from datamodel import Order, TradingState

LOOKBACK = {lookback}
ENTRY = {entry}
EXIT = {exit}
TARGET = {target}
POS_LIMIT = 200
MODE = {mode!r}

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
        pos = state.position.get(product, 0)
        target = pos

        if len(hist) >= LOOKBACK:
            window = hist[-LOOKBACK:]
            mean = sum(window) / len(window)
            var = sum((x - mean) ** 2 for x in window) / len(window)
            std = var ** 0.5
            z = 0.0 if std == 0 else (mid - mean) / std

            if MODE == "revert":
                if z >= ENTRY:
                    target = -TARGET
                elif z <= -ENTRY:
                    target = TARGET
                elif abs(z) <= EXIT:
                    target = 0
            elif MODE == "trend":
                if z >= ENTRY:
                    target = TARGET
                elif z <= -ENTRY:
                    target = -TARGET
                elif abs(z) <= EXIT:
                    target = 0
            elif MODE == "scaled_revert":
                if z >= ENTRY:
                    target = -min(POS_LIMIT, max(1, int(TARGET * min(2.0, abs(z)) / 2.0)))
                elif z <= -ENTRY:
                    target = min(POS_LIMIT, max(1, int(TARGET * min(2.0, abs(z)) / 2.0)))
                elif abs(z) <= EXIT:
                    target = 0

        target = max(-POS_LIMIT, min(POS_LIMIT, target))
        if target > pos:
            need = min(target - pos, POS_LIMIT - pos)
            for ask in asks:
                qty = min(need, -od.sell_orders[ask])
                if qty > 0:
                    orders.append(Order(product, ask, qty))
                    need -= qty
                if need <= 0:
                    break
        elif target < pos:
            need = min(pos - target, POS_LIMIT + pos)
            for bid in bids:
                qty = min(need, od.buy_orders[bid])
                if qty > 0:
                    orders.append(Order(product, bid, -qty))
                    need -= qty
                if need <= 0:
                    break

        hist.append(mid)
        shared["hydro_mid_hist"] = hist[-LOOKBACK:]
        return orders, shared
'''


@dataclass(frozen=True)
class Params:
    mode: str
    lookback: int
    entry: float
    exit: float
    target: int


def parse_pnl(output: str):
    match = re.findall(r"^Total profit:\s*(-?[\d,]+)$", output, re.MULTILINE)
    return int(match[-1].replace(",", "")) if match else None


def parse_day_pnl(output: str):
    days = re.findall(r"Backtesting [^\n]* on round 3 day (-?\d+)\n(?:.*\n)*?HYDROGEL_PACK:\s*(-?[\d,]+)", output)
    return {f"3-{day}": int(pnl.replace(",", "")) for day, pnl in days}


def run_one(params: Params, day_spec: str, data_dir: Path):
    source = TRADER_TEMPLATE.format(**params.__dict__)
    with tempfile.NamedTemporaryFile("w", suffix=".py", prefix="hydro_active_exit_", delete=False) as f:
        f.write(source)
        path = Path(f.name)
    try:
        proc = subprocess.run(
            [
                "prosperity4btest",
                str(path),
                day_spec,
                "--data",
                str(data_dir),
                "--no-out",
                "--no-progress",
                "--merge-pnl",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        output = proc.stdout + proc.stderr
        if proc.returncode != 0:
            return None, output[:400]
        return parse_pnl(output), parse_day_pnl(output), None
    finally:
        path.unlink(missing_ok=True)


def build_grid():
    grid = []
    for mode in ["revert", "scaled_revert"]:
        for lookback in [400, 500, 600, 700, 900, 1000, 1200]:
            for entry in [2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 4.0, 4.5, 5.0]:
                for exit_value in [0.0]:
                    for target in [10, 20, 30, 40, 50, 60, 75, 90]:
                        if exit_value < entry:
                            grid.append(Params(mode, lookback, entry, exit_value, target))
    return grid


def evaluate_params(args_tuple):
    params, day_spec, data_dir = args_tuple
    pnl, day_pnl, failed = run_one(params, day_spec, data_dir)
    if pnl is None and failed is None:
        failed = "parse failure"
    if failed:
        return {"params": params.__dict__, "error": failed}
    return {"params": params.__dict__, "day_pnl": day_pnl, "total_pnl": pnl}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day-spec", default="3")
    parser.add_argument("--data", type=Path, default=ROOT / "data_bt")
    parser.add_argument("--samples", type=int, default=0)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--out", type=Path, default=ROOT / "hydro_active_exit_results.json")
    args = parser.parse_args()

    grid = build_grid()
    if args.samples:
        grid = grid[:args.samples]

    results = []
    completed = 0
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(evaluate_params, (params, args.day_spec, args.data)) for params in grid]
        for fut in as_completed(futures):
            completed += 1
            row = fut.result()
            if "error" in row:
                print(f"[{completed}/{len(grid)}] FAIL {row['params']}: {row['error'][:120]}", flush=True)
                continue
            results.append(row)
            if row["total_pnl"] > 20000 or completed % 25 == 0:
                print(f"[{completed}/{len(grid)}] {row['params']} total={row['total_pnl']}", flush=True)

    results.sort(key=lambda r: r["total_pnl"], reverse=True)
    args.out.write_text(json.dumps(results, indent=2))

    print("\nTOP")
    for rank, row in enumerate(results[:args.top], 1):
        p = row["params"]
        print(
            f"{rank:2d} {p['mode']:13s} lb={p['lookback']:4d} entry={p['entry']:4.2f} "
            f"exit={p['exit']:4.2f} target={p['target']:3d} total={row['total_pnl']:8d} days={row['day_pnl']}"
        )
    print(f"\nWrote {len(results)} results to {args.out}")


if __name__ == "__main__":
    main()
