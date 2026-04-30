from collections import defaultdict
import json

from datamodel import Order, TradingState


PRODUCT = "HYDROGEL_PACK"
POSITION_LIMIT = 200

# Macro active taker. No price bands, no bot names, no passive maker edge.
HORIZON = 500
FAST_TURN = 25
ENTRY_Z = 1.35
EXIT_Z = 0.25
STOP_Z = 2.25
TARGET = 200
STEP = 50
MAX_AGE = 700


class Logger:
    def __init__(self):
        self.logs = ""

    def flush(self, state, orders, conversions, trader_data):
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
        od = state.order_depths.get(PRODUCT)
        if od is None or not od.buy_orders or not od.sell_orders:
            return []

        bids = sorted(od.buy_orders.items(), reverse=True)
        asks = sorted(od.sell_orders.items())
        best_bid = bids[0][0]
        best_ask = asks[0][0]
        mid = (best_bid + best_ask) / 2.0
        pos = state.position.get(PRODUCT, 0)

        hist = data.get("h", [])
        target = data.get("target", 0)
        age = data.get("age", 0)
        armed = data.get("armed", True)

        z = 0.0
        fast_move = 0.0
        if len(hist) >= HORIZON:
            long_move = mid - hist[-HORIZON]
            fast_move = mid - hist[-FAST_TURN] if len(hist) >= FAST_TURN else 0.0
            move_std = self.move_std(hist, HORIZON)
            z = 0.0 if move_std <= 0 else long_move / move_std

            if target == 0:
                if abs(z) < EXIT_Z:
                    armed = True

                # Fade only after the large move starts turning. This avoids
                # taking repeatedly into a one-way move while still using the
                # documented macro mean-reversion edge.
                if armed and z <= -ENTRY_Z and fast_move > 0:
                    target = TARGET
                    age = 0
                    armed = False
                elif armed and z >= ENTRY_Z and fast_move < 0:
                    target = -TARGET
                    age = 0
                    armed = False
            else:
                age += 1
                same_side_extreme = (target > 0 and z < -STOP_Z) or (target < 0 and z > STOP_Z)
                reverted = abs(z) <= EXIT_Z
                timed_out = age >= MAX_AGE
                if reverted or timed_out or same_side_extreme:
                    target = 0
                    age = 0

        orders = self.take_toward_target(bids, asks, pos, target)

        hist.append(mid)
        data["h"] = hist[-(HORIZON + 50):]
        data["target"] = target
        data["age"] = age
        data["armed"] = armed
        data["z"] = z
        data["fm"] = fast_move
        return orders

    def move_std(self, hist: list[float], horizon: int) -> float:
        if len(hist) < horizon + 20:
            return 0.0
        moves = [hist[i] - hist[i - horizon] for i in range(horizon, len(hist))]
        if not moves:
            return 0.0
        mean = sum(moves) / len(moves)
        variance = sum((x - mean) * (x - mean) for x in moves) / len(moves)
        return variance ** 0.5

    def take_toward_target(
        self,
        bids: list[tuple[int, int]],
        asks: list[tuple[int, int]],
        pos: int,
        target: int,
    ) -> list[Order]:
        orders = []
        target = max(-POSITION_LIMIT, min(POSITION_LIMIT, target))
        diff = target - pos
        if diff > 0:
            need = min(diff, STEP, POSITION_LIMIT - pos)
            for price, volume in asks:
                qty = min(need, abs(volume))
                if qty > 0:
                    orders.append(Order(PRODUCT, price, qty))
                    need -= qty
                if need <= 0:
                    break
        elif diff < 0:
            need = min(-diff, STEP, POSITION_LIMIT + pos)
            for price, volume in bids:
                qty = min(need, volume)
                if qty > 0:
                    orders.append(Order(PRODUCT, price, -qty))
                    need -= qty
                if need <= 0:
                    break
        return orders
