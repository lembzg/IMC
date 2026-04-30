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
import json
from collections import defaultdict
from datamodel import Order, ProsperityEncoder, TradingState

PRODUCT = "HYDROGEL_PACK"
POS_LIM = 200
ROLLING_WINDOW = {rolling_window}
ENTRY_Z = {entry_z}
TARGET_SIZE = {target_size}
MID_ENTRY_Z = {mid_entry_z}
MID_MODE = {mid_mode!r}
MID_MAIN_QTY = {mid_main_qty}
MID_SMALL_QTY = {mid_small_qty}
MID_IMPROVE = {mid_improve}
BOT_MAIN_QTY = {bot_main_qty}
BOT_SMALL_QTY = {bot_small_qty}
BOT_IMPROVE = {bot_improve}


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
                    if z >= ENTRY_Z:
                        macro_target = -TARGET_SIZE
                    elif z <= -ENTRY_Z:
                        macro_target = TARGET_SIZE

                    diff = max(-POS_LIM, min(POS_LIM, macro_target)) - pos
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

            if macro_target == 0:
                buy_room = POS_LIM - pos - buy_sent
                sell_room = POS_LIM + pos - sell_sent
                buy_price = best_bid + BOT_IMPROVE
                sell_price = best_ask - BOT_IMPROVE
                buy_qty = 0
                sell_qty = 0

                if len(mids) >= ROLLING_WINDOW and abs(z) >= MID_ENTRY_Z:
                    buy_price = best_bid + MID_IMPROVE
                    sell_price = best_ask - MID_IMPROVE
                    if z <= -MID_ENTRY_Z:
                        if MID_MODE == "one_sided":
                            buy_qty = MID_MAIN_QTY
                            sell_qty = 0
                        elif MID_MODE == "skewed":
                            buy_qty = MID_MAIN_QTY
                            sell_qty = MID_SMALL_QTY
                        else:
                            buy_qty = MID_MAIN_QTY
                            sell_qty = MID_SMALL_QTY if pos >= 0 else BOT_MAIN_QTY
                    else:
                        if MID_MODE == "one_sided":
                            buy_qty = 0
                            sell_qty = MID_MAIN_QTY
                        elif MID_MODE == "skewed":
                            buy_qty = MID_SMALL_QTY
                            sell_qty = MID_MAIN_QTY
                        else:
                            buy_qty = MID_SMALL_QTY if pos <= 0 else BOT_MAIN_QTY
                            sell_qty = MID_MAIN_QTY
                elif pos > 0:
                    sell_qty = BOT_MAIN_QTY
                    buy_qty = BOT_SMALL_QTY
                elif pos < 0:
                    buy_qty = BOT_MAIN_QTY
                    sell_qty = BOT_SMALL_QTY
                else:
                    buy_qty = BOT_MAIN_QTY
                    sell_qty = BOT_MAIN_QTY

                if buy_price < sell_price:
                    if buy_qty > 0 and buy_room > 0:
                        result[PRODUCT].append(Order(PRODUCT, buy_price, min(buy_qty, buy_room)))
                    if sell_qty > 0 and sell_room > 0:
                        result[PRODUCT].append(Order(PRODUCT, sell_price, -min(sell_qty, sell_room)))

            mids.append(mid)
            data["mids"] = mids[-ROLLING_WINDOW:]
            data["macro_target"] = macro_target

        trader_data = json.dumps(data, separators=(",", ":"))
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data
'''


@dataclass(frozen=True)
class Params:
    rolling_window: int = 800
    entry_z: float = 2.0
    target_size: int = 200
    mid_entry_z: float = 1.25
    mid_mode: str = "skewed"
    mid_main_qty: int = 10
    mid_small_qty: int = 2
    mid_improve: int = 1
    bot_main_qty: int = 6
    bot_small_qty: int = 2
    bot_improve: int = 1


def parse_total(output: str) -> int | None:
    totals = re.findall(r"Total profit:\s*(-?[\d,]+)", output)
    if not totals:
        return None
    return int(totals[-1].replace(",", ""))


def run_params(params: Params, days: tuple[str, ...]) -> dict:
    source = TRADER_TEMPLATE.format(**params.__dict__)
    with tempfile.NamedTemporaryFile("w", suffix=".py", prefix="hydro_mid_", delete=False) as f:
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
            timeout=120,
        )
        output = proc.stdout + proc.stderr
        total = parse_total(output)
        return {
            "params": params.__dict__,
            "days": days,
            "total": total,
            "error": None if proc.returncode == 0 and total is not None else output[-800:],
        }
    finally:
        path.unlink(missing_ok=True)


def build_grid() -> list[Params]:
    grid = []
    for mid_entry_z, mid_mode, mid_main_qty, mid_small_qty, mid_improve in itertools.product(
        [0.6, 0.8, 1.0, 1.2, 1.4, 1.6],
        ["skewed", "one_sided", "inventory_aware"],
        [4, 6, 8, 10, 14, 20, 30],
        [0, 1, 2, 4, 6],
        [1, 2],
    ):
        if mid_small_qty >= mid_main_qty:
            continue
        grid.append(
            Params(
                mid_entry_z=mid_entry_z,
                mid_mode=mid_mode,
                mid_main_qty=mid_main_qty,
                mid_small_qty=mid_small_qty,
                mid_improve=mid_improve,
            )
        )
    return grid


def main():
    train_days = ("4-1", "4-2")
    test_days = ("4-3",)
    grid = build_grid()
    results = []

    with ProcessPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(run_params, params, train_days) for params in grid]
        for i, fut in enumerate(as_completed(futures), 1):
            row = fut.result()
            if row["error"] is None:
                results.append(row)
            if i % 100 == 0 and results:
                best = max(results, key=lambda r: r["total"])
                print(f"{i}/{len(grid)} train_best={best['total']} {best['params']}", flush=True)

    results.sort(key=lambda r: r["total"], reverse=True)
    top = results[:25]
    tested = []
    for row in top:
        params = Params(**row["params"])
        test = run_params(params, test_days)
        tested.append({"train": row, "test": test})

    out = {
        "train_days": train_days,
        "test_days": test_days,
        "top_tested": tested,
        "top_train": results[:50],
    }
    (ROOT / "hydro_mid_layer_sweep_results.json").write_text(json.dumps(out, indent=2))

    print("Top train/test:")
    for i, row in enumerate(tested[:25], 1):
        print(i, "train", row["train"]["total"], "test", row["test"]["total"], row["train"]["params"])


if __name__ == "__main__":
    main()
