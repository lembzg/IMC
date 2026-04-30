from collections import defaultdict
import json

from datamodel import Order, TradingState


POS_LIMIT = 200
LOOKBACK = 100
ENTRY_Z = 0.5
QUOTE_QTY = 6
IMPROVE = 0


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

        result["HYDROGEL_PACK"] = self.hydro(state, data)
        trader_data = json.dumps(data, separators=(",", ":"))
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data

    def hydro(self, state: TradingState, data: dict) -> list[Order]:
        product = "HYDROGEL_PACK"
        od = state.order_depths.get(product)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        bid_price = best_bid + IMPROVE
        ask_price = best_ask - IMPROVE
        if bid_price >= ask_price:
            return []

        mid = (best_bid + best_ask) / 2.0
        pos = state.position.get(product, 0)
        hist = data.get("h", [])
        z = self.z_score(mid, hist)

        buy_room = POS_LIMIT - pos
        sell_room = POS_LIMIT + pos
        orders = []

        if z <= -ENTRY_Z and buy_room > 0:
            orders.append(Order(product, bid_price, min(QUOTE_QTY, buy_room)))
        elif z >= ENTRY_Z and sell_room > 0:
            orders.append(Order(product, ask_price, -min(QUOTE_QTY, sell_room)))
        elif pos > 0 and sell_room > 0:
            orders.append(Order(product, ask_price, -min(QUOTE_QTY, pos, sell_room)))
        elif pos < 0 and buy_room > 0:
            orders.append(Order(product, bid_price, min(QUOTE_QTY, -pos, buy_room)))

        hist.append(mid)
        data["h"] = hist[-LOOKBACK:]
        return orders

    def z_score(self, mid: float, hist: list[float]) -> float:
        if len(hist) < 20:
            return 0.0
        window = hist[-LOOKBACK:]
        mean = sum(window) / len(window)
        variance = sum((x - mean) * (x - mean) for x in window) / len(window)
        if variance <= 0:
            return 0.0
        return (mid - mean) / (variance ** 0.5)
