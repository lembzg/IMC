from collections import defaultdict
import json

from datamodel import Order, TradingState


PRODUCT = "HYDROGEL_PACK"
POSITION_LIMIT = 200

# Risk/signal parameters only. No absolute HYDROGEL price levels or bot names.
LOOKBACK = 100
MIN_HISTORY = 20
ENTRY_Z = 0.5
QUOTE_SIZE = 6
MAX_SPREAD = 20


class Logger:
    def __init__(self):
        self.logs = ""

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
                [
                    state.observations.plainValueObservations,
                    {
                        p: [
                            o.bidPrice,
                            o.askPrice,
                            o.transportFees,
                            o.exportTariff,
                            o.importTariff,
                            o.sugarPrice,
                            o.sunlightIndex,
                        ]
                        for p, o in state.observations.conversionObservations.items()
                    },
                ],
            ],
            [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr],
            conversions,
            trader_data,
            self.logs,
        ], separators=(",", ":")))
        self.logs = ""


logger = Logger()


class Trader:
    def bid(self, state=None):
        return 1

    def run(self, state: TradingState):
        result = defaultdict(list)
        data = {}
        if state.traderData:
            try:
                data = json.loads(state.traderData)
            except json.JSONDecodeError:
                data = {}

        result[PRODUCT] = self.trade_hydro(state, data)
        trader_data = json.dumps(data, separators=(",", ":"))
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data

    def trade_hydro(self, state: TradingState, data: dict) -> list[Order]:
        order_depth = state.order_depths.get(PRODUCT)
        if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
            return []

        best_bid = max(order_depth.buy_orders)
        best_ask = min(order_depth.sell_orders)
        spread = best_ask - best_bid
        if spread <= 0 or spread > MAX_SPREAD:
            return []

        mid = (best_bid + best_ask) / 2.0
        hist = data.get("h", [])
        z = self.rolling_z(mid, hist)

        pos = state.position.get(PRODUCT, 0)
        buy_room = POSITION_LIMIT - pos
        sell_room = POSITION_LIMIT + pos
        orders = []

        # Passive mean reversion: join the touch instead of paying spread.
        if z <= -ENTRY_Z and buy_room > 0:
            orders.append(Order(PRODUCT, best_bid, min(QUOTE_SIZE, buy_room)))
        elif z >= ENTRY_Z and sell_room > 0:
            orders.append(Order(PRODUCT, best_ask, -min(QUOTE_SIZE, sell_room)))
        elif pos > 0 and sell_room > 0:
            orders.append(Order(PRODUCT, best_ask, -min(QUOTE_SIZE, pos, sell_room)))
        elif pos < 0 and buy_room > 0:
            orders.append(Order(PRODUCT, best_bid, min(QUOTE_SIZE, -pos, buy_room)))

        hist.append(mid)
        data["h"] = hist[-LOOKBACK:]
        return orders

    def rolling_z(self, mid: float, hist: list[float]) -> float:
        if len(hist) < MIN_HISTORY:
            return 0.0
        window = hist[-LOOKBACK:]
        mean = sum(window) / len(window)
        variance = sum((x - mean) * (x - mean) for x in window) / len(window)
        if variance <= 0:
            return 0.0
        return (mid - mean) / (variance ** 0.5)
