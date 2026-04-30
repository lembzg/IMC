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
from collections import defaultdict
import json
from datamodel import Order, TradingState

POS_LIM = 200
QUOTE_QTY = {quote_qty}
IMPROVE = {improve}
MODE = {mode!r}
LOOKBACK = {lookback}
ENTRY_Z = {entry_z}

class Logger:
    def __init__(self): self.logs = ""
    def flush(self, state, orders, conversions, trader_data):
        print(json.dumps([[state.timestamp,state.traderData,[[l.symbol,l.product,l.denomination]for l in state.listings.values()],{{s:[od.buy_orders,od.sell_orders]for s,od in state.order_depths.items()}},[[t.symbol,t.price,t.quantity,t.buyer,t.seller,t.timestamp]for trades in state.own_trades.values()for t in trades],[[t.symbol,t.price,t.quantity,t.buyer,t.seller,t.timestamp]for trades in state.market_trades.values()for t in trades],dict(state.position),[state.observations.plainValueObservations,{{p:[o.bidPrice,o.askPrice,o.transportFees,o.exportTariff,o.importTariff,o.sugarPrice,o.sunlightIndex]for p,o in state.observations.conversionObservations.items()}}]],[[o.symbol,o.price,o.quantity]for arr in orders.values()for o in arr],conversions,trader_data,self.logs],separators=(",",":")))
        self.logs = ""
logger = Logger()

class Trader:
    def bid(self, state=None):
        return 1

    def run(self, state: TradingState):
        result = defaultdict(list)
        data = {{}}
        if state.traderData:
            try: data = json.loads(state.traderData)
            except Exception: data = {{}}

        od = state.order_depths.get("HYDROGEL_PACK")
        if od and od.buy_orders and od.sell_orders:
            bids = sorted(od.buy_orders.keys(), reverse=True)
            asks = sorted(od.sell_orders.keys())
            best_bid = bids[0]
            best_ask = asks[0]
            mid = (best_bid + best_ask) / 2.0
            pos = state.position.get("HYDROGEL_PACK", 0)
            prev_pos = data.get("p", 0)
            last_dir = data.get("d")
            hist = data.get("h", [])

            if pos > prev_pos:
                last_dir = "buy"
            elif pos < prev_pos:
                last_dir = "sell"

            z = 0.0
            if len(hist) >= LOOKBACK:
                w = hist[-LOOKBACK:]
                mean = sum(w) / LOOKBACK
                var = sum((x - mean) * (x - mean) for x in w) / LOOKBACK
                z = 0.0 if var <= 0 else (mid - mean) / (var ** 0.5)

            buy_room = POS_LIM - pos
            sell_room = POS_LIM + pos
            bid_px = best_bid + IMPROVE
            ask_px = best_ask - IMPROVE

            allow_buy = buy_room > 0
            allow_sell = sell_room > 0
            if MODE in ("cycle_z", "both_z"):
                if z <= -ENTRY_Z:
                    allow_sell = False
                elif z >= ENTRY_Z:
                    allow_buy = False

            if bid_px < ask_px:
                if MODE in ("both", "both_z"):
                    if allow_buy:
                        result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", bid_px, min(QUOTE_QTY, buy_room)))
                    if allow_sell:
                        result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", ask_px, -min(QUOTE_QTY, sell_room)))
                else:
                    if pos > 0 and allow_sell:
                        result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", ask_px, -min(pos, sell_room)))
                    elif pos < 0 and allow_buy:
                        result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", bid_px, min(-pos, buy_room)))
                    elif last_dir == "buy" and allow_sell:
                        result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", ask_px, -min(QUOTE_QTY, sell_room)))
                    elif last_dir == "sell" and allow_buy:
                        result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", bid_px, min(QUOTE_QTY, buy_room)))
                    else:
                        if allow_buy:
                            result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", bid_px, min(QUOTE_QTY, buy_room)))
                        if allow_sell:
                            result["HYDROGEL_PACK"].append(Order("HYDROGEL_PACK", ask_px, -min(QUOTE_QTY, sell_room)))

            hist.append(mid)
            data["h"] = hist[-LOOKBACK:]
            data["p"] = pos
            data["d"] = last_dir

        trader_data = json.dumps(data, separators=(",", ":"))
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data
'''


@dataclass(frozen=True)
class Params:
    quote_qty: int
    improve: int
    mode: str
    lookback: int
    entry_z: float


def parse(output: str):
    days = re.findall(r"round 4 day (\d+)\n(?:.*?\n)*?HYDROGEL_PACK:\s*(-?[\d,]+)", output)
    total = re.findall(r"Total profit:\s*(-?[\d,]+)", output)
    if not total:
        return None, {}
    return int(total[-1].replace(",", "")), {int(d): int(v.replace(",", "")) for d, v in days}


def run_one(params: Params):
    source = TEMPLATE.format(**params.__dict__)
    with tempfile.NamedTemporaryFile("w", suffix=".py", prefix="hydro_sweep_", delete=False) as f:
        f.write(source)
        path = Path(f.name)
    try:
        proc = subprocess.run(
            [
                "prosperity4btest",
                str(path),
                "4-1",
                "4-2",
                "4-3",
                "--data",
                str(ROOT / "data"),
                "--merge-pnl",
                "--no-out",
                "--no-progress",
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if proc.returncode != 0:
            return {"params": params.__dict__, "error": (proc.stdout + proc.stderr)[-500:]}
        total, days = parse(proc.stdout + proc.stderr)
        if total is None:
            return {"params": params.__dict__, "error": "parse failure"}
        return {"params": params.__dict__, "total": total, "days": days}
    finally:
        path.unlink(missing_ok=True)


def main():
    grid = [
        Params(q, improve, mode, 500, 1.5)
        for q, improve, mode in itertools.product(
            [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 30, 40, 60, 100, 150, 200],
            [0, 1, 2, 3, 4, 5, 6, 7],
            ["cycle", "cycle_z", "both", "both_z"],
        )
    ]
    results = []
    with ProcessPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(run_one, p) for p in grid]
        for i, fut in enumerate(as_completed(futures), 1):
            row = fut.result()
            if "error" not in row:
                results.append(row)
            if i % 50 == 0:
                best = max(results, key=lambda r: r["total"]) if results else None
                print(f"{i}/{len(grid)} best={best}", flush=True)

    results.sort(key=lambda r: (min(r["days"].values()), r["total"]), reverse=True)
    (ROOT / "hydro_btest_sweep_results.json").write_text(json.dumps(results, indent=2))
    for rank, row in enumerate(results[:40], 1):
        print(rank, row)


if __name__ == "__main__":
    main()
