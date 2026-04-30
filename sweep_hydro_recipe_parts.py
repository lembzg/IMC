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
ROLLING_WINDOW = 700
ENTRY_Z = 2.4
FULL_Z = {full_z}
SMALL_TARGET = {small_target}
FULL_TARGET = 200
EXIT_Z = {exit_z}
USE_TREND = {use_trend}
TREND_SKIP = {trend_skip}
USE_CHUNK = {use_chunk}
MAX_TAKE_PER_TICK = {max_take_per_tick}
BOT_NORMAL_MAIN_QTY = 6
BOT_NORMAL_SMALL_QTY = 2
BOT_IMPROVE = 1

class Logger:
    def __init__(self): self.logs = ""
    def flush(self, state, orders, conversions, trader_data):
        print(json.dumps([[state.timestamp,state.traderData,[[l.symbol,l.product,l.denomination] for l in state.listings.values()],{{s:[od.buy_orders,od.sell_orders] for s,od in state.order_depths.items()}},[[t.symbol,t.price,t.quantity,t.buyer,t.seller,t.timestamp] for trades in state.own_trades.values() for t in trades],[[t.symbol,t.price,t.quantity,t.buyer,t.seller,t.timestamp] for trades in state.market_trades.values() for t in trades],dict(state.position),[state.observations.plainValueObservations,{{p:[o.bidPrice,o.askPrice,o.transportFees,o.exportTariff,o.importTariff,o.sugarPrice,o.sunlightIndex] for p,o in state.observations.conversionObservations.items()}}]],[[o.symbol,o.price,o.quantity] for arr in orders.values() for o in arr],conversions,trader_data,self.logs], cls=ProsperityEncoder, separators=(",",":")))
        self.logs = ""
logger = Logger()

class Trader:
    def bid(self, state=None): return 0
    def run(self, state: TradingState):
        result = defaultdict(list)
        try: data = json.loads(state.traderData) if state.traderData else {{}}
        except Exception: data = {{}}
        mids = data.get("mids", [])
        macro_target = data.get("macro_target", 0)
        od = state.order_depths.get(PRODUCT)
        if od and od.buy_orders and od.sell_orders:
            bids = sorted(od.buy_orders.items(), reverse=True)
            asks = sorted(od.sell_orders.items())
            best_bid = bids[0][0]; best_ask = asks[0][0]
            mid = (best_bid + best_ask) / 2
            pos = state.position.get(PRODUCT, 0)
            buy_sent = 0; sell_sent = 0
            if len(mids) >= ROLLING_WINDOW:
                w = mids[-ROLLING_WINDOW:]
                mean = sum(w) / ROLLING_WINDOW
                var = sum((x - mean) ** 2 for x in w) / ROLLING_WINDOW
                std = var ** 0.5
                if std > 0:
                    z = (mid - mean) / std
                    skip_short = skip_long = False
                    if USE_TREND:
                        short_mean = sum(mids[-100:]) / 100
                        trend = short_mean - mean
                        skip_short = z > 0 and trend > TREND_SKIP
                        skip_long = z < 0 and trend < -TREND_SKIP
                    if z >= FULL_Z and not skip_short:
                        macro_target = -FULL_TARGET
                    elif z >= ENTRY_Z and not skip_short:
                        macro_target = -SMALL_TARGET
                    elif z <= -FULL_Z and not skip_long:
                        macro_target = FULL_TARGET
                    elif z <= -ENTRY_Z and not skip_long:
                        macro_target = SMALL_TARGET
                    elif EXIT_Z > 0 and abs(z) <= EXIT_Z:
                        macro_target = 0
                    target = max(-POS_LIM, min(POS_LIM, macro_target))
                    diff = target - pos
                    if diff > 0:
                        need = min(diff, POS_LIM - pos)
                        if USE_CHUNK:
                            need = min(need, MAX_TAKE_PER_TICK)
                        if need > 0:
                            result[PRODUCT].append(Order(PRODUCT, asks[-1][0], need)); buy_sent += need
                    elif diff < 0:
                        need = min(-diff, POS_LIM + pos)
                        if USE_CHUNK:
                            need = min(need, MAX_TAKE_PER_TICK)
                        if need > 0:
                            result[PRODUCT].append(Order(PRODUCT, bids[-1][0], -need)); sell_sent += need
            if macro_target == 0:
                buy_price = best_bid + BOT_IMPROVE; sell_price = best_ask - BOT_IMPROVE
                buy_room = POS_LIM - pos - buy_sent; sell_room = POS_LIM + pos - sell_sent
                if buy_price < sell_price:
                    if pos > 0:
                        sell_qty = min(BOT_NORMAL_MAIN_QTY, sell_room); buy_qty = min(BOT_NORMAL_SMALL_QTY, buy_room)
                    elif pos < 0:
                        buy_qty = min(BOT_NORMAL_MAIN_QTY, buy_room); sell_qty = min(BOT_NORMAL_SMALL_QTY, sell_room)
                    else:
                        buy_qty = min(BOT_NORMAL_MAIN_QTY, buy_room); sell_qty = min(BOT_NORMAL_MAIN_QTY, sell_room)
                    if buy_qty > 0: result[PRODUCT].append(Order(PRODUCT, buy_price, buy_qty))
                    if sell_qty > 0: result[PRODUCT].append(Order(PRODUCT, sell_price, -sell_qty))
            mids.append(mid); data["mids"] = mids[-ROLLING_WINDOW:]; data["macro_target"] = macro_target
        trader_data = json.dumps(data, separators=(",",":"))
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data
'''


@dataclass(frozen=True)
class Params:
    full_z: float
    small_target: int
    exit_z: float
    use_trend: bool
    trend_skip: float
    use_chunk: bool
    max_take_per_tick: int


def parse(out):
    total = re.findall(r"Total profit:\s*(-?[\d,]+)", out)
    days = re.findall(r"Round (\d+) day (-?\d+):\s*(-?[\d,]+)", out)
    return (int(total[-1].replace(",", "")) if total else None,
            {f"{r}-{d}": int(v.replace(",", "")) for r, d, v in days})


def run(p: Params):
    src = TEMPLATE.format(**p.__dict__)
    with tempfile.NamedTemporaryFile("w", suffix=".py", prefix="hydro_parts_", delete=False) as f:
        f.write(src); path = Path(f.name)
    try:
        proc = subprocess.run(["prosperity4btest", str(path), "3-0", "3-1", "3-2", "4-1", "4-2", "4-3", "--data", str(ROOT / "data"), "--limit", "HYDROGEL_PACK:200", "--merge-pnl", "--no-out", "--no-progress"], capture_output=True, text=True, timeout=180)
        total, days = parse(proc.stdout + proc.stderr)
        return {"params": p.__dict__, "total": total, "days": days, "error": None if proc.returncode == 0 and total is not None else (proc.stdout + proc.stderr)[-800:]}
    finally:
        path.unlink(missing_ok=True)


def main():
    grid = [
        Params(full_z, small, exit_z, use_trend, trend_skip, use_chunk, take)
        for full_z, small, exit_z, use_trend, trend_skip, use_chunk, take in itertools.product(
            [2.8, 3.0, 3.2, 999.0],
            [100, 150, 200],
            [0.0, 0.2, 0.3, 0.5],
            [False, True],
            [15.0, 20.0, 30.0],
            [False, True],
            [40, 80],
        )
    ]
    results = []
    with ProcessPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(run, p) for p in grid]
        for i, fut in enumerate(as_completed(futs), 1):
            row = fut.result()
            if row["error"] is None:
                results.append(row)
            if i % 100 == 0 and results:
                b = max(results, key=lambda r: r["total"])
                print(i, "best", b["total"], min(b["days"].values()), b["params"], flush=True)
    results.sort(key=lambda r: (r["total"], min(r["days"].values())), reverse=True)
    (ROOT / "hydro_recipe_parts_results.json").write_text(json.dumps(results[:80], indent=2))
    for i, r in enumerate(results[:30], 1):
        print(i, "total", r["total"], "min", min(r["days"].values()), "days", r["days"], r["params"])

if __name__ == "__main__":
    main()
