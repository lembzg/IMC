import json
from collections import defaultdict
from datamodel import Order, Symbol, TradingState
from typing import Dict, List, Tuple, Optional


# ── Spot constants ─────────────────────────────────────────────────────────────
SPOT = "VELVETFRUIT_EXTRACT"
SPOT_LIMIT = 200
SPOT_ALPHA = 0.02
SPOT_ACTIVE_THR = 2.0
SPOT_QUOTE_LIMIT = 15

# ── Options constants (407468 unchanged) ───────────────────────────────────────
OPT_LIMITS = {
    "VEV_4000": 300, "VEV_4500": 300, "VEV_5000": 300,
    "VEV_5100": 300, "VEV_5200": 300, "VEV_5300": 300,
    "VEV_5400": 300, "VEV_5500": 300,
}
ALPHA_FAST    = 0.97
ALPHA_SLOW    = 0.0001  # near-constant anchor — freezes reference at initial price level
EXT_ALPHA     = 0.01
EXT_THR       = 10
MARGIN        = 0.01
STOP_LOSS     = -10000
OPT_TRADE_QTY = 1       # 1 lot per signal — maximises signal frequency

# ── HYDROGEL_PACK range strategy parameters ──────────────────────────────────
HYDRO_POS_LIM    = 200
HYDRO_STEP_SIZE  = 20
HYDRO_MAX_SPREAD = 20   # don't trade if book spread is wider than this (typical ~16)

# Buy tiers: (mid_below_threshold, target_long_position)
# Evaluated top-to-bottom; first match wins.
HYDRO_BUY_TIERS = [
    (9925, 70),
    (9930, 60),
    (9935, 50),
    (9940, 40),
]

# Sell tiers: (mid_above_threshold, target_short_position)
# Evaluated top-to-bottom; first match wins.
# Grid search optimum: sell_ref=10025 (+5 vs original 10020)
HYDRO_SELL_TIERS = [
    (10040, 70),
    (10035, 60),
    (10030, 50),
    (10025, 40),
]

# Neutral zone flatten: disabled by default.
# The strategy intentionally holds position while waiting for price to
# reach the opposite tier — flattening early cuts winning trades short.
HYDRO_NEUTRAL_FLATTEN = False
HYDRO_FLATTEN_TRIGGER = 30


class Logger:
    def __init__(self):
        self.logs = ""

    def print(self, *objects, sep=" ", end="\n"):
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict, conversions: int, trader_data: str):
        print(json.dumps([
            [
                state.timestamp,
                state.traderData,
                [[l.symbol, l.product, l.denomination] for l in state.listings.values()],
                {s: [od.buy_orders, od.sell_orders] for s, od in state.order_depths.items()},
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp] for trades in state.own_trades.values() for t in trades],
                [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp] for trades in state.market_trades.values() for t in trades],
                dict(state.position),
                [state.observations.plainValueObservations, {
                    p: [o.bidPrice, o.askPrice, o.transportFees, o.exportTariff, o.importTariff, o.sugarPrice, o.sunlightIndex]
                    for p, o in state.observations.conversionObservations.items()
                }],
            ],
            [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr],
            conversions,
            trader_data,
            self.logs,
        ], separators=(",", ":")))
        self.logs = ""


logger = Logger()


def update_ema(prev: Optional[float], price: float, alpha: float) -> float:
    return price if prev is None else alpha * price + (1 - alpha) * prev


def spot_orders(depth, ema: float, pos: int) -> List[Order]:
    orders = []
    best_ask = min(depth.sell_orders)
    best_bid = max(depth.buy_orders)

    # Active take
    if best_ask < ema - SPOT_ACTIVE_THR:
        qty = min(SPOT_QUOTE_LIMIT, SPOT_LIMIT - pos)
        if qty > 0:
            orders.append(Order(SPOT, best_ask, qty))
    if best_bid > ema + SPOT_ACTIVE_THR:
        qty = min(SPOT_QUOTE_LIMIT, SPOT_LIMIT + pos)
        if qty > 0:
            orders.append(Order(SPOT, best_bid, -qty))

    # Passive quote
    quote_bid = best_bid + 1
    quote_ask = best_ask - 1
    if quote_bid < ema:
        qty = min(SPOT_QUOTE_LIMIT, SPOT_LIMIT - pos)
        if qty > 0:
            orders.append(Order(SPOT, quote_bid, qty))
    if quote_ask > ema:
        qty = min(SPOT_QUOTE_LIMIT, SPOT_LIMIT + pos)
        if qty > 0:
            orders.append(Order(SPOT, quote_ask, -qty))

    return orders


class Trader:
    def bid(self):
        return 1

    def run(self, state: TradingState) -> Tuple[Dict[Symbol, List[Order]], int, str]:
        saved = {}
        if state.traderData:
            try:
                saved = json.loads(state.traderData)
            except Exception:
                pass

        result: Dict[Symbol, List[Order]] = {}

        # ── Spot: passive MM ──────────────────────────────────────────────────
        spot_depth = state.order_depths.get(SPOT)
        if spot_depth and spot_depth.buy_orders and spot_depth.sell_orders:
            mid = (max(spot_depth.buy_orders) + min(spot_depth.sell_orders)) / 2.0
            spot_ema = update_ema(saved.get("se"), mid, SPOT_ALPHA)
            saved["se"] = spot_ema
            pos = state.position.get(SPOT, 0)
            orders = spot_orders(spot_depth, spot_ema, pos)
            if orders:
                result[SPOT] = orders

        # ── Options: 407468 logic unchanged ──────────────────────────────────
        ema_fast = saved.get("f", {})
        ema_slow = saved.get("s", {})
        ext_ema: Dict[str, float] = saved.get("e", {})

        spot_mid = None
        if spot_depth and spot_depth.buy_orders and spot_depth.sell_orders:
            spot_mid = (max(spot_depth.buy_orders) + min(spot_depth.sell_orders)) / 2.0

        for product, limit in OPT_LIMITS.items():
            depth = state.order_depths.get(product)
            if not depth or not depth.buy_orders or not depth.sell_orders:
                continue

            best_ask = min(depth.sell_orders)
            best_bid = max(depth.buy_orders)
            mid_price = (best_ask + best_bid) / 2.0

            if product not in ema_fast:
                ema_fast[product] = mid_price
                ema_slow[product] = mid_price
            else:
                ema_fast[product] = ALPHA_FAST * mid_price + (1 - ALPHA_FAST) * ema_fast[product]
                ema_slow[product] = ALPHA_SLOW * mid_price + (1 - ALPHA_SLOW) * ema_slow[product]

            expected_price = ema_slow[product]
            momentum = mid_price - ema_fast[product]

            extrinsic = mid_price
            ev_mavg = 0
            if spot_mid is not None:
                strike = int(product.split("_")[1])
                intrinsic = max(0, spot_mid - strike)
                extrinsic = mid_price - intrinsic
                prev = ext_ema.get(product)
                ext_ema[product] = extrinsic if prev is None else EXT_ALPHA * extrinsic + (1 - EXT_ALPHA) * prev
                ev_mavg = ext_ema[product]

            current_pos = state.position.get(product, 0)
            to_buy = limit - current_pos
            to_sell = limit + current_pos

            orders: List[Order] = []

            # Stop-loss
            own_trades = state.own_trades.get(product, [])
            if own_trades:
                mid_pnl = (best_bid + best_ask) / 2
                realized = sum((t.price - mid_pnl) * t.quantity for t in own_trades)
                if realized < STOP_LOSS:
                    if current_pos > 0:
                        orders.append(Order(product, best_bid, -current_pos))
                    elif current_pos < 0:
                        orders.append(Order(product, best_ask, -current_pos))
                    if orders:
                        result[product] = orders
                    continue

            take_buy = (best_ask < expected_price - MARGIN or momentum < -8) and to_buy > 0
            take_sell = (best_bid > expected_price + MARGIN or momentum > 8) and to_sell > 0

            if ev_mavg > 0:
                if extrinsic > ev_mavg + EXT_THR:
                    take_sell = True
                elif extrinsic < ev_mavg - EXT_THR:
                    take_buy = True

            if take_buy and to_buy > 0:
                vol = depth.sell_orders[best_ask]
                qty = min(to_buy, -vol, OPT_TRADE_QTY)
                if qty > 0:
                    orders.append(Order(product, best_ask, qty))

            if take_sell and to_sell > 0:
                vol = depth.buy_orders[best_bid]
                qty = min(to_sell, vol, OPT_TRADE_QTY)
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))

            if orders:
                result[product] = orders

        saved["f"] = {k: round(v, 2) for k, v in ema_fast.items()}
        saved["s"] = {k: round(v, 2) for k, v in ema_slow.items()}
        saved["e"] = {k: round(v, 2) for k, v in ext_ema.items()}
        if "se" in saved:
            saved["se"] = round(saved["se"], 2)

        # ── HYDROGEL_PACK: range strategy ─────────────────────────────────────
        hydro_orders = self.hydro_range_strategy(state, saved)
        if hydro_orders:
            result["HYDROGEL_PACK"] = hydro_orders

        trader_data = json.dumps(saved)
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data

    def hydro_range_strategy(self, state: TradingState, shared: dict) -> list:
        product = "HYDROGEL_PACK"

        od = state.order_depths.get(product)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        spread   = best_ask - best_bid

        if spread > HYDRO_MAX_SPREAD or spread <= 0:
            return []

        mid = (best_bid + best_ask) / 2
        pos = state.position.get(product, 0)

        # ── Emergency unwind ──────────────────────────────────────────────────
        # Triggered only if price moves far outside the expected range.
        # Thresholds (9820 / 10100) are well outside normal operating range
        # so this should never fire under normal conditions.
        if mid < 9820 and pos > 0:
            logger.print(f"EMERGENCY UNWIND LONG: mid={mid} pos={pos}")
            return [Order("HYDROGEL_PACK", int(best_bid), -pos)]
        if mid > 10100 and pos < 0:
            logger.print(f"EMERGENCY UNWIND SHORT: mid={mid} pos={pos}")
            return [Order("HYDROGEL_PACK", int(best_ask), -pos)]

        buy_room  = HYDRO_POS_LIM - pos
        sell_room = HYDRO_POS_LIM + pos

        orders = []

        # ── Buy tiers ─────────────────────────────────────────────────────────
        for threshold, target in HYDRO_BUY_TIERS:
            if mid < threshold:
                qty = min(HYDRO_STEP_SIZE, target - pos, buy_room)
                if qty > 0:
                    orders.append(Order(product, int(best_ask), qty))
                break

        # ── Sell tiers ────────────────────────────────────────────────────────
        if not orders:
            for threshold, target in HYDRO_SELL_TIERS:
                if mid > threshold:
                    qty = min(HYDRO_STEP_SIZE, pos + target, sell_room)
                    if qty > 0:
                        orders.append(Order(product, int(best_bid), -qty))
                    break

        # ── Neutral zone flatten ──────────────────────────────────────────────
        if not orders and HYDRO_NEUTRAL_FLATTEN:
            if pos > HYDRO_FLATTEN_TRIGGER:
                qty = min(HYDRO_STEP_SIZE, pos, sell_room)
                if qty > 0:
                    orders.append(Order(product, int(best_bid), -qty))
            elif pos < -HYDRO_FLATTEN_TRIGGER:
                qty = min(HYDRO_STEP_SIZE, -pos, buy_room)
                if qty > 0:
                    orders.append(Order(product, int(best_ask), qty))

        return orders
