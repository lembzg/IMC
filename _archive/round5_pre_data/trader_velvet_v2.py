import json
from datamodel import Order, Symbol, TradingState
from typing import Dict, List, Optional, Tuple


OPT_LIMITS: Dict[str, int] = {
    "VEV_4000": 300,
    "VEV_4500": 300,
    "VEV_5000": 300,
    "VEV_5100": 300,
    "VEV_5200": 300,
    "VEV_5300": 300,
    "VEV_5400": 300,
    "VEV_5500": 300,
}

ALPHA_FAST = 0.97
ALPHA_SLOW = 0.0
EXT_ALPHA = 0.01
EXT_THR = 10.0
STOP_LOSS = -10000

MIN_DEV_FRAC = 0.9
QTY_DIV_SCALE = 0.4
MAX_QTY = 8
BASE_SOFT_LIMIT = 20
SOFT_LIMIT_TICK_DIVISOR = 10


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
            conversions,
            trader_data,
            self.logs,
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

        spot_depth = state.order_depths.get("VELVETFRUIT_EXTRACT")
        spot_mid: Optional[float] = None
        if spot_depth and spot_depth.buy_orders and spot_depth.sell_orders:
            spot_mid = (max(spot_depth.buy_orders) + min(spot_depth.sell_orders)) / 2.0

        ema_fast: Dict[str, float] = saved.get("f", {})
        ema_slow: Dict[str, float] = saved.get("s", {})
        ext_ema: Dict[str, float] = saved.get("e", {})

        for product, limit in OPT_LIMITS.items():
            depth = state.order_depths.get(product)
            if not depth or not depth.buy_orders or not depth.sell_orders:
                continue

            best_ask = min(depth.sell_orders)
            best_bid = max(depth.buy_orders)
            spread = best_ask - best_bid
            if spread <= 0:
                continue

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
            ev_mavg = 0.0
            if spot_mid is not None:
                strike = int(product.split("_")[1])
                intrinsic = max(0.0, spot_mid - strike)
                extrinsic = mid_price - intrinsic
                prev = ext_ema.get(product)
                ext_ema[product] = extrinsic if prev is None else EXT_ALPHA * extrinsic + (1 - EXT_ALPHA) * prev
                ev_mavg = ext_ema[product]

            current_pos = state.position.get(product, 0)
            observed_ticks = max(1, state.timestamp // 100 + 1)
            soft_limit = min(limit, BASE_SOFT_LIMIT + observed_ticks // SOFT_LIMIT_TICK_DIVISOR)
            to_buy = soft_limit - current_pos
            to_sell = soft_limit + current_pos

            orders: List[Order] = []

            own_trades = state.own_trades.get(product, [])
            if own_trades:
                mid_pnl = (best_bid + best_ask) / 2.0
                realized = sum((t.price - mid_pnl) * t.quantity for t in own_trades)
                if realized < STOP_LOSS:
                    if current_pos > 0:
                        orders.append(Order(product, best_bid, -current_pos))
                    elif current_pos < 0:
                        orders.append(Order(product, best_ask, -current_pos))
                    if orders:
                        result[product] = orders
                    continue

            min_dev = spread * MIN_DEV_FRAC
            buy_dev = expected_price - best_ask
            sell_dev = best_bid - expected_price

            take_buy = (buy_dev >= min_dev or momentum < -8) and to_buy > 0
            take_sell = (sell_dev >= min_dev or momentum > 8) and to_sell > 0

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

        trader_data = json.dumps(saved)
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data
