import json
from datamodel import Order, TradingState
from typing import List

HYDRO_POS_LIM    = 200
HYDRO_STEP_SIZE  = 20
HYDRO_MAX_SPREAD = 20
HYDRO_FAIR_INIT  = 10000.0

# Buy tiers: (mid_below_threshold, target_long_position)
HYDRO_BUY_TIERS = [
    (9925, 100),
    (9930, 85),
    (9935, 70),
    (9940, 55),
]

# Sell tiers: (mid_above_threshold, target_short_position)
HYDRO_SELL_TIERS = [
    (10040, 100),
    (10035, 85),
    (10030, 70),
    (10025, 55),
]

# Maker (passive quote) parameters — only active when position is near flat
HYDRO_MAKER_SIZE     = 12   # units per side per tick
HYDRO_MAKER_MAX_POS  = 15   # maker shuts off entirely if |pos| > this


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


class Trader:
    def bid(self):
        return 1

    def run(self, state: TradingState):
        saved = {}
        if state.traderData:
            try:
                saved = json.loads(state.traderData)
            except Exception:
                pass

        result = {}
        hydro_orders = self.hydro_range_strategy(state, saved)
        if hydro_orders:
            result["HYDROGEL_PACK"] = hydro_orders

        trader_data = json.dumps(saved)
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data

    def hydro_range_strategy(self, state: TradingState, saved: dict) -> list:
        product = "HYDROGEL_PACK"
        od = state.order_depths.get(product)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        spread = best_ask - best_bid

        if spread > HYDRO_MAX_SPREAD or spread <= 0:
            return []

        bid_vol = od.buy_orders[best_bid]
        ask_vol = abs(od.sell_orders[best_ask])
        total_vol = bid_vol + ask_vol
        microprice = (best_bid * ask_vol + best_ask * bid_vol) / total_vol if total_vol > 0 else (best_bid + best_ask) / 2.0

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

        # Maker: passive quotes only when position is near flat.
        # Shuts off entirely once taker has built a position — avoids
        # prematurely covering taker positions during directional moves.
        if not orders and spread >= 4 and abs(pos) <= HYDRO_MAKER_MAX_POS:
            quote_bid = best_bid + 1
            quote_ask = best_ask - 1
            if quote_bid < quote_ask:
                if buy_room > 0:
                    orders.append(Order(product, quote_bid, min(HYDRO_MAKER_SIZE, buy_room)))
                if sell_room > 0:
                    orders.append(Order(product, quote_ask, -min(HYDRO_MAKER_SIZE, sell_room)))

        return orders