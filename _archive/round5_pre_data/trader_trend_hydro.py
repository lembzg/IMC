import json
from typing import Any

from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState


class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(self.to_json([
            self.compress_state(state, ""),
            self.compress_orders(orders),
            conversions,
            "",
            "",
        ]))
        max_item_length = (self.max_log_length - base_length) // 3
        print(self.to_json([
            self.compress_state(state, self.truncate(state.traderData, max_item_length)),
            self.compress_orders(orders),
            conversions,
            self.truncate(trader_data, max_item_length),
            self.truncate(self.logs, max_item_length),
        ]))
        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        return [[l.symbol, l.product, l.denomination] for l in listings.values()]

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        return {s: [od.buy_orders, od.sell_orders] for s, od in order_depths.items()}

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        return [[t.symbol, t.price, t.quantity, t.buyer, t.seller, t.timestamp] for arr in trades.values() for t in arr]

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {}
        for product, o in observations.conversionObservations.items():
            conversion_observations[product] = [
                o.bidPrice, o.askPrice, o.transportFees,
                o.exportTariff, o.importTariff,
                o.sugarPrice, o.sunlightIndex,
            ]
        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        return [[o.symbol, o.price, o.quantity] for arr in orders.values() for o in arr]

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        lo, hi = 0, min(len(value), max_length)
        out = ""
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = value[:mid]
            if len(candidate) < len(value):
                candidate += "..."
            if len(json.dumps(candidate)) <= max_length:
                out = candidate
                lo = mid + 1
            else:
                hi = mid - 1
        return out


logger = Logger()


class Trader:
    PRODUCT = "HYDROGEL_PACK"
    LIMIT = 200

    LOOKBACK = 800
    ENTRY_Z = 2.0
    ACTIVE_TARGET = 200

    PASSIVE_SIZE = 40
    PENNY_JUMP = 1
    INVENTORY_BRAKE = 200

    def run(self, state: TradingState) -> tuple[dict[Symbol, list[Order]], int, str]:
        result: dict[Symbol, list[Order]] = {}
        conversions = 0

        data = {}
        if state.traderData:
            try:
                data = json.loads(state.traderData)
            except json.JSONDecodeError:
                data = {}

        result[self.PRODUCT] = self.trade_hydro(state, data)
        trader_data = json.dumps(data, separators=(",", ":"))
        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data

    def bid(self, state: TradingState) -> int:
        return 0

    def trade_hydro(self, state: TradingState, data: dict) -> list[Order]:
        product = self.PRODUCT
        if product not in state.order_depths:
            return []

        od = state.order_depths[product]
        bids = sorted(od.buy_orders.items(), reverse=True)
        asks = sorted(od.sell_orders.items())
        if not bids or not asks:
            return []

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        mid = (best_bid + best_ask) / 2.0
        pos = state.position.get(product, 0)

        hist = data.get("h", [])
        z = self.rolling_z(mid, hist)

        orders: list[Order] = []
        buy_used = 0
        sell_used = 0

        target = pos
        if z >= self.ENTRY_Z:
            target = -self.ACTIVE_TARGET
        elif z <= -self.ENTRY_Z:
            target = self.ACTIVE_TARGET

        target = max(-self.LIMIT, min(self.LIMIT, target))
        if target > pos:
            buy_used += self.take_to_target(product, asks, orders, pos + buy_used, target)
        elif target < pos:
            sell_used += self.hit_to_target(product, bids, orders, pos - sell_used, target)

        buy_room = max(0, self.LIMIT - pos - buy_used)
        sell_room = max(0, self.LIMIT + pos - sell_used)

        quote_bid = best_bid + self.PENNY_JUMP
        quote_ask = best_ask - self.PENNY_JUMP
        if quote_bid < quote_ask:
            allow_bid = buy_room > 0 and pos < self.INVENTORY_BRAKE
            allow_ask = sell_room > 0 and pos > -self.INVENTORY_BRAKE

            if z <= -self.ENTRY_Z:
                allow_ask = False
            elif z >= self.ENTRY_Z:
                allow_bid = False

            if allow_bid:
                qty = min(self.PASSIVE_SIZE, buy_room)
                if qty > 0:
                    orders.append(Order(product, quote_bid, qty))
            if allow_ask:
                qty = min(self.PASSIVE_SIZE, sell_room)
                if qty > 0:
                    orders.append(Order(product, quote_ask, -qty))

        hist.append(mid)
        data["h"] = hist[-self.LOOKBACK:]
        return orders

    def rolling_z(self, mid: float, hist: list[float]) -> float:
        if len(hist) < self.LOOKBACK:
            return 0.0
        window = hist[-self.LOOKBACK:]
        mean = sum(window) / self.LOOKBACK
        variance = sum((x - mean) * (x - mean) for x in window) / self.LOOKBACK
        if variance <= 0:
            return 0.0
        return (mid - mean) / (variance ** 0.5)

    def take_to_target(
        self,
        product: str,
        asks: list[tuple[int, int]],
        orders: list[Order],
        current_pos: int,
        target: int,
    ) -> int:
        need = min(target - current_pos, self.LIMIT - current_pos)
        sent = 0
        for price, volume in asks:
            qty = min(need, abs(volume))
            if qty > 0:
                orders.append(Order(product, price, qty))
                sent += qty
                need -= qty
            if need <= 0:
                break
        return sent

    def hit_to_target(
        self,
        product: str,
        bids: list[tuple[int, int]],
        orders: list[Order],
        current_pos: int,
        target: int,
    ) -> int:
        need = min(current_pos - target, self.LIMIT + current_pos)
        sent = 0
        for price, volume in bids:
            qty = min(need, volume)
            if qty > 0:
                orders.append(Order(product, price, -qty))
                sent += qty
                need -= qty
            if need <= 0:
                break
        return sent
