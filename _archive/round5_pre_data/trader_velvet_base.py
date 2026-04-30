from datamodel import TradingState, Order
from typing import List, Dict, Tuple, Optional
import json
import math


PRODUCT = "VELVETFRUIT_EXTRACT"
POSITION_LIMIT = 200          # spot self-imposed hard cap
PASSIVE_CAP = 50              # passive penny jump's self-imposed inventory cap
QUOTE_SIZE = 15

OPTIONS = {
    "VEV_5000": 300,
    "VEV_5100": 300,
    "VEV_5200": 300,
    "VEV_5300": 300,
    "VEV_5400": 300,
    "VEV_5500": 300,
}
OPT_MARGIN = 5.0
OPT_QUOTE_LIMIT = 15
OPT_TAKE_LIMIT = 8
OPT_WARMUP_TS = 50_000
OPT_EMA_ALPHA = 0.02

SPOT_MARGIN = 5.0
SPOT_TAKE_LIMIT = 8
SPOT_WARMUP_TS = 50_000   # use EMA fair while ts < this; cumulative mean after
SPOT_EMA_ALPHA = 0.02     # warmup EMA alpha (half-life ~35 ticks)

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


SMILE_A = 0.0088
SMILE_B = -0.0007
SMILE_C = 0.3584


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


def spot_penny_jump(depth, pos: int) -> List[Order]:
    """Passive penny-jump quotes with PASSIVE_CAP self-cap on each side."""
    if not depth.buy_orders or not depth.sell_orders:
        return []
    best_bid = max(depth.buy_orders.keys())
    best_ask = min(depth.sell_orders.keys())

    quote_bid = best_bid + 1
    quote_ask = best_ask - 1
    if quote_bid >= quote_ask:
        return []

    buy_room = POSITION_LIMIT - pos
    sell_room = POSITION_LIMIT + pos
    passive_buy_room = max(0, PASSIVE_CAP - pos)
    passive_sell_room = max(0, PASSIVE_CAP + pos)
    bid_size = min(QUOTE_SIZE, passive_buy_room, buy_room)
    ask_size = min(QUOTE_SIZE, passive_sell_room, sell_room)

    orders: List[Order] = []
    if bid_size > 0:
        orders.append(Order(PRODUCT, quote_bid, bid_size))
    if ask_size > 0:
        orders.append(Order(PRODUCT, quote_ask, -ask_size))
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
            for symbol in OPTIONS:
                K = float(symbol.split("_")[1])
                pos = state.position.get(symbol, 0)
                sigma = smile_sigma(S, K, T)
                d = bsm_delta(S, K, T, sigma)
                net_delta += pos * d

        buy_scale, sell_scale = delta_scales(net_delta)

        # Options: EMA warmup → cumulative-mean active take
        opt_sum = saved.get("opt_sum", {})
        opt_count = saved.get("opt_count", {})
        opt_ema = saved.get("opt_ema", {})
        opt_fair_used: Dict[str, float] = {}
        for symbol, limit in OPTIONS.items():
            odepth = state.order_depths.get(symbol)
            if not odepth or not odepth.buy_orders or not odepth.sell_orders:
                continue
            best_bid = max(odepth.buy_orders)
            best_ask = min(odepth.sell_orders)
            mid = (best_bid + best_ask) / 2.0

            # Always update EMA (used during warmup and as handoff seed)
            if symbol not in opt_ema:
                opt_ema[symbol] = mid
            else:
                opt_ema[symbol] = OPT_EMA_ALPHA * mid + (1.0 - OPT_EMA_ALPHA) * opt_ema[symbol]

            if state.timestamp < OPT_WARMUP_TS:
                fair = opt_ema[symbol]
            else:
                if opt_count.get(symbol, 0) == 0:
                    opt_sum[symbol] = opt_ema[symbol] * 500.0
                    opt_count[symbol] = 500
                opt_sum[symbol] = opt_sum.get(symbol, 0.0) + mid
                opt_count[symbol] = opt_count.get(symbol, 0) + 1
                fair = opt_sum[symbol] / opt_count[symbol]

            opt_fair_used[symbol] = fair
            pos = state.position.get(symbol, 0)

            active = option_active_orders(symbol, odepth, fair, pos, limit, buy_scale, sell_scale)
            if active:
                result[symbol] = active
        saved["opt_sum"] = opt_sum
        saved["opt_count"] = opt_count
        saved["opt_ema"] = opt_ema

        # Spot: EMA warmup → cumulative-mean active take + passive penny jump
        spot_sum = saved.get("spot_sum", 0.0)
        spot_count = saved.get("spot_count", 0)
        spot_ema = saved.get("spot_ema", None)
        spot_fair = None
        if spot_depth and spot_depth.buy_orders and spot_depth.sell_orders:
            best_bid_s = max(spot_depth.buy_orders)
            best_ask_s = min(spot_depth.sell_orders)
            spot_mid = (best_bid_s + best_ask_s) / 2.0

            # Always update EMA (used during warmup and as handoff seed)
            if spot_ema is None:
                spot_ema = spot_mid
            else:
                spot_ema = SPOT_EMA_ALPHA * spot_mid + (1.0 - SPOT_EMA_ALPHA) * spot_ema

            if state.timestamp < SPOT_WARMUP_TS:
                spot_fair = spot_ema
            else:
                # First tick after warmup: seed cumulative mean from EMA
                if spot_count == 0:
                    spot_sum = spot_ema * 500.0
                    spot_count = 500
                spot_sum += spot_mid
                spot_count += 1
                spot_fair = spot_sum / spot_count

            spot_pos = state.position.get(PRODUCT, 0)
            spot_orders: List[Order] = []
            take_buy = 0
            take_sell = 0

            if best_ask_s < spot_fair - SPOT_MARGIN:
                ask_vol = -spot_depth.sell_orders[best_ask_s]
                take_buy = min(POSITION_LIMIT - spot_pos, ask_vol, SPOT_TAKE_LIMIT)
                if take_buy > 0:
                    spot_orders.append(Order(PRODUCT, best_ask_s, take_buy))
            if best_bid_s > spot_fair + SPOT_MARGIN:
                bid_vol = spot_depth.buy_orders[best_bid_s]
                take_sell = min(POSITION_LIMIT + spot_pos, bid_vol, SPOT_TAKE_LIMIT)
                if take_sell > 0:
                    spot_orders.append(Order(PRODUCT, best_bid_s, -take_sell))

            effective_pos = spot_pos + take_buy - take_sell
            spot_orders.extend(spot_penny_jump(spot_depth, effective_pos))
            if spot_orders:
                result[PRODUCT] = spot_orders
        saved["spot_sum"] = spot_sum
        saved["spot_count"] = spot_count
        saved["spot_ema"] = spot_ema

        spot_fair_log = round(spot_fair, 2) if spot_fair is not None else None
        spot_mode = "ema" if state.timestamp < SPOT_WARMUP_TS else "cum"
        opt_mode = "ema" if state.timestamp < OPT_WARMUP_TS else "cum"
        opt_fair_log = {sym: round(v, 2) for sym, v in opt_fair_used.items()}
        logger.print(f"fair spot={spot_fair_log}({spot_mode}) opts({opt_mode})={opt_fair_log}")

        trader_data = json.dumps(saved)
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data