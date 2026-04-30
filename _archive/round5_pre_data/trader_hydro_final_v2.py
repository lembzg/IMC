from datamodel import TradingState, Order
import json
from collections import defaultdict

# ── HYDROGEL_PACK range strategy parameters ──────────────────────────────────
HYDRO_POS_LIM    = 200
HYDRO_STEP_SIZE  = 20
HYDRO_MAX_SPREAD = 20   # don't trade if book spread is wider than this (typical ~16)

# Mark 14 signal: Mark 14 always buys at lows / sells at highs (always vs Mark 38).
# When confirmed, shift thresholds to allow entries slightly deeper into neutral zone.
MARK_THRESHOLD_SHIFT = 5    # how far to extend buy/sell thresholds
MARK_SIGNAL_TTL      = 3000 # timestamps the signal stays active after last seen trade

# Buy tiers: (mid_below_threshold, target_long_position)
# Evaluated top-to-bottom; first match wins.
HYDRO_BUY_TIERS = [
    (9925, 70),
    (9930, 60),
    (9935, 50),
    (9940, 40),
]

# Sell tiers: (mid_above_threshold, target_short_position)
# Evaluated top-to-bottom; first match wins.
# Grid search optimum: sell_ref=10025 (+5 vs original 10020)
HYDRO_SELL_TIERS = [
    (10040, 70),
    (10035, 60),
    (10030, 50),
    (10025, 40),
]

# Neutral zone flatten: disabled by default.
# The strategy intentionally holds position while waiting for price to
# reach the opposite tier — flattening early cuts winning trades short.
HYDRO_NEUTRAL_FLATTEN = False
HYDRO_FLATTEN_TRIGGER = 30


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
        result = defaultdict(list)
        conversions = 0

        shared = {}
        if state.traderData:
            try:
                shared = json.loads(state.traderData)
            except Exception:
                shared = {}

        result["HYDROGEL_PACK"] = self.hydro_range_strategy(state, shared)

        trader_data = json.dumps(shared)
        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data

    def _hydro_mark_signal(self, state: TradingState, shared: dict) -> int:
        """
        Returns +1 (buy bias), -1 (sell bias), or 0 (neutral) based on Mark 14 activity.
        Mark 14 always trades vs Mark 38: buys at lows, sells at highs.
        Signal persists for MARK_SIGNAL_TTL timestamps after last observed trade.
        """
        ts = state.timestamp
        signal = 0
        for t in state.market_trades.get("HYDROGEL_PACK", []):
            if t.buyer == "Mark 14":
                signal = 1
            elif t.seller == "Mark 14":
                signal = -1

        if signal != 0:
            shared["hydro_mark_signal"] = signal
            shared["hydro_mark_ts"] = ts
        elif ts - shared.get("hydro_mark_ts", 0) > MARK_SIGNAL_TTL:
            shared["hydro_mark_signal"] = 0

        return shared.get("hydro_mark_signal", 0)

    def hydro_range_strategy(self, state: TradingState, shared: dict) -> list:
        product = "HYDROGEL_PACK"

        od = state.order_depths.get(product)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        spread   = best_ask - best_bid

        if spread > HYDRO_MAX_SPREAD or spread <= 0:
            return []

        mid = (best_bid + best_ask) / 2
        pos = state.position.get(product, 0)
        mark = self._hydro_mark_signal(state, shared)

        # ── Emergency unwind ──────────────────────────────────────────────────
        # Triggered only if price moves far outside the expected range.
        # Thresholds (9820 / 10100) are well outside normal operating range
        # so this should never fire under normal conditions.
        if mid < 9820 and pos > 0:
            logger.print(f"EMERGENCY UNWIND LONG: mid={mid} pos={pos}")
            return [Order("HYDROGEL_PACK", int(best_bid), -pos)]
        if mid > 10100 and pos < 0:
            logger.print(f"EMERGENCY UNWIND SHORT: mid={mid} pos={pos}")
            return [Order("HYDROGEL_PACK", int(best_ask), -pos)]

        buy_room  = HYDRO_POS_LIM - pos
        sell_room = HYDRO_POS_LIM + pos

        orders = []

        # ── Buy tiers ─────────────────────────────────────────────────────────
        # Mark 14 buy signal shifts thresholds up, allowing entries slightly into neutral zone.
        buy_shift = MARK_THRESHOLD_SHIFT if mark > 0 else 0
        for threshold, target in HYDRO_BUY_TIERS:
            if mid < threshold + buy_shift:
                qty = min(HYDRO_STEP_SIZE, target - pos, buy_room)
                if qty > 0:
                    orders.append(Order(product, int(best_ask), qty))
                break

        # ── Sell tiers ────────────────────────────────────────────────────────
        # Mark 14 sell signal shifts thresholds down similarly.
        if not orders:
            sell_shift = MARK_THRESHOLD_SHIFT if mark < 0 else 0
            for threshold, target in HYDRO_SELL_TIERS:
                if mid > threshold - sell_shift:
                    qty = min(HYDRO_STEP_SIZE, pos + target, sell_room)
                    if qty > 0:
                        orders.append(Order(product, int(best_bid), -qty))
                    break

        # ── Neutral zone flatten ──────────────────────────────────────────────
        if not orders and HYDRO_NEUTRAL_FLATTEN:
            if pos > HYDRO_FLATTEN_TRIGGER:
                qty = min(HYDRO_STEP_SIZE, pos, sell_room)
                if qty > 0:
                    orders.append(Order(product, int(best_bid), -qty))
            elif pos < -HYDRO_FLATTEN_TRIGGER:
                qty = min(HYDRO_STEP_SIZE, -pos, buy_room)
                if qty > 0:
                    orders.append(Order(product, int(best_ask), qty))

        return orders
