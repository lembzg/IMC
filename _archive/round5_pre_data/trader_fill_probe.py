from datamodel import TradingState, Order
from typing import Dict, List, Tuple
import json


PRODUCT = "VELVETFRUIT_EXTRACT"
QTY = 1


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
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        result: Dict[str, List[Order]] = {}
        depth = state.order_depths.get(PRODUCT)

        fills = state.own_trades.get(PRODUCT, [])
        if fills:
            for fill in fills:
                logger.print(
                    "FILL",
                    "ts", state.timestamp,
                    "fill_ts", fill.timestamp,
                    "px", fill.price,
                    "qty", fill.quantity,
                    "buyer", fill.buyer,
                    "seller", fill.seller,
                    "pos", state.position.get(PRODUCT, 0),
                )

        if depth and depth.buy_orders and depth.sell_orders:
            best_bid = max(depth.buy_orders)
            best_ask = min(depth.sell_orders)
            spread = best_ask - best_bid

            # Alternate tests every 50 ticks. This keeps one level active long
            # enough to observe passive fills without mixing all four tests.
            phase = (state.timestamp // 5000) % 4

            orders: List[Order] = []
            if phase == 0:
                label = "BUY_AT_BEST_BID"
                price = best_bid
                orders.append(Order(PRODUCT, price, QTY))
            elif phase == 1:
                label = "BUY_AT_BEST_BID_PLUS_1"
                price = best_bid + 1
                if price < best_ask:
                    orders.append(Order(PRODUCT, price, QTY))
            elif phase == 2:
                label = "SELL_AT_BEST_ASK"
                price = best_ask
                orders.append(Order(PRODUCT, price, -QTY))
            else:
                label = "SELL_AT_BEST_ASK_MINUS_1"
                price = best_ask - 1
                if price > best_bid:
                    orders.append(Order(PRODUCT, price, -QTY))

            logger.print(
                "QUOTE",
                label,
                "ts", state.timestamp,
                "bid", best_bid,
                "ask", best_ask,
                "spread", spread,
                "orders", [(o.price, o.quantity) for o in orders],
                "pos", state.position.get(PRODUCT, 0),
            )

            if orders:
                result[PRODUCT] = orders

        trader_data = "{}"
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data

    def bid(self, state: TradingState) -> int:
        return 0
