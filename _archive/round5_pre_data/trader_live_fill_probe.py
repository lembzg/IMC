from datamodel import TradingState, Order
from typing import Dict, List, Tuple
import json


PRODUCT = "VELVETFRUIT_EXTRACT"
POSITION_LIMIT = 200
PROBE_CAP = 5
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
        saved = json.loads(state.traderData) if state.traderData else {}
        fill_count = int(saved.get("fill_count", 0))

        fills = state.own_trades.get(PRODUCT, [])
        if fills:
            fill_count += len(fills)
            for fill in fills:
                logger.print(
                    "BEST_BID_ASK_FILL_PROBE_FILL",
                    "count", fill_count,
                    "ts", state.timestamp,
                    "fill_ts", fill.timestamp,
                    "px", fill.price,
                    "qty", fill.quantity,
                    "buyer", fill.buyer,
                    "seller", fill.seller,
                    "pos", state.position.get(PRODUCT, 0),
                )

        result: Dict[str, List[Order]] = {}
        depth = state.order_depths.get(PRODUCT)
        pos = state.position.get(PRODUCT, 0)

        if depth and depth.buy_orders and depth.sell_orders:
            best_bid = max(depth.buy_orders)
            best_ask = min(depth.sell_orders)
            bid = best_bid
            ask = best_ask

            orders: List[Order] = []
            if pos < PROBE_CAP and pos < POSITION_LIMIT:
                orders.append(Order(PRODUCT, bid, QTY))
            if pos > -PROBE_CAP and pos > -POSITION_LIMIT:
                orders.append(Order(PRODUCT, ask, -QTY))

            logger.print(
                "BEST_BID_ASK_FILL_PROBE_QUOTE",
                "ts", state.timestamp,
                "best_bid", best_bid,
                "best_ask", best_ask,
                "posting_bid", bid,
                "posting_ask", ask,
                "orders", [(o.price, o.quantity) for o in orders],
                "pos", pos,
                "fill_count", fill_count,
            )

            if orders:
                result[PRODUCT] = orders

        saved["fill_count"] = fill_count
        trader_data = json.dumps(saved)
        logger.flush(state, result, 0, trader_data)
        return result, 0, trader_data

    def bid(self, state: TradingState) -> int:
        return 0
