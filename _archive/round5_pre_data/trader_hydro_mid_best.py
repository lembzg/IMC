import json
from collections import defaultdict
from typing import Any

from datamodel import Order, ProsperityEncoder, Symbol, TradingState


PRODUCT = "HYDROGEL_PACK"
POS_LIM = 200

ROLLING_WINDOW = 800
MID_ENTRY_Z = 0.6
MID_MAIN_QTY = 4
MID_SMALL_QTY = 0
MID_IMPROVE = 1


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
        print(
            json.dumps(
                [
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
                ],
                cls=ProsperityEncoder,
                separators=(",", ":"),
            )
        )
        self.logs = ""


logger = Logger()


class Trader:
    def bid(self, state: TradingState | None = None) -> int:
        return 0

    def run(self, state: TradingState):
        result = defaultdict(list)
        conversions = 0

        try:
            data: dict[str, Any] = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            data = {}

        mids = data.get("mids", [])
        od = state.order_depths.get(PRODUCT)

        if od and od.buy_orders and od.sell_orders:
            bids = sorted(od.buy_orders.items(), reverse=True)
            asks = sorted(od.sell_orders.items())
            best_bid = bids[0][0]
            best_ask = asks[0][0]
            mid = (best_bid + best_ask) / 2
            pos = state.position.get(PRODUCT, 0)

            if len(mids) >= ROLLING_WINDOW:
                window = mids[-ROLLING_WINDOW:]
                mean = sum(window) / ROLLING_WINDOW
                var = sum((x - mean) ** 2 for x in window) / ROLLING_WINDOW
                std = var ** 0.5
                z = 0.0 if std == 0 else (mid - mean) / std

                buy_price = best_bid + MID_IMPROVE
                sell_price = best_ask - MID_IMPROVE
                buy_room = POS_LIM - pos
                sell_room = POS_LIM + pos

                if buy_price < sell_price:
                    if z <= -MID_ENTRY_Z and buy_room > 0:
                        result[PRODUCT].append(Order(PRODUCT, buy_price, min(MID_MAIN_QTY, buy_room)))
                    elif z >= MID_ENTRY_Z and sell_room > 0:
                        result[PRODUCT].append(Order(PRODUCT, sell_price, -min(MID_MAIN_QTY, sell_room)))

            mids.append(mid)
            data["mids"] = mids[-ROLLING_WINDOW:]

        trader_data = json.dumps(data, separators=(",", ":"))
        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data
