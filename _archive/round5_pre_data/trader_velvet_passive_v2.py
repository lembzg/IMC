from datamodel import TradingState, Order
from typing import List, Dict, Tuple
import json


PRODUCT = "VELVETFRUIT_EXTRACT"

POSITION_LIMIT = 200
QUOTE_LIMIT = 15

EMA_ALPHA = 0.02
ACTIVE_THR = 2.0

BIAS_THR = 3.0
INVENTORY_SOFT_LIMIT = 100


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


def update_ema(prev, price: float, alpha: float) -> float:
    if prev is None:
        return price
    return alpha * price + (1 - alpha) * prev


def active_orders(depth, fair: float, pos: int) -> List[Order]:
    orders = []

    best_ask = min(depth.sell_orders)
    best_bid = max(depth.buy_orders)

    buy_room = POSITION_LIMIT - pos
    sell_room = POSITION_LIMIT + pos

    # Take cheap asks
    if best_ask < fair - ACTIVE_THR:
        qty = min(QUOTE_LIMIT, buy_room, -depth.sell_orders[best_ask])
        if qty > 0:
            orders.append(Order(PRODUCT, best_ask, qty))

    # Hit expensive bids
    if best_bid > fair + ACTIVE_THR:
        qty = min(QUOTE_LIMIT, sell_room, depth.buy_orders[best_bid])
        if qty > 0:
            orders.append(Order(PRODUCT, best_bid, -qty))

    return orders


def biased_passive_orders(depth, fair: float, pos: int, mid: float) -> List[Order]:
    orders = []

    best_bid = max(depth.buy_orders)
    best_ask = min(depth.sell_orders)

    quote_bid = best_bid + 1
    quote_ask = best_ask - 1

    buy_room = POSITION_LIMIT - pos
    sell_room = POSITION_LIMIT + pos

    # Price cheap vs EMA -> lean BUY only
    if mid < fair - BIAS_THR:
        if pos < INVENTORY_SOFT_LIMIT and quote_bid < fair:
            qty = min(QUOTE_LIMIT, buy_room)
            if qty > 0:
                orders.append(Order(PRODUCT, quote_bid, qty))

    # Price expensive vs EMA -> lean SELL only
    elif mid > fair + BIAS_THR:
        if pos > -INVENTORY_SOFT_LIMIT and quote_ask > fair:
            qty = min(QUOTE_LIMIT, sell_room)
            if qty > 0:
                orders.append(Order(PRODUCT, quote_ask, -qty))

    # Neutral zone -> small both sides, inventory-aware
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


class Trader:
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        saved = {}

        if state.traderData:
            try:
                saved = json.loads(state.traderData)
            except Exception:
                saved = {}

        result: Dict[str, List[Order]] = {}
        conversions = 0

        depth = state.order_depths.get(PRODUCT)

        if depth and depth.buy_orders and depth.sell_orders:
            best_bid = max(depth.buy_orders)
            best_ask = min(depth.sell_orders)
            mid = (best_bid + best_ask) / 2

            ema = update_ema(saved.get("ema"), mid, EMA_ALPHA)
            saved["ema"] = ema

            fair = ema
            pos = state.position.get(PRODUCT, 0)

            #orders = active_orders(depth, fair, pos)
            orders = biased_passive_orders(depth, fair, pos, mid)

            if orders:
                result[PRODUCT] = orders

        trader_data = json.dumps(saved)

        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data