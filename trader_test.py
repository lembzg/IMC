from datamodel import Order, TradingState
from typing import Dict, List
import json
import math


YELLOW = "UV_VISOR_YELLOW"
CLUSTER = (
    "UV_VISOR_YELLOW",
    "UV_VISOR_MAGENTA",
    "UV_VISOR_ORANGE",
    "UV_VISOR_RED",
)

POSITION_LIMIT = 10
ORDER_SIZE = 10

WINDOW = 4000
MIN_HISTORY = 1000
ENTRY_Z = 1.00
EXIT_Z = 0.10

HISTORY_KEY = "yellow_uv_cluster_spread"


class Trader:
    def bid(self, state=None) -> int:
        return 0

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {YELLOW: []}

        data = {}
        if state.traderData:
            try:
                data = json.loads(state.traderData)
            except Exception:
                data = {}

        history = data.get(HISTORY_KEY, [])

        mids = {}
        depths = {}

        for product in CLUSTER:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                data[HISTORY_KEY] = history[-WINDOW:]
                return result, 0, json.dumps(data)

            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            mids[product] = (best_bid + best_ask) / 2.0
            depths[product] = (best_bid, best_ask)

        cluster_avg = sum(mids[p] for p in CLUSTER) / len(CLUSTER)
        spread = mids[YELLOW] - cluster_avg

        z = None
        if len(history) >= MIN_HISTORY:
            sample = history[-WINDOW:]
            mean = sum(sample) / len(sample)
            var = sum((x - mean) * (x - mean) for x in sample) / max(1, len(sample) - 1)
            std = math.sqrt(var)
            if std > 1e-9:
                z = (spread - mean) / std

        # Append after z calculation so current tick is not in its own rolling stats.
        history.append(round(spread, 2))
        data[HISTORY_KEY] = history[-WINDOW:]

        if z is None:
            return result, 0, json.dumps(data)

        best_bid, best_ask = depths[YELLOW]
        position = state.position.get(YELLOW, 0)

        target_pos = position

        # Flipped/momentum rule:
        # YELLOW high vs UV cluster -> buy YELLOW
        # YELLOW low vs UV cluster  -> sell YELLOW
        if position == 0:
            if z >= ENTRY_Z:
                target_pos = ORDER_SIZE
            elif z <= -ENTRY_Z:
                target_pos = -ORDER_SIZE

        elif position > 0:
            if z <= EXIT_Z:
                target_pos = 0

        elif position < 0:
            if z >= -EXIT_Z:
                target_pos = 0

        target_pos = max(-POSITION_LIMIT, min(POSITION_LIMIT, target_pos))
        delta = target_pos - position

        orders: List[Order] = []
        if delta > 0:
            orders.append(Order(YELLOW, best_ask, delta))
        elif delta < 0:
            orders.append(Order(YELLOW, best_bid, delta))

        result[YELLOW] = orders
        return result, 0, json.dumps(data)