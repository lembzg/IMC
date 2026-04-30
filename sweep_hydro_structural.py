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
EXIT_Z = {exit_z}
TARGET_MODE = {target_mode!r}
BASE_TARGET = {base_target}
MAX_TARGET = {max_target}
DECAY_STEP = {decay_step}
KEEP_BOT = {keep_bot}
GATE_MODE = {gate_mode!r}
TREND_LOOKBACK = {trend_lookback}
TREND_MAX = {trend_max}
FLIP_MIN = {flip_min}
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


def clip(v, lo, hi):
    return max(lo, min(hi, v))


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
        z_signs = data.get("z_signs", [])
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
            macro_allowed = True

            if len(mids) >= ROLLING_WINDOW:
                window = mids[-ROLLING_WINDOW:]
                mean = sum(window) / ROLLING_WINDOW
                var = sum((x - mean) ** 2 for x in window) / ROLLING_WINDOW
                std = var ** 0.5
                if std > 0:
                    z = (mid - mean) / std
                    sign = 1 if z > ENTRY_Z else (-1 if z < -ENTRY_Z else 0)
                    if sign != 0:
                        z_signs.append(sign)
                    z_signs = z_signs[-20:]

                    if GATE_MODE == "trend" and len(mids) >= TREND_LOOKBACK:
                        trend = abs(mid - mids[-TREND_LOOKBACK])
                        macro_allowed = trend <= TREND_MAX
                    elif GATE_MODE == "flips":
                        flips = 0
                        prev = 0
                        for s in z_signs:
                            if prev != 0 and s != prev:
                                flips += 1
                            prev = s
                        macro_allowed = flips >= FLIP_MIN
                    elif GATE_MODE == "both" and len(mids) >= TREND_LOOKBACK:
                        trend = abs(mid - mids[-TREND_LOOKBACK])
                        flips = 0
                        prev = 0
                        for s in z_signs:
                            if prev != 0 and s != prev:
                                flips += 1
                            prev = s
                        macro_allowed = trend <= TREND_MAX and flips >= FLIP_MIN

                    desired_dir = 0
                    if macro_allowed:
                        if z >= ENTRY_Z:
                            desired_dir = -1
                        elif z <= -ENTRY_Z:
                            desired_dir = 1

                    if desired_dir != 0:
                        if TARGET_MODE == "fixed":
                            size = MAX_TARGET
                        elif TARGET_MODE == "tiered":
                            size = BASE_TARGET if abs(z) < ENTRY_Z + 0.5 else MAX_TARGET
                        else:
                            raw = BASE_TARGET + int((abs(z) - ENTRY_Z) * 80)
                            size = clip(raw, BASE_TARGET, MAX_TARGET)
                        macro_target = desired_dir * size
                    elif EXIT_Z > 0 and abs(z) <= EXIT_Z:
                        if DECAY_STEP >= MAX_TARGET:
                            macro_target = 0
                        elif macro_target > 0:
                            macro_target = max(0, macro_target - DECAY_STEP)
                        elif macro_target < 0:
                            macro_target = min(0, macro_target + DECAY_STEP)

                    target = clip(macro_target, -POS_LIM, POS_LIM)
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

            if macro_target == 0 or KEEP_BOT:
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

                    # During macro, only quote the inventory-reducing side plus the side
                    # that moves toward target. This preserves spread capture without
                    # fighting the macro too much.
                    if KEEP_BOT and macro_target > 0:
                        sell_qty = min(sell_qty, BOT_SMALL_QTY)
                    elif KEEP_BOT and macro_target < 0:
                        buy_qty = min(buy_qty, BOT_SMALL_QTY)

                    if buy_qty > 0 and buy_room > 0:
                        result[PRODUCT].append(Order(PRODUCT, buy_price, min(buy_qty, buy_room)))
                    if sell_qty > 0 and sell_room > 0:
                        result[PRODUCT].append(Order(PRODUCT, sell_price, -min(sell_qty, sell_room)))

            mids.append(mid)
            data["mids"] = mids[-ROLLING_WINDOW:]
            data["macro_target"] = macro_target
            data["z_signs"] = z_signs

        trader_data = json.dumps(data, separators=(",", ":"))
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data
'''


@dataclass(frozen=True)
class Params:
    rolling_window: int
    entry_z: float
    exit_z: float
    target_mode: str
    base_target: int
    max_target: int
    decay_step: int
    keep_bot: bool
    gate_mode: str
    trend_lookback: int
    trend_max: float
    flip_min: int


def parse(output: str):
    total = re.findall(r"Total profit:\s*(-?[\d,]+)", output)
    days = re.findall(r"Round (\d+) day (-?\d+):\s*(-?[\d,]+)", output)
    if not total:
        return None, {}
    return int(total[-1].replace(",", "")), {f"{r}-{d}": int(v.replace(",", "")) for r, d, v in days}


def run(params: Params):
    days = ("3-0", "3-1", "3-2", "4-1", "4-2", "4-3")
    source = TEMPLATE.format(**params.__dict__)
    with tempfile.NamedTemporaryFile("w", suffix=".py", prefix="hydro_struct_", delete=False) as f:
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


def build_grid():
    base = []
    # Focus around the known good 700/2.4 and old 800/2.0 regimes.
    for rolling_window, entry_z in [(700, 2.2), (700, 2.4), (700, 2.6), (800, 2.0), (800, 2.2), (900, 1.8)]:
        for target_mode, base_target, max_target, keep_bot in itertools.product(
            ["fixed", "tiered", "scaled"],
            [80, 120, 150, 200],
            [150, 200],
            [False, True],
        ):
            if base_target > max_target:
                continue
            for exit_z, decay_step in [(0.0, 200), (0.5, 50), (0.8, 50), (1.0, 100), (1.2, 100)]:
                base.append(Params(rolling_window, entry_z, exit_z, target_mode, base_target, max_target, decay_step, keep_bot, "none", 100, 9999.0, 0))
    # Smaller regime gate set.
    for rolling_window, entry_z, gate_mode in itertools.product([700, 800], [2.0, 2.4], ["trend", "flips", "both"]):
        for trend_lookback, trend_max, flip_min in itertools.product([100, 200, 400], [20.0, 35.0, 50.0], [1, 2, 3]):
            base.append(Params(rolling_window, entry_z, 0.0, "fixed", 200, 200, 200, False, gate_mode, trend_lookback, trend_max, flip_min))
    return base


def main():
    results = []
    grid = build_grid()
    with ProcessPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(run, p) for p in grid]
        for i, fut in enumerate(as_completed(futures), 1):
            row = fut.result()
            if row["error"] is None:
                results.append(row)
            if i % 100 == 0 and results:
                best = max(results, key=lambda r: r["total"])
                print(f"{i}/{len(grid)} best_total={best['total']} min={min(best['days'].values())} params={best['params']}", flush=True)
    results.sort(key=lambda r: (r["total"], min(r["days"].values())), reverse=True)
    (ROOT / "hydro_structural_results.json").write_text(json.dumps(results[:100], indent=2))
    for i, row in enumerate(results[:40], 1):
        print(i, "total", row["total"], "min", min(row["days"].values()), "days", row["days"], row["params"])


if __name__ == "__main__":
    main()
