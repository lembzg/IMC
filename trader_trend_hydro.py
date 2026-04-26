from collections import defaultdict
import json

from datamodel import Order, TradingState


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
    HYDRO_POS_LIMIT = 200

    # How far back to measure gradient (short window captures the local slope)
    GRADIENT_WINDOW = 500

    # Minimum absolute gradient to act (filters noise / flat periods)
    GRADIENT_THRESHOLD = 0.00

    # Fixed position size when we have a signal
    TARGET_SIZE = 100

    def run(self, state: TradingState):
        result = defaultdict(list)
        conversions = 0
        shared = {}
        if state.traderData:
            try:
                shared = json.loads(state.traderData)
            except json.JSONDecodeError:
                pass

        result["HYDROGEL_PACK"], hydro_data = self.hydro(state, shared)
        trader_data = json.dumps(hydro_data)
        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data

    def hydro(self, state: TradingState, shared: dict):
        product = "HYDROGEL_PACK"
        orders = []
        if product not in state.order_depths:
            return orders, shared

        order_depth = state.order_depths[product]
        bids = sorted(order_depth.buy_orders.keys(), reverse=True)
        asks = sorted(order_depth.sell_orders.keys())
        if not bids or not asks:
            return orders, shared

        best_bid = bids[0]
        best_ask = asks[0]
        mid = (best_bid + best_ask) / 2.0

        pos = state.position.get(product, 0)

        mid_hist = shared.get("hydro_mid_hist", [])
        mid_hist.append(mid)

        target = pos  # default: hold current position

        if len(mid_hist) >= self.GRADIENT_WINDOW:
            # Gradient = change over the last GRADIENT_WINDOW ticks (price per tick)
            gradient = (mid_hist[-1] - mid_hist[-self.GRADIENT_WINDOW]) / self.GRADIENT_WINDOW

            if gradient < -self.GRADIENT_THRESHOLD:
                # Price has been falling → reversal expected upward → go long
                target = self.TARGET_SIZE
            elif gradient > self.GRADIENT_THRESHOLD:
                # Price has been rising → reversal expected downward → go short
                target = -self.TARGET_SIZE
            # else: gradient too flat, do nothing

        target = max(-self.HYDRO_POS_LIMIT, min(self.HYDRO_POS_LIMIT, target))

        if target > pos:
            need = target - pos
            for ask in asks:
                available = abs(order_depth.sell_orders[ask])
                qty = min(need, available)
                if qty > 0:
                    orders.append(Order(product, ask, qty))
                    need -= qty
                if need <= 0:
                    break
        elif target < pos:
            need = pos - target
            for bid in bids:
                available = order_depth.buy_orders[bid]
                qty = min(need, available)
                if qty > 0:
                    orders.append(Order(product, bid, -qty))
                    need -= qty
                if need <= 0:
                    break

        # Keep history bounded to avoid traderData bloat
        shared["hydro_mid_hist"] = mid_hist[-300:]
        return orders, shared
