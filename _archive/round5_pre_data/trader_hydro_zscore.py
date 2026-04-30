import json
from typing import Any
from collections import defaultdict

from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState


PRODUCT = "HYDROGEL_PACK"
POS_LIM = 200

ROLLING_WINDOW = 700
ENTRY_Z = 2.4
EXIT_Z = 0.0
TARGET_SIZE = 200
TREND_LOOKBACK = 100
TREND_MAX = 50.0

FAIR_LOOKBACK = 1000
BOT_THRESH = 7
BOT_NORMAL_MAIN_QTY = 6
BOT_NORMAL_SMALL_QTY = 2
BOT_DIRECTIONAL_QTY = 10
BOT_IMPROVE = 1


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(
            self.to_json(
                [
                    self.compress_state(state, ""),
                    self.compress_orders(orders),
                    conversions,
                    "",
                    "",
                ]
            )
        )

        max_item_length = (self.max_log_length - base_length) // 3

        print(
            self.to_json(
                [
                    self.compress_state(state, self.truncate(state.traderData, max_item_length)),
                    self.compress_orders(orders),
                    conversions,
                    self.truncate(trader_data, max_item_length),
                    self.truncate(self.logs, max_item_length),
                ]
            )
        )

        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
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
        ]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        return [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr]

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        return value[:max_length]


logger = Logger()


class Trader:
    def bid(self, state: TradingState | None = None) -> int:
        return 0

    def run(self, state: TradingState):
        result = defaultdict(list)
        conversions = 0

        # -----------------------------
        # Restore state
        # -----------------------------
        try:
            data = json.loads(state.traderData) if state.traderData else {}
        except:
            data = {}

        mids = data.get("mids", [])
        macro_target = data.get("macro_target", 0)

        od = state.order_depths.get(PRODUCT)

        if od and od.buy_orders and od.sell_orders:
            bids = sorted(od.buy_orders.items(), reverse=True)
            asks = sorted(od.sell_orders.items())
            best_bid = bids[0][0]
            best_ask = asks[0][0]
            mid = (best_bid + best_ask) / 2

            pos = state.position.get(PRODUCT, 0)
            buy_sent = 0
            sell_sent = 0

            fair = data.get("fair", mid)
            alpha = 2 / (FAIR_LOOKBACK + 1)
            data["fair"] = alpha * mid + (1 - alpha) * fair

            # -----------------------------
            # Z-score logic. Use only prior mids for the fair value so the
            # current extreme is measured against the pre-existing regime.
            # -----------------------------
            if len(mids) >= ROLLING_WINDOW:
                window = mids[-ROLLING_WINDOW:]
                mean = sum(window) / ROLLING_WINDOW
                var = sum((x - mean) ** 2 for x in window) / ROLLING_WINDOW
                std = var ** 0.5

                if std > 0:
                    z = (mid - mean) / std
                    macro_allowed = True
                    if len(mids) >= TREND_LOOKBACK:
                        recent_move = abs(mid - mids[-TREND_LOOKBACK])
                        macro_allowed = recent_move <= TREND_MAX

                    if z >= ENTRY_Z and macro_allowed:
                        macro_target = -TARGET_SIZE
                    elif z <= -ENTRY_Z and macro_allowed:
                        macro_target = TARGET_SIZE

                    target = macro_target
                    target = max(-POS_LIM, min(POS_LIM, target))
                    diff = target - pos

                    # -----------------------------
                    # Execution: active taker, cross enough visible book depth
                    # to reach the intended macro position.
                    # -----------------------------
                    if diff > 0:
                        need = min(diff, POS_LIM - pos)
                        if need > 0:
                            price = asks[-1][0]
                            result[PRODUCT].append(Order(PRODUCT, price, need))
                            buy_sent += need
                    elif diff < 0:
                        need = min(-diff, POS_LIM + pos)
                        if need > 0:
                            price = bids[-1][0]
                            result[PRODUCT].append(Order(PRODUCT, price, -need))
                            sell_sent += need

            if macro_target == 0:
                buy_price = best_bid + BOT_IMPROVE
                sell_price = best_ask - BOT_IMPROVE
                buy_room = POS_LIM - pos - buy_sent
                sell_room = POS_LIM + pos - sell_sent

                if buy_price < sell_price:
                    if pos > 0:
                        sell_qty = min(BOT_NORMAL_MAIN_QTY, sell_room)
                        buy_qty = min(BOT_NORMAL_SMALL_QTY, buy_room)
                        if sell_qty > 0:
                            result[PRODUCT].append(Order(PRODUCT, sell_price, -sell_qty))
                        if buy_qty > 0:
                            result[PRODUCT].append(Order(PRODUCT, buy_price, buy_qty))
                    elif pos < 0:
                        buy_qty = min(BOT_NORMAL_MAIN_QTY, buy_room)
                        sell_qty = min(BOT_NORMAL_SMALL_QTY, sell_room)
                        if buy_qty > 0:
                            result[PRODUCT].append(Order(PRODUCT, buy_price, buy_qty))
                        if sell_qty > 0:
                            result[PRODUCT].append(Order(PRODUCT, sell_price, -sell_qty))
                    else:
                        buy_qty = min(BOT_NORMAL_MAIN_QTY, buy_room)
                        sell_qty = min(BOT_NORMAL_MAIN_QTY, sell_room)
                        if buy_qty > 0:
                            result[PRODUCT].append(Order(PRODUCT, buy_price, buy_qty))
                        if sell_qty > 0:
                            result[PRODUCT].append(Order(PRODUCT, sell_price, -sell_qty))

            mids.append(mid)
            if len(mids) > ROLLING_WINDOW:
                mids = mids[-ROLLING_WINDOW:]

        # -----------------------------
        # Save state
        # -----------------------------
        data["mids"] = mids
        data["macro_target"] = macro_target

        trader_data = json.dumps(data)

        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data
