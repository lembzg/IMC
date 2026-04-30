import json
from collections import defaultdict
from typing import Any

from datamodel import Order, ProsperityEncoder, Symbol, TradingState


PRODUCT = "HYDROGEL_PACK"
POS_LIM = 200

ROLLING_WINDOW = 700
ENTRY_Z = 2.4
FULL_Z = 3.0
EXIT_Z = 0.3
TREND_LOOKBACK = 100
TREND_SKIP = 20
STOP_LOSS = 20
MAX_TAKE_PER_TICK = 40

BOT_NORMAL_MAIN_QTY = 6
BOT_NORMAL_SMALL_QTY = 2
BOT_IMPROVE = 1


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
        macro_target = data.get("macro_target", 0)
        entry_mid = data.get("entry_mid")
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

            if len(mids) >= ROLLING_WINDOW:
                window = mids[-ROLLING_WINDOW:]
                mean = sum(window) / ROLLING_WINDOW
                var = sum((x - mean) ** 2 for x in window) / ROLLING_WINDOW
                std = var ** 0.5

                if std > 0:
                    z = (mid - mean) / std
                    short_mean = sum(mids[-TREND_LOOKBACK:]) / TREND_LOOKBACK
                    long_mean = mean
                    trend = short_mean - long_mean
                    skip_short = z > 0 and trend > TREND_SKIP
                    skip_long = z < 0 and trend < -TREND_SKIP

                    old_target = macro_target
                    if z >= FULL_Z and not skip_short:
                        macro_target = -200
                    elif z >= ENTRY_Z and not skip_short:
                        macro_target = -100
                    elif z <= -FULL_Z and not skip_long:
                        macro_target = 200
                    elif z <= -ENTRY_Z and not skip_long:
                        macro_target = 100
                    elif abs(z) <= EXIT_Z:
                        macro_target = 0
                        entry_mid = None

                    if old_target == 0 and macro_target != 0:
                        entry_mid = mid

                    if entry_mid is not None:
                        if pos > 0 and mid < entry_mid - STOP_LOSS:
                            macro_target = min(macro_target, 100)
                        elif pos < 0 and mid > entry_mid + STOP_LOSS:
                            macro_target = max(macro_target, -100)

                    target = max(-POS_LIM, min(POS_LIM, macro_target))
                    diff = target - pos

                    if diff > 0:
                        need = min(diff, POS_LIM - pos, MAX_TAKE_PER_TICK)
                        if need > 0:
                            result[PRODUCT].append(Order(PRODUCT, asks[-1][0], need))
                            buy_sent += need
                    elif diff < 0:
                        need = min(-diff, POS_LIM + pos, MAX_TAKE_PER_TICK)
                        if need > 0:
                            result[PRODUCT].append(Order(PRODUCT, bids[-1][0], -need))
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
                    elif pos < 0:
                        buy_qty = min(BOT_NORMAL_MAIN_QTY, buy_room)
                        sell_qty = min(BOT_NORMAL_SMALL_QTY, sell_room)
                    else:
                        buy_qty = min(BOT_NORMAL_MAIN_QTY, buy_room)
                        sell_qty = min(BOT_NORMAL_MAIN_QTY, sell_room)
                    if buy_qty > 0:
                        result[PRODUCT].append(Order(PRODUCT, buy_price, buy_qty))
                    if sell_qty > 0:
                        result[PRODUCT].append(Order(PRODUCT, sell_price, -sell_qty))

            mids.append(mid)
            data["mids"] = mids[-ROLLING_WINDOW:]
            data["macro_target"] = macro_target
            data["entry_mid"] = entry_mid

        trader_data = json.dumps(data, separators=(",", ":"))
        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data
