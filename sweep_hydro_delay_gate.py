import itertools
import json
import re
import subprocess
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent


TEMPLATE = r'''
import json
from collections import defaultdict
from datamodel import Order, ProsperityEncoder, TradingState

PRODUCT = "HYDROGEL_PACK"
POS_LIM = 200
ROLLING_WINDOW = {rolling_window}
ENTRY_Z = {entry_z}
TARGET_SIZE = 200
MACRO_START_TS = {macro_start_ts}
BOT_MAIN_QTY = 6
BOT_SMALL_QTY = 2
BOT_IMPROVE = 1

class Logger:
    def __init__(self):
        self.logs = ""
    def flush(self, state, orders, conversions, trader_data):
        print(json.dumps([
            [state.timestamp, state.traderData, [[l.symbol,l.product,l.denomination] for l in state.listings.values()],
             {{s:[od.buy_orders,od.sell_orders] for s,od in state.order_depths.items()}},
             [[t.symbol,t.price,t.quantity,t.buyer,t.seller,t.timestamp] for trades in state.own_trades.values() for t in trades],
             [[t.symbol,t.price,t.quantity,t.buyer,t.seller,t.timestamp] for trades in state.market_trades.values() for t in trades],
             dict(state.position),
             [state.observations.plainValueObservations, {{p:[o.bidPrice,o.askPrice,o.transportFees,o.exportTariff,o.importTariff,o.sugarPrice,o.sunlightIndex] for p,o in state.observations.conversionObservations.items()}}]],
            [[o.symbol,o.price,o.quantity] for arr in orders.values() for o in arr],
            conversions, trader_data, self.logs
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

            if state.timestamp >= MACRO_START_TS and len(mids) >= ROLLING_WINDOW:
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
        trader_data = json.dumps(data, separators=(",", ":"))
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data
'''


@dataclass(frozen=True)
class Params:
    rolling_window: int
    entry_z: float
    macro_start_ts: int


def parse(output: str):
    total = re.findall(r"Total profit:\s*(-?[\d,]+)", output)
    days = re.findall(r"Round (\d+) day (-?\d+):\s*(-?[\d,]+)", output)
    if not total:
        return None, {}
    return int(total[-1].replace(",", "")), {f"{r}-{d}": int(v.replace(",", "")) for r, d, v in days}


def run(params: Params):
    days = ("3-0", "3-1", "3-2", "4-1", "4-2", "4-3")
    source = TEMPLATE.format(**params.__dict__)
    with tempfile.NamedTemporaryFile("w", suffix=".py", prefix="hydro_delay_", delete=False) as f:
        f.write(source)
        path = Path(f.name)
    try:
        proc = subprocess.run(
            ["prosperity4btest", str(path), *days, "--data", str(ROOT / "data"), "--limit", "HYDROGEL_PACK:200", "--merge-pnl", "--no-out", "--no-progress"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        total, day_pnl = parse(proc.stdout + proc.stderr)
        return {"params": params.__dict__, "total": total, "days": day_pnl, "error": None if proc.returncode == 0 and total is not None else (proc.stdout + proc.stderr)[-800:]}
    finally:
        path.unlink(missing_ok=True)


def main():
    grid = [
        Params(w, e, start)
        for w, e, start in itertools.product(
            [700, 800, 900],
            [1.8, 2.0, 2.2, 2.4],
            [0, 80_000, 120_000, 160_000, 200_000, 250_000, 300_000, 400_000],
        )
    ]
    results = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(run, p) for p in grid]
        for fut in as_completed(futures):
            row = fut.result()
            if row["error"] is None:
                results.append(row)
    results.sort(key=lambda r: (r["total"], min(r["days"].values())), reverse=True)
    (ROOT / "hydro_delay_gate_results.json").write_text(json.dumps(results[:80], indent=2))
    for i, row in enumerate(results[:30], 1):
        print(i, "total", row["total"], "min", min(row["days"].values()), "days", row["days"], row["params"])


if __name__ == "__main__":
    main()
