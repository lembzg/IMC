from datamodel import TradingState, Order
import json
from collections import defaultdict


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
    def bid(self):
        return 1

    def run(self, state: TradingState):
        result = defaultdict(list)
        conversions = 0

        try:
            shared = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            shared = {}

        orders, shared = self.hydro_baseline(state, shared)
        result["HYDROGEL_PACK"] = orders

        trader_data = json.dumps(shared)
        logger.flush(state, result, conversions, trader_data)
        return result, conversions, trader_data

    def hydro_baseline(self, state: TradingState, shared: dict):
        product = "HYDROGEL_PACK"
        orders = []

        POS_LIMIT = 200
        LOOKBACK = 500
        ENTRY = 2.5
        TARGET = 200

        if product not in state.order_depths:
            return orders, shared

        od = state.order_depths[product]
        if not od.buy_orders or not od.sell_orders:
            return orders, shared

        bids = sorted(od.buy_orders.keys(), reverse=True)
        asks = sorted(od.sell_orders.keys())
        best_bid, best_ask = bids[0], asks[0]
        mid = (best_bid + best_ask) / 2
        pos = state.position.get(product, 0)

        hist = shared.get("hydro_hist", [])
        hist.append(mid)
        hist = hist[-LOOKBACK:]
        shared["hydro_hist"] = hist

        signal = 0.0
        if len(hist) >= LOOKBACK:
            window = hist[-LOOKBACK:]
            mean = sum(window) / len(window)
            var = sum((x - mean) ** 2 for x in window) / len(window)
            std = var ** 0.5
            if std > 0:
                signal = (mid - mean) / std

        # direction=-1: counter-trend (mean reversion)
        directed = -signal
        if directed >= ENTRY:
            target = TARGET
        elif directed <= -ENTRY:
            target = -TARGET
        else:
            target = pos  # hold

        target = max(-POS_LIMIT, min(POS_LIMIT, target))

        if target > pos:
            need = min(target - pos, POS_LIMIT - pos)
            for ask in asks:
                qty = min(need, -od.sell_orders[ask])
                if qty > 0:
                    orders.append(Order(product, ask, qty))
                    need -= qty
                if need <= 0:
                    break
        elif target < pos:
            need = min(pos - target, POS_LIMIT + pos)
            for bid in bids:
                qty = min(need, od.buy_orders[bid])
                if qty > 0:
                    orders.append(Order(product, bid, -qty))
                    need -= qty
                if need <= 0:
                    break

        return orders, shared