"""
trader_vev.py — Best VEV-only strategy
=======================================
VEV options: dynamic-qty spread-filtered mean reversion.
  - Frozen anchor (ALPHA_SLOW=0.0): reference price never moves from first observed tick.
  - Only trade when deviation >= MIN_DEV_FRAC * spread (filters unprofitable small-dev trades).
  - qty proportional to deviation/spread ratio (sizes up on high-conviction signals).
  - HYDROGEL_PACK and spot included (they don't hurt and HYDRO adds ~20k).

Best VEV-only backtest: ~93,911 across all 3 round-3 days.
Combined with HYDRO: ~111,556.
"""

import json
from datamodel import Order, Symbol, TradingState
from typing import Dict, List, Tuple, Optional


# ── VEV Options parameters ─────────────────────────────────────────────────────
OPT_LIMITS: Dict[str, int] = {
    "VEV_4000": 300, "VEV_4500": 300, "VEV_5000": 300,
    "VEV_5100": 300, "VEV_5200": 300, "VEV_5300": 300,
    "VEV_5400": 300, "VEV_5500": 300,
}
ALPHA_FAST    = 0.97
ALPHA_SLOW    = 0.0       # frozen anchor — reference price fixed at first tick
EXT_ALPHA     = 0.01
EXT_THR       = 10.0
STOP_LOSS     = -10000

MIN_DEV_FRAC  = 0.9       # deviation must be >= 0.9 × spread to trade
QTY_DIV_SCALE = 0.4       # qty = int(dev / (spread × 0.4))
MAX_QTY       = 8         # cap per signal

# ── HYDROGEL_PACK parameters ───────────────────────────────────────────────────
HYDRO_POS_LIM    = 200
HYDRO_STEP_SIZE  = 20
HYDRO_MAX_SPREAD = 20

HYDRO_BUY_TIERS = [
    (9925, 70),
    (9930, 60),
    (9935, 50),
    (9940, 40),
]
HYDRO_SELL_TIERS = [
    (10040, 70),
    (10035, 60),
    (10030, 50),
    (10025, 40),
]


class Logger:
    def __init__(self):
        self.logs = ""

    def print(self, *objects, sep=" ", end="\n"):
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict, conversions: int, trader_data: str):
        print(json.dumps([
            [
                state.timestamp, state.traderData,
                [[l.symbol, l.product, l.denomination] for l in state.listings.values()],
                {s: [od.buy_orders, od.sell_orders] for s, od in state.order_depths.items()},
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
                 for trades in state.own_trades.values() for t in trades],
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp]
                 for trades in state.market_trades.values() for t in trades],
                dict(state.position),
                [state.observations.plainValueObservations, {
                    p: [o.bidPrice, o.askPrice, o.transportFees, o.exportTariff,
                        o.importTariff, o.sugarPrice, o.sunlightIndex]
                    for p, o in state.observations.conversionObservations.items()
                }],
            ],
            [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr],
            conversions, trader_data, self.logs,
        ], separators=(",", ":")))
        self.logs = ""


logger = Logger()


class Trader:
    def bid(self):
        return 1

    def run(self, state: TradingState) -> Tuple[Dict[Symbol, List[Order]], int, str]:
        saved: dict = {}
        if state.traderData:
            try:
                saved = json.loads(state.traderData)
            except Exception:
                pass

        result: Dict[Symbol, List[Order]] = {}

        # ── Spot mid (for extrinsic value calc only — no spot orders) ──────────
        spot_depth = state.order_depths.get("VELVETFRUIT_EXTRACT")
        spot_mid: Optional[float] = None
        if spot_depth and spot_depth.buy_orders and spot_depth.sell_orders:
            spot_mid = (max(spot_depth.buy_orders) + min(spot_depth.sell_orders)) / 2.0

        # ── Options: dynamic-qty spread-filtered mean reversion ───────────────
        ema_fast: Dict[str, float] = saved.get("f", {})
        ema_slow: Dict[str, float] = saved.get("s", {})
        ext_ema:  Dict[str, float] = saved.get("e", {})

        for product, limit in OPT_LIMITS.items():
            depth = state.order_depths.get(product)
            if not depth or not depth.buy_orders or not depth.sell_orders:
                continue

            best_ask = min(depth.sell_orders)
            best_bid = max(depth.buy_orders)
            spread    = best_ask - best_bid
            mid_price = (best_ask + best_bid) / 2.0

            if product not in ema_fast:
                ema_fast[product] = mid_price
                ema_slow[product] = mid_price
            else:
                ema_fast[product] = ALPHA_FAST * mid_price + (1 - ALPHA_FAST) * ema_fast[product]
                ema_slow[product] = ALPHA_SLOW * mid_price + (1 - ALPHA_SLOW) * ema_slow[product]

            expected_price = ema_slow[product]
            momentum       = mid_price - ema_fast[product]

            extrinsic = mid_price
            ev_mavg   = 0.0
            if spot_mid is not None:
                strike    = int(product.split("_")[1])
                intrinsic = max(0.0, spot_mid - strike)
                extrinsic = mid_price - intrinsic
                prev = ext_ema.get(product)
                ext_ema[product] = extrinsic if prev is None else EXT_ALPHA * extrinsic + (1 - EXT_ALPHA) * prev
                ev_mavg = ext_ema[product]

            current_pos = state.position.get(product, 0)
            to_buy  = limit - current_pos
            to_sell = limit + current_pos

            orders: List[Order] = []

            # Stop-loss
            own_trades = state.own_trades.get(product, [])
            if own_trades:
                mid_pnl  = (best_bid + best_ask) / 2.0
                realized = sum((t.price - mid_pnl) * t.quantity for t in own_trades)
                if realized < STOP_LOSS:
                    if current_pos > 0:
                        orders.append(Order(product, best_bid, -current_pos))
                    elif current_pos < 0:
                        orders.append(Order(product, best_ask, -current_pos))
                    if orders:
                        result[product] = orders
                    continue

            # Signal: only trade when deviation >= MIN_DEV_FRAC * spread
            min_dev  = spread * MIN_DEV_FRAC
            buy_dev  = expected_price - best_ask   # positive = ask is below fair value
            sell_dev = best_bid - expected_price    # positive = bid is above fair value

            take_buy  = (buy_dev  >= min_dev or momentum < -8) and to_buy  > 0
            take_sell = (sell_dev >= min_dev or momentum >  8) and to_sell > 0

            if ev_mavg > 0:
                if extrinsic > ev_mavg + EXT_THR:
                    take_sell = True
                elif extrinsic < ev_mavg - EXT_THR:
                    take_buy = True

            if take_buy and to_buy > 0:
                dev = max(buy_dev, min_dev)
                qty = max(1, min(MAX_QTY, int(dev / max(1, spread * QTY_DIV_SCALE))))
                qty = min(qty, to_buy, -depth.sell_orders[best_ask])
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))

            if take_sell and to_sell > 0:
                dev = max(sell_dev, min_dev)
                qty = max(1, min(MAX_QTY, int(dev / max(1, spread * QTY_DIV_SCALE))))
                qty = min(qty, to_sell, depth.buy_orders[best_bid])
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))

            if orders:
                result[product] = orders

        saved["f"] = {k: round(v, 2) for k, v in ema_fast.items()}
        saved["s"] = {k: round(v, 2) for k, v in ema_slow.items()}
        saved["e"] = {k: round(v, 2) for k, v in ext_ema.items()}

        # ── HYDROGEL_PACK: tier-based range strategy ──────────────────────────
        hydro_orders = self._hydro_range(state)
        if hydro_orders:
            result["HYDROGEL_PACK"] = hydro_orders

        trader_data = json.dumps(saved)
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data

    def _hydro_range(self, state: TradingState) -> List[Order]:
        product = "HYDROGEL_PACK"
        od = state.order_depths.get(product)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        spread   = best_ask - best_bid
        if spread > HYDRO_MAX_SPREAD or spread <= 0:
            return []

        mid = (best_bid + best_ask) / 2.0
        pos = state.position.get(product, 0)

        if mid < 9820 and pos > 0:
            return [Order(product, int(best_bid), -pos)]
        if mid > 10100 and pos < 0:
            return [Order(product, int(best_ask), -pos)]

        buy_room  = HYDRO_POS_LIM - pos
        sell_room = HYDRO_POS_LIM + pos
        orders: List[Order] = []

        for threshold, target in HYDRO_BUY_TIERS:
            if mid < threshold:
                qty = min(HYDRO_STEP_SIZE, target - pos, buy_room)
                if qty > 0:
                    orders.append(Order(product, int(best_ask), qty))
                break

        if not orders:
            for threshold, target in HYDRO_SELL_TIERS:
                if mid > threshold:
                    qty = min(HYDRO_STEP_SIZE, pos + target, sell_room)
                    if qty > 0:
                        orders.append(Order(product, int(best_bid), -qty))
                    break

        return orders
