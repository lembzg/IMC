from datamodel import TradingState, Order
from typing import List, Dict, Tuple, Optional
import json
import math


PRODUCT = "VELVETFRUIT_EXTRACT"
POSITION_LIMIT = 200
QUOTE_LIMIT = 15
EMA_ALPHA = 0.02
ACTIVE_THR = 2.0
BIAS_THR = 3.0
INVENTORY_SOFT_LIMIT = 100

OPTIONS = {
    "VEV_5000": 300,
    "VEV_5100": 300,
    "VEV_5200": 300,
    "VEV_5300": 300,
    "VEV_5400": 300,
    "VEV_5500": 300,
}
OPT_ALPHA = 0.001
OPT_MARGIN = 3.0
OPT_QUOTE_LIMIT = 15
OPT_TAKE_LIMIT = 10

DELTA_SOFT = 800.0
DELTA_HARD = 1200.0


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


SMILE_A = 0.1336
SMILE_B = 0.0192
SMILE_C = 0.2259


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bsm_delta(S: float, K: float, T: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0 or S <= 0:
        return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    return norm_cdf(d1)


def smile_sigma(S: float, K: float, T: float) -> float:
    if T <= 0 or S <= 0:
        return SMILE_C
    m = math.log(K / S) / math.sqrt(T)
    return max(0.01, SMILE_A * m * m + SMILE_B * m + SMILE_C)


def update_ema(prev: Optional[float], price: float, alpha: float) -> float:
    return price if prev is None else alpha * price + (1 - alpha) * prev


def delta_scales(net_delta: float) -> Tuple[float, float]:
    if net_delta <= DELTA_SOFT:
        buy_scale = 1.0
    elif net_delta <= DELTA_HARD:
        buy_scale = 0.5
    else:
        buy_scale = 0.0
    if net_delta >= -DELTA_SOFT:
        sell_scale = 1.0
    elif net_delta >= -DELTA_HARD:
        sell_scale = 0.5
    else:
        sell_scale = 0.0
    return buy_scale, sell_scale


def active_orders(depth, fair: float, pos: int) -> List[Order]:
    orders = []
    best_ask = min(depth.sell_orders)
    best_bid = max(depth.buy_orders)
    if best_ask < fair - ACTIVE_THR:
        qty = min(QUOTE_LIMIT, POSITION_LIMIT - pos)
        if qty > 0:
            orders.append(Order(PRODUCT, best_ask, qty))
    if best_bid > fair + ACTIVE_THR:
        qty = min(QUOTE_LIMIT, POSITION_LIMIT + pos)
        if qty > 0:
            orders.append(Order(PRODUCT, best_bid, -qty))
    return orders


def passive_orders(depth, fair: float, pos: int, mid: float) -> List[Order]:
    orders = []
    quote_bid = max(depth.buy_orders) + 1
    quote_ask = min(depth.sell_orders) - 1
    buy_room = POSITION_LIMIT - pos
    sell_room = POSITION_LIMIT + pos

    if mid < fair - BIAS_THR:
        if pos < INVENTORY_SOFT_LIMIT and quote_bid < fair:
            qty = min(QUOTE_LIMIT, buy_room)
            if qty > 0:
                orders.append(Order(PRODUCT, quote_bid, qty))
    elif mid > fair + BIAS_THR:
        if pos > -INVENTORY_SOFT_LIMIT and quote_ask > fair:
            qty = min(QUOTE_LIMIT, sell_room)
            if qty > 0:
                orders.append(Order(PRODUCT, quote_ask, -qty))
    else:
        if pos < INVENTORY_SOFT_LIMIT and quote_bid < fair:
            qty = min(QUOTE_LIMIT // 2, buy_room)
            if qty > 0:
                orders.append(Order(PRODUCT, quote_bid, qty))
        if pos > -INVENTORY_SOFT_LIMIT and quote_ask > fair:
            qty = min(QUOTE_LIMIT // 2, sell_room)
            if qty > 0:
                orders.append(Order(PRODUCT, quote_ask, -qty))
    return orders


def option_passive_orders(symbol: str, depth, fair: float, pos: int, limit: int,
                          buy_scale: float, sell_scale: float) -> List[Order]:
    orders = []
    quote_bid = max(depth.buy_orders) + 1
    quote_ask = min(depth.sell_orders) - 1
    if quote_bid < fair:
        qty = min(int(OPT_QUOTE_LIMIT * buy_scale), limit - pos)
        if qty > 0:
            orders.append(Order(symbol, quote_bid, qty))
    if quote_ask > fair:
        qty = min(int(OPT_QUOTE_LIMIT * sell_scale), limit + pos)
        if qty > 0:
            orders.append(Order(symbol, quote_ask, -qty))
    return orders


def option_active_orders(symbol: str, depth, fair: float, pos: int, limit: int,
                         buy_scale: float, sell_scale: float) -> List[Order]:
    orders = []
    best_ask = min(depth.sell_orders)
    best_bid = max(depth.buy_orders)
    if best_ask < fair - OPT_MARGIN:
        ask_vol = -depth.sell_orders[best_ask]
        qty = min(limit - pos, ask_vol, int(OPT_TAKE_LIMIT * buy_scale))
        if qty > 0:
            orders.append(Order(symbol, best_ask, qty))
    if best_bid > fair + OPT_MARGIN:
        bid_vol = depth.buy_orders[best_bid]
        qty = min(limit + pos, bid_vol, int(OPT_TAKE_LIMIT * sell_scale))
        if qty > 0:
            orders.append(Order(symbol, best_bid, -qty))
    return orders


class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        saved = json.loads(state.traderData) if state.traderData else {}
        result: Dict[str, List[Order]] = {}

        # Net delta first (drives option size skew)
        spot_depth = state.order_depths.get(PRODUCT)
        net_delta = 0.0
        if spot_depth and spot_depth.buy_orders and spot_depth.sell_orders:
            S = (max(spot_depth.buy_orders) + min(spot_depth.sell_orders)) / 2.0
            day = state.timestamp // 1_000_000
            T = max(0.0, (5 - day) / 365.0)
            spot_pos = state.position.get(PRODUCT, 0)
            net_delta = float(spot_pos)
            per_strike = []
            for symbol in OPTIONS:
                K = float(symbol.split("_")[1])
                pos = state.position.get(symbol, 0)
                sigma = smile_sigma(S, K, T)
                d = bsm_delta(S, K, T, sigma)
                net_delta += pos * d
                per_strike.append(f"{symbol}:{pos}:{d:.4f}")
            logger.print(f"DELTA,{state.timestamp},{S:.2f},{spot_pos},{net_delta:.2f}," + ",".join(per_strike))

        buy_scale, sell_scale = delta_scales(net_delta)
        if buy_scale < 1.0 or sell_scale < 1.0:
            logger.print(f"SKEW,{state.timestamp},{net_delta:.1f},{buy_scale},{sell_scale}")

        # Options loop with delta-driven size scaling
        opt_ema = saved.get("opt_ema", {})
        for symbol, limit in OPTIONS.items():
            odepth = state.order_depths.get(symbol)
            if not odepth or not odepth.buy_orders or not odepth.sell_orders:
                continue
            best_bid = max(odepth.buy_orders)
            best_ask = min(odepth.sell_orders)
            mid = (best_bid + best_ask) / 2.0
            fair = update_ema(opt_ema.get(symbol), mid, OPT_ALPHA)
            opt_ema[symbol] = fair
            pos = state.position.get(symbol, 0)

            active = option_active_orders(symbol, odepth, fair, pos, limit, buy_scale, sell_scale)
            passive = option_passive_orders(symbol, odepth, fair, pos, limit, buy_scale, sell_scale)

            orders = active + passive
            if orders:
                result[symbol] = orders
        saved["opt_ema"] = opt_ema

        # Spot: friend's biased passive MM
        depth = state.order_depths.get(PRODUCT)
        if depth and depth.buy_orders and depth.sell_orders:
            mid = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
            ema = update_ema(saved.get("ema"), mid, EMA_ALPHA)
            pos = state.position.get(PRODUCT, 0)
            spot_orders = active_orders(depth, ema, pos)
            spot_orders += passive_orders(depth, ema, pos, mid)
            result[PRODUCT] = spot_orders
            saved["ema"] = ema

        trader_data = json.dumps(saved)
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data