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


TEMPLATE = r'''
import json
from collections import defaultdict
from datamodel import Order, ProsperityEncoder, TradingState

PRODUCT = "HYDROGEL_PACK"
POS_LIM = 200
ROLLING_WINDOW = {rolling_window}
ENTRY_Z = {entry_z}
FULL_Z = {full_z}
SMALL_TARGET = {small_target}
FULL_TARGET = {full_target}
CONFIRM_TICKS = {confirm_ticks}
BOT_MAIN_QTY = 6
BOT_SMALL_QTY = 2
BOT_IMPROVE = 1


class Logger:
    def __init__(self):
        self.logs = ""
    def flush(self, state, orders, conversions, trader_data):
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
        ], cls=ProsperityEncoder, separators=(",", ":")))
        self.logs = ""


logger = Logger()


class Trader:
    def bid(self, state=None):
        return 0

    def run(self, state: TradingState):
        result = defaultdict(list)
        try:
            data = json.loads(state.traderData) if state.traderData else {{}}
        except Exception:
            data = {{}}

        mids = data.get("mids", [])
        macro_target = data.get("macro_target", 0)
        confirm_dir = data.get("confirm_dir", 0)
        confirm_count = data.get("confirm_count", 0)
        od = state.order_depths.get(PRODUCT)

        if od and od.buy_orders and od.sell_orders:
            bids = sorted(od.buy_orders.items(), reverse=True)
            asks = sorted(od.sell_orders.items())
            best_bid = bids[0][0]
            best_ask = asks[0][0]
            mid = (best_bid + best_ask) / 2
            pos = state.position.get(PRODUCT, 0)
            buy_sent = 0
            sell_sent = 0
            z = 0.0

            if len(mids) >= ROLLING_WINDOW:
                window = mids[-ROLLING_WINDOW:]
                mean = sum(window) / ROLLING_WINDOW
                var = sum((x - mean) ** 2 for x in window) / ROLLING_WINDOW
                std = var ** 0.5
                if std > 0:
                    z = (mid - mean) / std
                    desired_dir = 0
                    if z >= ENTRY_Z:
                        desired_dir = -1
                    elif z <= -ENTRY_Z:
                        desired_dir = 1

                    if desired_dir == 0:
                        confirm_dir = 0
                        confirm_count = 0
                    elif desired_dir == confirm_dir:
                        confirm_count += 1
                    else:
                        confirm_dir = desired_dir
                        confirm_count = 1

                    if desired_dir != 0 and confirm_count >= CONFIRM_TICKS:
                        target_size = FULL_TARGET if abs(z) >= FULL_Z else SMALL_TARGET
                        macro_target = desired_dir * target_size

                    target = max(-POS_LIM, min(POS_LIM, macro_target))
                    diff = target - pos
                    if diff > 0:
                        need = min(diff, POS_LIM - pos)
                        if need > 0:
                            result[PRODUCT].append(Order(PRODUCT, asks[-1][0], need))
                            buy_sent += need
                    elif diff < 0:
                        need = min(-diff, POS_LIM + pos)
                        if need > 0:
                            result[PRODUCT].append(Order(PRODUCT, bids[-1][0], -need))
                            sell_sent += need

            # Bot is active when no macro target. This matches the current structure,
            # but lets small targets reduce the damage of weak z-score signals.
            if macro_target == 0:
                buy_price = best_bid + BOT_IMPROVE
                sell_price = best_ask - BOT_IMPROVE
                buy_room = POS_LIM - pos - buy_sent
                sell_room = POS_LIM + pos - sell_sent

                if buy_price < sell_price:
                    if pos > 0:
                        sell_qty = min(BOT_MAIN_QTY, sell_room)
                        buy_qty = min(BOT_SMALL_QTY, buy_room)
                    elif pos < 0:
                        buy_qty = min(BOT_MAIN_QTY, buy_room)
                        sell_qty = min(BOT_SMALL_QTY, sell_room)
                    else:
                        buy_qty = min(BOT_MAIN_QTY, buy_room)
                        sell_qty = min(BOT_MAIN_QTY, sell_room)
                    if buy_qty > 0:
                        result[PRODUCT].append(Order(PRODUCT, buy_price, buy_qty))
                    if sell_qty > 0:
                        result[PRODUCT].append(Order(PRODUCT, sell_price, -sell_qty))

            mids.append(mid)
            data["mids"] = mids[-ROLLING_WINDOW:]
            data["macro_target"] = macro_target
            data["confirm_dir"] = confirm_dir
            data["confirm_count"] = confirm_count

        trader_data = json.dumps(data, separators=(",", ":"))
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data
'''


@dataclass(frozen=True)
class Params:
    rolling_window: int
    entry_z: float
    full_z: float
    small_target: int
    full_target: int
    confirm_ticks: int


def parse(output: str):
    total_match = re.findall(r"Total profit:\s*(-?[\d,]+)", output)
    day_matches = re.findall(r"Round (\d+) day (-?\d+):\s*(-?[\d,]+)", output)
    if not total_match:
        return None, {}
    days = {f"{r}-{d}": int(v.replace(",", "")) for r, d, v in day_matches}
    return int(total_match[-1].replace(",", "")), days


def run_params(params: Params, days: tuple[str, ...]) -> dict:
    source = TEMPLATE.format(**params.__dict__)
    with tempfile.NamedTemporaryFile("w", suffix=".py", prefix="hydro_robust_", delete=False) as f:
        f.write(source)
        path = Path(f.name)
    try:
        proc = subprocess.run(
            [
                "prosperity4btest",
                str(path),
                *days,
                "--data",
                str(ROOT / "data"),
                "--limit",
                "HYDROGEL_PACK:200",
                "--merge-pnl",
                "--no-out",
                "--no-progress",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        output = proc.stdout + proc.stderr
        total, day_pnl = parse(output)
        return {
            "params": params.__dict__,
            "total": total,
            "days": day_pnl,
            "error": None if proc.returncode == 0 and total is not None else output[-800:],
        }
    finally:
        path.unlink(missing_ok=True)


def build_grid() -> list[Params]:
    grid = []
    for rolling_window, entry_z, full_z, small_target, confirm_ticks in itertools.product(
        [700, 800, 900],
        [2.0, 2.2, 2.4],
        [2.4, 2.6, 2.8, 3.0],
        [50, 80, 100, 150],
        [1, 2, 3],
    ):
        if full_z <= entry_z:
            continue
        grid.append(Params(rolling_window, entry_z, full_z, small_target, 200, confirm_ticks))
    return grid


def score(row: dict) -> tuple[int, int, int]:
    days = row["days"]
    all_values = list(days.values())
    bad_day0 = days.get("3-0", -10**9)
    return (min(all_values), bad_day0, row["total"])


def main():
    days = ("3-0", "3-1", "3-2", "4-1", "4-2", "4-3")
    grid = build_grid()
    results = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(run_params, params, days) for params in grid]
        for i, fut in enumerate(as_completed(futures), 1):
            row = fut.result()
            if row["error"] is None:
                results.append(row)
            if i % 50 == 0 and results:
                best = max(results, key=score)
                print(f"{i}/{len(grid)} best_score={score(best)} params={best['params']}", flush=True)

    results.sort(key=score, reverse=True)
    out = {"days": days, "top": results[:80]}
    (ROOT / "hydro_robust_zscore_results.json").write_text(json.dumps(out, indent=2))
    for i, row in enumerate(results[:30], 1):
        print(i, "score", score(row), "total", row["total"], "days", row["days"], row["params"])


if __name__ == "__main__":
    main()
