from datamodel import Order, TradingState
from typing import Dict, List, Optional
import json
import math


SNACKPACK_TRADES = ("SNACKPACK_RASPBERRY", "SNACKPACK_VANILLA")
SNACKPACK_PRODUCTS = (
    "SNACKPACK_CHOCOLATE",
    "SNACKPACK_PISTACHIO",
    "SNACKPACK_RASPBERRY",
    "SNACKPACK_STRAWBERRY",
    "SNACKPACK_VANILLA",
)
PEBBLES_TRADES = ("PEBBLES_XS", "PEBBLES_XL")
POSITION_LIMIT = 10
HISTORY_LIMIT = 200
PRODUCT_OFFSETS = {
    "SNACKPACK_RASPBERRY": 0,
    "SNACKPACK_VANILLA": 0,
}
ENTRY_THRESHOLD = 255
EXIT_THRESHOLD = 105
ORDER_SIZE = 4
PEBBLES_PAIR_FAIR = 20200
PEBBLES_ENTRY_THRESHOLD = 200
PEBBLES_EXIT_THRESHOLD = 0
PEBBLES_ORDER_SIZE = 10
XS_RECT_TRADES = ("PEBBLES_XS", "MICROCHIP_RECTANGLE")
XS_RECT_HISTORY_KEY = "xs_rect_spread"
XS_RECT_HISTORY_LIMIT = 1000
XS_RECT_WARMUP = 200
XS_RECT_ENTRY_Z = 1.75
XS_RECT_EXIT_Z = 0.05
XS_RECT_ORDER_SIZE = 3
PEBBLES_MS_TRADES = ("PEBBLES_M", "PEBBLES_S")
PEBBLES_MS_PAIR_FAIR = 19000
PEBBLES_MS_ENTRY_THRESHOLD = 700
PEBBLES_MS_EXIT_THRESHOLD = 0
PEBBLES_MS_ORDER_SIZE = 5
SNACKPAIR_TRADES = ("SNACKPACK_STRAWBERRY", "SNACKPACK_PISTACHIO")
SNACKPAIR_FAIR = 20150
SNACKPAIR_ENTRY_THRESHOLD = 150
SNACKPAIR_EXIT_THRESHOLD = 100
SNACKPAIR_ORDER_SIZE = 5
CHOCOLATE_BUY_ENTRY = -500
CHOCOLATE_SELL_ENTRY = 0
CHOCOLATE_EXIT_CENTER = -250
CHOCOLATE_SIGNAL_SIZE = 10
TRANSLATOR_TARGET = "TRANSLATOR_SPACE_GRAY"
TRANSLATOR_CLUSTER_PRODUCTS = (
    "PANEL_2X2",
    "PEBBLES_S",
    "ROBOT_LAUNDRY",
    "ROBOT_IRONING",
    "SNACKPACK_CHOCOLATE",
    "OXYGEN_SHAKE_MINT",
    "MICROCHIP_TRIANGLE",
    "MICROCHIP_OVAL",
)
TRANSLATOR_CLUSTER_THRESHOLD = 75
PANEL_CLUSTER_TARGET = "PANEL_2X2"
PANEL_CLUSTER_PRODUCTS = (
    "PEBBLES_S",
    "ROBOT_LAUNDRY",
    "ROBOT_IRONING",
    "SNACKPACK_CHOCOLATE",
    "OXYGEN_SHAKE_MINT",
    "MICROCHIP_TRIANGLE",
    "MICROCHIP_OVAL",
    "TRANSLATOR_SPACE_GRAY",
)
PANEL_CLUSTER_THRESHOLD = 200
PANEL44_CLUSTER_TARGET = "PANEL_4X4"
PANEL44_CLUSTER_PRODUCTS = (
    "PEBBLES_S",
    "ROBOT_LAUNDRY",
    "ROBOT_IRONING",
    "SNACKPACK_CHOCOLATE",
    "OXYGEN_SHAKE_MINT",
    "MICROCHIP_TRIANGLE",
    "MICROCHIP_OVAL",
    "TRANSLATOR_SPACE_GRAY",
)
PANEL44_CLUSTER_THRESHOLD = 175
PANEL_1X_TARGET = "PANEL_1X2"
PANEL_1X_SIGNAL = "PANEL_1X4"
PANEL_1X_HISTORY_KEY = "panel_1x_sum"
PANEL_1X_HISTORY_LIMIT = 3000
PANEL_1X_WARMUP = 500
PANEL_1X_ENTRY_Z = 1.5
PANEL_1X_EXIT_Z = 0.1
PANEL_1X_ORDER_SIZE = 1
UV_AO_TRADES = ("UV_VISOR_AMBER", "UV_VISOR_ORANGE")
UV_AO_PAIR_FAIR = 18338
UV_AO_ENTRY_THRESHOLD = 200
UV_AO_EXIT_THRESHOLD = 100
IRON_PEB_TRADES = ("ROBOT_IRONING", "PEBBLES_S")
IRON_PEB_ENTRY = 250
IRON_PEB_EXIT = 0
PEBBLES_L_FAIR_PRODUCTS = ("PEBBLES_XS", "PEBBLES_S", "PEBBLES_M", "PEBBLES_XL")
PEBBLES_L_ENTRY_THRESHOLD = 400
PEBBLES_L_EXIT_THRESHOLD = 0
CHIP_CT_TRADES = ("MICROCHIP_CIRCLE", "MICROCHIP_TRIANGLE")
CHIP_CT_PAIR_FAIR = 19127
CHIP_CT_ENTRY = 200
CHIP_CT_EXIT = 100
ROBOT_LD_TRADES = ("ROBOT_LAUNDRY", "ROBOT_DISHES")
ROBOT_LD_HISTORY_KEY = "robot_ld_sum"
ROBOT_LD_HISTORY_LIMIT = 3000
ROBOT_LD_WARMUP = 400
ROBOT_LD_ENTRY_Z = 1.5
ROBOT_LD_EXIT_Z = 0.5
ROBOT_LD_ORDER_SIZE = 10
ROBOT_MD_TRADES = ("ROBOT_MOPPING", "ROBOT_DISHES")
ROBOT_MD_HISTORY_KEY = "robot_md_sum"
ROBOT_MD_HISTORY_LIMIT = 3000
ROBOT_MD_WARMUP = 300
ROBOT_MD_ENTRY_Z = 2.5
ROBOT_MD_EXIT_Z = 0.75
ROBOT_MD_ORDER_SIZE = 5
SUEDE_COTTON_TRADES = ("SLEEP_POD_SUEDE", "SLEEP_POD_COTTON")
SUEDE_COTTON_ENTRY = 300
SUEDE_COTTON_EXIT = 150
UV_RM_TRADES = ("UV_VISOR_RED", "UV_VISOR_MAGENTA")
UV_RM_ENTRY = 400
UV_RM_EXIT = 50
UV_YO_SIGNAL = "UV_VISOR_YELLOW"
UV_YO_TARGET = "UV_VISOR_ORANGE"
UV_YO_ENTRY = 700
UV_YO_EXIT = 50
GALAXY_DM_PR_TRADES = ("GALAXY_SOUNDS_DARK_MATTER", "GALAXY_SOUNDS_PLANETARY_RINGS")
GALAXY_DM_PR_ENTRY = 400
GALAXY_DM_PR_EXIT = 0
GALAXY_SW_DM_TRADES = ("GALAXY_SOUNDS_SOLAR_WINDS", "GALAXY_SOUNDS_DARK_MATTER")
GALAXY_SW_DM_ENTRY = 200
GALAXY_SW_DM_EXIT = 0
GALAXY_SW_BH_SIGNAL = "GALAXY_SOUNDS_SOLAR_WINDS"
GALAXY_SW_BH_TARGET = "GALAXY_SOUNDS_BLACK_HOLES"
GALAXY_SW_BH_ENTRY = 900
GALAXY_SW_BH_EXIT = 0
TRANSLATOR_ECLIPSE_TARGET = "TRANSLATOR_ECLIPSE_CHARCOAL"
TRANSLATOR_AVG_PRODUCTS = (
    "TRANSLATOR_SPACE_GRAY",
    "TRANSLATOR_ASTRO_BLACK",
    "TRANSLATOR_ECLIPSE_CHARCOAL",
    "TRANSLATOR_GRAPHITE_MIST",
    "TRANSLATOR_VOID_BLUE",
)
TRANSLATOR_ECLIPSE_AVG_ENTRY = 650
TRANSLATOR_ECLIPSE_AVG_EXIT = 200
TRANSLATOR_ECLIPSE_AVG_SIZE = 10
TRANSLATOR_VOID_TARGET = "TRANSLATOR_VOID_BLUE"
TRANSLATOR_VOID_SIGNAL_PRODUCTS = (
    "TRANSLATOR_SPACE_GRAY",
    "TRANSLATOR_ASTRO_BLACK",
    "TRANSLATOR_ECLIPSE_CHARCOAL",
    "TRANSLATOR_GRAPHITE_MIST",
    "TRANSLATOR_VOID_BLUE",
)
TRANSLATOR_VOID_FV = 49600
TRANSLATOR_VOID_ENTRY = 900
TRANSLATOR_VOID_EXIT = 0
UV_AMBER_OTHERS = ("UV_VISOR_YELLOW", "UV_VISOR_ORANGE", "UV_VISOR_RED", "UV_VISOR_MAGENTA")
UV_AMBER_FAIR = 18000
UV_AMBER_ENTRY = 250
UV_AMBER_EXIT = 150
RASP_PIS_EMA_ALPHA = 0.001
RASP_PIS_ENTRY = 300
RASP_PIS_EXIT = 75
RASP_PIS_ORDER_SIZE = 5
NYLON_CHOCOLATE_TARGET = "SLEEP_POD_NYLON"
NYLON_CHOCOLATE_SIGNAL = "OXYGEN_SHAKE_CHOCOLATE"
NYLON_CHOCOLATE_HISTORY_KEY = "nylon_chocolate_spread"
NYLON_CHOCOLATE_HISTORY_LIMIT = 1000
NYLON_CHOCOLATE_WARMUP = 500
NYLON_CHOCOLATE_ENTRY_Z = 2.0
NYLON_CHOCOLATE_EXIT_Z = 0.05
NYLON_CHOCOLATE_SIZE = 1
# ─── Robot Vacuuming (vacuum + rectangle rolling-sum signal) ───
ROBOT_VAC_TARGET = "ROBOT_VACUUMING"
ROBOT_VAC_SIGNAL = "MICROCHIP_RECTANGLE"
ROBOT_VAC_HISTORY_KEY = "robot_vac_rect_sum"
ROBOT_VAC_HISTORY_LIMIT = 1000
ROBOT_VAC_WARMUP = 1000
ROBOT_VAC_ENTRY_Z = 2.0
ROBOT_VAC_EXIT_Z = 0.05
ROBOT_VAC_SIZE = 1
# ─── Galaxy Solar Flames (pair vs Solar Winds; SF−SW mean≈−14, std≈398) ───
SOLAR_FLAMES_SIGNAL = "GALAXY_SOUNDS_SOLAR_WINDS"
SOLAR_FLAMES_TARGET = "GALAXY_SOUNDS_SOLAR_FLAMES"
SOLAR_FLAMES_FAIR_DIFF = -14.1  # SF - SW mean
SOLAR_FLAMES_ENTRY = 500        # ~1.25σ of 397.74
SOLAR_FLAMES_EXIT = 150
SOLAR_FLAMES_SIZE = 10
# ─── Sleep Pod Lamb Wool (pair vs Nylon; LW−NYLON mean=685, std=348) ───
LAMB_WOOL_SIGNAL = "SLEEP_POD_NYLON"
LAMB_WOOL_TARGET = "SLEEP_POD_LAMB_WOOL"
LAMB_WOOL_FAIR_DIFF = 685.3     # LW - NYLON mean
LAMB_WOOL_ENTRY = 450           # ~1.3σ of 348.46
LAMB_WOOL_EXIT = 150
LAMB_WOOL_SIZE = 10
# ─── Oxygen Shake Mint (group mean; MINT−group mean=−1122.5, std=491) ───
MINT_TARGET = "OXYGEN_SHAKE_MINT"
MINT_GROUP = ("OXYGEN_SHAKE_MORNING_BREATH", "OXYGEN_SHAKE_EVENING_BREATH", "OXYGEN_SHAKE_GARLIC", "OXYGEN_SHAKE_CHOCOLATE")
MINT_FAIR_DIFF = -1122.5        # MINT - group_avg mean
MINT_ENTRY = 700                # ~1.4σ of 491.66
MINT_EXIT = 200
MINT_SIZE = 10
# ─── UV Visor Yellow (group mean; YELLOW−group mean=403, std=766) ───
UV_YELLOW_TARGET = "UV_VISOR_YELLOW"
UV_YELLOW_GROUP = ("UV_VISOR_ORANGE", "UV_VISOR_RED", "UV_VISOR_MAGENTA", "UV_VISOR_AMBER")
UV_YELLOW_FAIR_DIFF = 403.3     # YELLOW - group_avg mean
UV_YELLOW_ENTRY = 1000          # ~1.3σ of 766.43
UV_YELLOW_EXIT = 300
UV_YELLOW_SIZE = 10
# ─── Microchip Square (vs OVAL; SQ−OVAL mean=8703, std=514) ───
MC_SQ_TARGET = "MICROCHIP_SQUARE"
MC_SQ_SIGNAL = "MICROCHIP_OVAL"
MC_SQ_FAIR_DIFF = 8702.9        # SQ - OVAL mean
MC_SQ_ENTRY = 700               # ~1.36σ of 513.96
MC_SQ_EXIT = 200
MC_SQ_SIZE = 10
# ─── Panel 2X4 (vs Panel 1X2; 2X4−1X2 mean=2620, std=231) ───
PANEL2X4_TARGET = "PANEL_2X4"
PANEL2X4_SIGNAL = "PANEL_1X2"
PANEL2X4_FAIR_DIFF = 2620.0     # 2X4 - 1X2 mean
PANEL2X4_ENTRY = 300            # ~1.3σ of 231.82
PANEL2X4_EXIT = 100
PANEL2X4_SIZE = 10
# ─── Panel 1X4 (cluster mean reversion; includes 1X4 in the cluster avg) ───
PANEL1X4_TARGET = "PANEL_1X4"
PANEL1X4_GROUP = (
    "MICROCHIP_RECTANGLE",
    "OXYGEN_SHAKE_MORNING_BREATH",
    "PEBBLES_XS",
    "PANEL_1X4",
    "ROBOT_VACUUMING",
    "UV_VISOR_AMBER",
    "TRANSLATOR_ASTRO_BLACK",
    "SNACKPACK_PISTACHIO",
)
PANEL1X4_FAIR_DIFF = 335.7
PANEL1X4_ENTRY = 500
PANEL1X4_EXIT = 0
PANEL1X4_SIZE = 1

# ─────────────────────────── trader_test module helpers ───────────────────────────

def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _clean_history(raw_values, history_limit: int) -> List[int]:
    cleaned: List[int] = []
    if not isinstance(raw_values, list):
        return cleaned
    for value in raw_values[-history_limit:]:
        try:
            cleaned.append(int(value))
        except (TypeError, ValueError):
            continue
    return cleaned


def _rolling_z_score(history: List[int], current_residual: int, window: int, min_history: int, min_std: float, residual_scale: int) -> Optional[float]:
    lookback = history[-window:]
    if len(lookback) < min_history:
        return None
    mean = sum(lookback) / len(lookback)
    mean_square = sum(v * v for v in lookback) / len(lookback)
    variance = max(0.0, mean_square - mean * mean)
    std = math.sqrt(variance)
    if std < min_std * residual_scale:
        return None
    return (current_residual - mean) / std


def _order_to_target(product, order_depth, current_position: int, target_position: int, position_limit: int, max_order_size: int) -> List[Order]:
    orders: List[Order] = []
    target_position = _clamp(target_position, -position_limit, position_limit)
    desired_delta = target_position - current_position
    if desired_delta == 0:
        return orders
    if not order_depth.buy_orders or not order_depth.sell_orders:
        return orders
    best_bid = max(order_depth.buy_orders)
    best_ask = min(order_depth.sell_orders)
    if desired_delta > 0:
        visible_volume = max(0, -order_depth.sell_orders.get(best_ask, 0))
        limit_room = max(0, position_limit - current_position)
        quantity = min(desired_delta, visible_volume, limit_room, max_order_size)
        if quantity > 0:
            orders.append(Order(product, best_ask, quantity))
    else:
        visible_volume = max(0, order_depth.buy_orders.get(best_bid, 0))
        limit_room = max(0, position_limit + current_position)
        quantity = min(-desired_delta, visible_volume, limit_room, max_order_size)
        if quantity > 0:
            orders.append(Order(product, best_bid, -quantity))
    return orders


def _mid_price(order_depth) -> Optional[float]:
    if not order_depth or not order_depth.buy_orders or not order_depth.sell_orders:
        return None
    return (max(order_depth.buy_orders) + min(order_depth.sell_orders)) / 2.0


# ─────────────────────────── TranslatorModule (trader_test) ───────────────────────────

class _TranslatorModule:
    PRODUCTS = (
        "TRANSLATOR_SPACE_GRAY",
        "TRANSLATOR_ASTRO_BLACK",
        "TRANSLATOR_ECLIPSE_CHARCOAL",
        "TRANSLATOR_GRAPHITE_MIST",
        "TRANSLATOR_VOID_BLUE",
    )
    WINDOW = 1200
    MIN_HISTORY = 1200
    ENTRY_Z = 1.75
    MIN_STD = 1.0
    TARGET_SIZE = 10
    POSITION_LIMIT = 10
    MAX_ORDER_SIZE = 10
    HISTORY_LIMIT = 1200
    RESIDUAL_SCALE = 10

    def load_state(self, loaded):
        histories = {p: [] for p in self.PRODUCTS}
        targets = {p: 0 for p in self.PRODUCTS}
        if not isinstance(loaded, dict):
            return histories, targets
        raw_h = loaded.get("h", {})
        if isinstance(raw_h, dict):
            for p in self.PRODUCTS:
                histories[p] = _clean_history(raw_h.get(p, []), self.HISTORY_LIMIT)
        raw_t = loaded.get("t", {})
        if isinstance(raw_t, dict):
            for p in self.PRODUCTS:
                try:
                    targets[p] = _clamp(int(raw_t.get(p, 0)), -self.TARGET_SIZE, self.TARGET_SIZE)
                except (TypeError, ValueError):
                    targets[p] = 0
        return histories, targets

    def dump_state(self, histories, targets) -> dict:
        return {
            "h": {p: histories.get(p, [])[-self.HISTORY_LIMIT:] for p in self.PRODUCTS},
            "t": {p: int(targets.get(p, 0)) for p in self.PRODUCTS},
        }

    def run(self, state: TradingState, histories, targets, trade_products, result) -> dict:
        mids = {}
        for p in self.PRODUCTS:
            od = state.order_depths.get(p)
            mid = _mid_price(od)
            if mid is None:
                return targets
            mids[p] = mid
        group_mean = sum(mids.values()) / len(self.PRODUCTS)
        residuals = {p: int(round((mids[p] - group_mean) * self.RESIDUAL_SCALE)) for p in self.PRODUCTS}
        next_targets = {}
        for p in self.PRODUCTS:
            history = histories[p]
            has_min = len(history) >= self.MIN_HISTORY
            z = _rolling_z_score(history, residuals[p], self.WINDOW, self.MIN_HISTORY, self.MIN_STD, self.RESIDUAL_SCALE)
            prev = targets.get(p, 0)
            if not has_min:
                next_targets[p] = 0
            elif z is None:
                next_targets[p] = prev
            elif z > self.ENTRY_Z:
                next_targets[p] = -self.TARGET_SIZE
            elif z < -self.ENTRY_Z:
                next_targets[p] = self.TARGET_SIZE
            else:
                next_targets[p] = prev
        for p in trade_products:
            od = state.order_depths.get(p)
            if od is None:
                continue
            orders = _order_to_target(p, od, state.position.get(p, 0), next_targets[p], self.POSITION_LIMIT, self.MAX_ORDER_SIZE)
            if orders:
                result[p] = orders
        for p in self.PRODUCTS:
            history = histories[p]
            history.append(residuals[p])
            if len(history) > self.HISTORY_LIMIT:
                del history[:len(history) - self.HISTORY_LIMIT]
        return next_targets


# ─────────────────────────── MicrochipModule (trader_test) ───────────────────────────

class _MicrochipModule:
    PRODUCTS = ("MICROCHIP_OVAL", "MICROCHIP_TRIANGLE")
    WINDOW = 1000
    MIN_HISTORY = 1000
    ENTRY_Z = 1.50
    MIN_STD = 1.0
    TARGET_SIZE = 10
    POSITION_LIMIT = 10
    MAX_ORDER_SIZE = 10
    HISTORY_LIMIT = 1000
    RESIDUAL_SCALE = 10

    def load_state(self, loaded):
        history: List[int] = []
        targets = {p: 0 for p in self.PRODUCTS}
        if not isinstance(loaded, dict):
            return history, targets
        history = _clean_history(loaded.get("h", []), self.HISTORY_LIMIT)
        raw_t = loaded.get("t", {})
        if isinstance(raw_t, dict):
            for p in self.PRODUCTS:
                try:
                    targets[p] = _clamp(int(raw_t.get(p, 0)), -self.TARGET_SIZE, self.TARGET_SIZE)
                except (TypeError, ValueError):
                    targets[p] = 0
        return history, targets

    def dump_state(self, history, targets) -> dict:
        return {"h": history[-self.HISTORY_LIMIT:], "t": {p: int(targets.get(p, 0)) for p in self.PRODUCTS}}

    def run(self, state: TradingState, history, targets, result) -> dict:
        mids = {}
        for p in self.PRODUCTS:
            od = state.order_depths.get(p)
            mid = _mid_price(od)
            if mid is None:
                return targets
            mids[p] = mid
        oval, triangle = self.PRODUCTS
        residual = int(round((mids[oval] - mids[triangle]) * self.RESIDUAL_SCALE))
        has_min = len(history) >= self.MIN_HISTORY
        z = _rolling_z_score(history, residual, self.WINDOW, self.MIN_HISTORY, self.MIN_STD, self.RESIDUAL_SCALE)
        prev_oval, prev_tri = targets.get(oval, 0), targets.get(triangle, 0)
        if not has_min:
            next_targets = {oval: 0, triangle: 0}
        elif z is None:
            next_targets = dict(targets)
        elif z > self.ENTRY_Z:
            next_targets = {oval: -self.TARGET_SIZE, triangle: self.TARGET_SIZE}
        elif z < -self.ENTRY_Z:
            next_targets = {oval: self.TARGET_SIZE, triangle: -self.TARGET_SIZE}
        else:
            next_targets = dict(targets)
        for p in self.PRODUCTS:
            od = state.order_depths.get(p)
            if od is None:
                continue
            orders = _order_to_target(p, od, state.position.get(p, 0), next_targets[p], self.POSITION_LIMIT, self.MAX_ORDER_SIZE)
            if orders:
                result[p] = orders
        history.append(residual)
        if len(history) > self.HISTORY_LIMIT:
            del history[:len(history) - self.HISTORY_LIMIT]
        return next_targets


class _MicrochipRectModule:
    """Trade RECTANGLE only, using OVAL-RECT z-score as signal.
    OVAL is managed by _MicrochipModule so we never touch it here."""
    SIGNAL = "MICROCHIP_OVAL"
    TARGET = "MICROCHIP_RECTANGLE"
    WINDOW = 600
    MIN_HISTORY = 600
    ENTRY_Z = 0.75
    EXIT_Z = 0.1
    MIN_STD = 1.0
    TARGET_SIZE = 10
    POSITION_LIMIT = 10
    MAX_ORDER_SIZE = 10
    HISTORY_LIMIT = 600
    RESIDUAL_SCALE = 10

    def load_state(self, loaded):
        history: List[int] = []
        target = 0
        if not isinstance(loaded, dict):
            return history, target
        history = _clean_history(loaded.get("h", []), self.HISTORY_LIMIT)
        try:
            target = _clamp(int(loaded.get("t", 0)), -self.TARGET_SIZE, self.TARGET_SIZE)
        except (TypeError, ValueError):
            target = 0
        return history, target

    def dump_state(self, history, target) -> dict:
        return {"h": history[-self.HISTORY_LIMIT:], "t": int(target)}

    def run(self, state: TradingState, history, target, result) -> int:
        od_sig = state.order_depths.get(self.SIGNAL)
        od_tgt = state.order_depths.get(self.TARGET)
        sig_mid = _mid_price(od_sig)
        tgt_mid = _mid_price(od_tgt)
        if sig_mid is None or tgt_mid is None:
            return target
        residual = int(round((sig_mid - tgt_mid) * self.RESIDUAL_SCALE))
        has_min = len(history) >= self.MIN_HISTORY
        z = _rolling_z_score(history, residual, self.WINDOW, self.MIN_HISTORY, self.MIN_STD, self.RESIDUAL_SCALE)
        if not has_min or z is None:
            next_target = 0
        elif z > self.ENTRY_Z:
            # OVAL overpriced vs RECT → RECT expected to rise → long RECT
            next_target = self.TARGET_SIZE
        elif z < -self.ENTRY_Z:
            # OVAL underpriced vs RECT → RECT expected to fall → short RECT
            next_target = -self.TARGET_SIZE
        elif abs(z) < self.EXIT_Z:
            next_target = 0
        else:
            next_target = target
        orders = _order_to_target(self.TARGET, od_tgt, state.position.get(self.TARGET, 0), next_target, self.POSITION_LIMIT, self.MAX_ORDER_SIZE)
        if orders:
            result[self.TARGET] = orders
        history.append(residual)
        if len(history) > self.HISTORY_LIMIT:
            del history[:len(history) - self.HISTORY_LIMIT]
        return next_target


_translator_module = _TranslatorModule()
_microchip_module = _MicrochipModule()
_microchip_rect_module = _MicrochipRectModule()

# ─────────────────────────── Oxygen Shake helpers ───────────────────────────

def _update_ema(prev: Optional[float], value: float, alpha: float) -> float:
    if prev is None:
        return value
    return alpha * value + (1.0 - alpha) * prev


def _get_mid(depth) -> Optional[float]:
    if not depth or not depth.buy_orders or not depth.sell_orders:
        return None
    return (max(depth.buy_orders) + min(depth.sell_orders)) / 2.0


def _popular_mid(depth) -> Optional[float]:
    if not depth or not depth.buy_orders or not depth.sell_orders:
        return None
    pop_bid = max(depth.buy_orders, key=lambda p: depth.buy_orders[p])
    pop_ask = max(depth.sell_orders, key=lambda p: -depth.sell_orders[p])
    return (pop_bid + pop_ask) / 2.0


def _passive_buy(symbol: str, depth, size: int) -> Optional[Order]:
    if size <= 0 or not depth.buy_orders or not depth.sell_orders:
        return None
    price = max(depth.buy_orders) + 1
    if price >= min(depth.sell_orders):
        return None
    return Order(symbol, price, size)


def _passive_sell(symbol: str, depth, size: int) -> Optional[Order]:
    if size <= 0 or not depth.buy_orders or not depth.sell_orders:
        return None
    price = min(depth.sell_orders) - 1
    if price <= max(depth.buy_orders):
        return None
    return Order(symbol, price, -size)


def _apply_skew(price: int, pos: int, K: float) -> int:
    return int(price - K * pos)


def _trend_regime(fast: float, slow: float, prev_regime: str, buffer: float) -> str:
    gap = fast - slow
    if gap > buffer:
        return "long"
    if gap < -buffer:
        return "short"
    return prev_regime


def _regime_mode(abs_gap: float, prev_mode: str, threshold: float, buffer: float) -> str:
    if abs_gap > threshold + buffer:
        return "trend"
    if abs_gap < threshold - buffer:
        return "mm"
    return prev_mode


def _mm_with_take(state: TradingState, cfg: dict) -> List[Order]:
    sym = cfg["symbol"]
    depth = state.order_depths.get(sym)
    if not depth or not depth.buy_orders or not depth.sell_orders:
        return []
    fair = _popular_mid(depth)
    if fair is None:
        return []
    best_bid = max(depth.buy_orders)
    best_ask = min(depth.sell_orders)
    pos = state.position.get(sym, 0)
    size = cfg["size"]
    limit = cfg["limit"]
    take_margin = cfg["take_margin"]
    orders: List[Order] = []
    eff_pos = pos
    if eff_pos < 0 and best_ask <= fair:
        ask_vol = -depth.sell_orders[best_ask]
        take_qty = min(ask_vol, -eff_pos)
        if take_qty > 0:
            orders.append(Order(sym, best_ask, take_qty))
            eff_pos += take_qty
    elif eff_pos >= 0 and best_ask < fair - take_margin and eff_pos < limit:
        ask_vol = -depth.sell_orders[best_ask]
        take_qty = min(ask_vol, limit - eff_pos)
        if take_qty > 0:
            orders.append(Order(sym, best_ask, take_qty))
            eff_pos += take_qty
    if eff_pos > 0 and best_bid >= fair:
        bid_vol = depth.buy_orders[best_bid]
        take_qty = min(bid_vol, eff_pos)
        if take_qty > 0:
            orders.append(Order(sym, best_bid, -take_qty))
            eff_pos -= take_qty
    elif eff_pos <= 0 and best_bid > fair + take_margin and eff_pos > -limit:
        bid_vol = depth.buy_orders[best_bid]
        take_qty = min(bid_vol, limit + eff_pos)
        if take_qty > 0:
            orders.append(Order(sym, best_bid, -take_qty))
            eff_pos -= take_qty
    K = cfg.get("skew_k", 0)
    bid_quote = _apply_skew(min(best_bid + 1, math.floor(fair)), eff_pos, K)
    ask_quote = _apply_skew(max(best_ask - 1, math.ceil(fair)), eff_pos, K)
    if eff_pos < limit and bid_quote < best_ask:
        buy_size = min(size, limit - eff_pos)
        if buy_size > 0:
            orders.append(Order(sym, bid_quote, buy_size))
    if eff_pos > -limit and ask_quote > best_bid:
        sell_size = min(size, limit + eff_pos)
        if sell_size > 0:
            orders.append(Order(sym, ask_quote, -sell_size))
    return orders


# ─────────────────────────── Oxygen Shake configs ───────────────────────────

_GARLIC_CFG = {
    "symbol": "OXYGEN_SHAKE_GARLIC",
    "limit": 10,
    "alpha_fast": 0.1,
    "alpha_slow": 0.01,
    "warmup": 70000,
    "trend_threshold": 15,
    "mode_buffer": 5,
}
_GARLIC_MM_CFG = {
    "symbol": "OXYGEN_SHAKE_GARLIC",
    "limit": 10,
    "size": 5,
    "take_margin": 1,
    "skew_k": -1.0,
}
_MORNING_BREATH_CFG = {
    "symbol": "OXYGEN_SHAKE_MORNING_BREATH",
    "limit": 10,
    "alpha_fast": 0.1,
    "alpha_slow": 0.01,
    "warmup": 50000,
    "dir_buffer": 5,
    "trend_threshold": 20,
    "mode_buffer": 10,
}
_MORNING_BREATH_MM_CFG = {
    "symbol": "OXYGEN_SHAKE_MORNING_BREATH",
    "limit": 10,
    "size": 5,
    "take_margin": 1,
    "skew_k": 0.0,
}
_EVENING_BREATH_CFG = {
    "symbol": "OXYGEN_SHAKE_EVENING_BREATH",
    "limit": 10,
    "alpha_fast": 0.1,
    "alpha_slow": 0.01,
    "warmup": 50000,
    "dir_buffer": 5,
    "trend_threshold": 20,
    "mode_buffer": 10,
}
_EVENING_BREATH_MM_CFG = {
    "symbol": "OXYGEN_SHAKE_EVENING_BREATH",
    "limit": 10,
    "size": 10,
    "take_margin": 1,
    "skew_k": 0.5,
}
_OXYGEN_BASKET_CFG = {
    "signal_symbols": [
        "OXYGEN_SHAKE_MORNING_BREATH",
        "OXYGEN_SHAKE_EVENING_BREATH",
        "OXYGEN_SHAKE_MINT",
        "OXYGEN_SHAKE_CHOCOLATE",
    ],
    "trade_symbols": ["OXYGEN_SHAKE_CHOCOLATE"],
    "fv": 39000,
    "entry_threshold": 800,
    "reduce_buffer": 0,
    "limit": 10,
}


# ─────────────────────────── Galaxy Sounds strategies (trader_test) ───────────────────────────

_BLACK_HOLES_CFG = {
    "symbol": "GALAXY_SOUNDS_BLACK_HOLES",
    "limit": 10,
    "alpha_fast": 0.05,
    "alpha_slow": 0.005,
    "warmup": 50000,
}
_PLANETARY_RINGS_CFG = {
    "symbol": "GALAXY_SOUNDS_PLANETARY_RINGS",
    "limit": 10,
    "alpha_fast": 0.1,
    "alpha_slow": 0.01,
    "warmup": 50000,
    "dir_buffer": 5,
    "trend_threshold": 30,
    "mode_buffer": 10,
}
_PR_MM_CFG = {
    "symbol": "GALAXY_SOUNDS_PLANETARY_RINGS",
    "limit": 10,
    "size": 10,
    "take_margin": 1,
    "skew_k": 0.0,
}


def _trade_black_holes(state: TradingState, saved: dict) -> List[Order]:
    cfg = _BLACK_HOLES_CFG
    sym = cfg["symbol"]
    depth = state.order_depths.get(sym)
    mid = _get_mid(depth)
    if mid is None:
        return []
    s = saved.setdefault("bh", {})
    s["f"] = _update_ema(s.get("f"), mid, cfg["alpha_fast"])
    s["s"] = _update_ema(s.get("s"), mid, cfg["alpha_slow"])
    if state.timestamp < cfg["warmup"]:
        return []
    pos = state.position.get(sym, 0)
    if s["f"] > s["s"]:
        o = _passive_buy(sym, depth, cfg["limit"] - pos)
        return [o] if o else []
    elif s["f"] < s["s"]:
        o = _passive_sell(sym, depth, max(0, pos))
        return [o] if o else []
    return []


def _trade_planetary_rings(state: TradingState, saved: dict) -> List[Order]:
    cfg = _PLANETARY_RINGS_CFG
    sym = cfg["symbol"]
    depth = state.order_depths.get(sym)
    mid = _get_mid(depth)
    if mid is None:
        return []
    s = saved.setdefault("pr", {})
    s["f"] = _update_ema(s.get("f"), mid, cfg["alpha_fast"])
    s["s"] = _update_ema(s.get("s"), mid, cfg["alpha_slow"])
    if state.timestamp < cfg["warmup"]:
        return []
    gap = s["f"] - s["s"]
    abs_gap = abs(gap)
    mode = _regime_mode(abs_gap, s.get("mode", "mm"), cfg["trend_threshold"], cfg["mode_buffer"])
    s["mode"] = mode
    if mode == "trend":
        direction = _trend_regime(s["f"], s["s"], s.get("dir", "flat"), cfg["dir_buffer"])
        s["dir"] = direction
        pos = state.position.get(sym, 0)
        if direction == "long":
            o = _passive_buy(sym, depth, cfg["limit"] - pos)
            return [o] if o else []
        elif direction == "short":
            o = _passive_sell(sym, depth, cfg["limit"] + pos)
            return [o] if o else []
        return []
    return _mm_with_take(state, _PR_MM_CFG)


# ─────────────────────────── Oxygen Shake strategies ───────────────────────────

def _trade_garlic(state: TradingState, saved: dict) -> List[Order]:
    cfg = _GARLIC_CFG
    sym = cfg["symbol"]
    depth = state.order_depths.get(sym)
    mid = _get_mid(depth)
    if mid is None:
        return []
    s = saved.setdefault("garlic", {})
    s["f"] = _update_ema(s.get("f"), mid, cfg["alpha_fast"])
    s["s"] = _update_ema(s.get("s"), mid, cfg["alpha_slow"])
    if state.timestamp < cfg["warmup"]:
        return []
    gap = s["f"] - s["s"]
    abs_gap = abs(gap)
    mode = _regime_mode(abs_gap, s.get("mode", "mm"), cfg["trend_threshold"], cfg["mode_buffer"])
    s["mode"] = mode
    if mode == "trend":
        pos = state.position.get(sym, 0)
        if s["f"] > s["s"]:
            o = _passive_buy(sym, depth, cfg["limit"] - pos)
            return [o] if o else []
        else:
            o = _passive_sell(sym, depth, max(0, pos))
            return [o] if o else []
    return _mm_with_take(state, _GARLIC_MM_CFG)


def _trade_morning_breath(state: TradingState, saved: dict) -> List[Order]:
    cfg = _MORNING_BREATH_CFG
    sym = cfg["symbol"]
    depth = state.order_depths.get(sym)
    mid = _get_mid(depth)
    if mid is None:
        return []
    s = saved.setdefault("mb", {})
    s["f"] = _update_ema(s.get("f"), mid, cfg["alpha_fast"])
    s["s"] = _update_ema(s.get("s"), mid, cfg["alpha_slow"])
    if state.timestamp < cfg["warmup"]:
        return []
    gap = s["f"] - s["s"]
    abs_gap = abs(gap)
    mode = _regime_mode(abs_gap, s.get("mode", "mm"), cfg["trend_threshold"], cfg["mode_buffer"])
    s["mode"] = mode
    if mode == "trend":
        direction = _trend_regime(s["f"], s["s"], s.get("dir", "flat"), cfg["dir_buffer"])
        s["dir"] = direction
        pos = state.position.get(sym, 0)
        if direction == "long":
            o = _passive_buy(sym, depth, cfg["limit"] - pos)
            return [o] if o else []
        elif direction == "short":
            o = _passive_sell(sym, depth, cfg["limit"] + pos)
            return [o] if o else []
        return []
    return _mm_with_take(state, _MORNING_BREATH_MM_CFG)


def _trade_evening_breath(state: TradingState, saved: dict) -> List[Order]:
    cfg = _EVENING_BREATH_CFG
    sym = cfg["symbol"]
    depth = state.order_depths.get(sym)
    mid = _get_mid(depth)
    if mid is None:
        return []
    s = saved.setdefault("eb", {})
    s["f"] = _update_ema(s.get("f"), mid, cfg["alpha_fast"])
    s["s"] = _update_ema(s.get("s"), mid, cfg["alpha_slow"])
    if state.timestamp < cfg["warmup"]:
        return []
    gap = s["f"] - s["s"]
    abs_gap = abs(gap)
    mode = _regime_mode(abs_gap, s.get("mode", "mm"), cfg["trend_threshold"], cfg["mode_buffer"])
    s["mode"] = mode
    if mode == "trend":
        direction = _trend_regime(s["f"], s["s"], s.get("dir", "flat"), cfg["dir_buffer"])
        s["dir"] = direction
        pos = state.position.get(sym, 0)
        if direction == "long":
            o = _passive_buy(sym, depth, cfg["limit"] - pos)
            return [o] if o else []
        elif direction == "short":
            o = _passive_sell(sym, depth, cfg["limit"] + pos)
            return [o] if o else []
        return []
    return _mm_with_take(state, _EVENING_BREATH_MM_CFG)


def _trade_oxygen_basket(state: TradingState, saved: dict) -> List[Order]:
    cfg = _OXYGEN_BASKET_CFG
    mids = {}
    for sym in cfg["signal_symbols"]:
        depth = state.order_depths.get(sym)
        m = _get_mid(depth)
        if m is None:
            return []
        mids[sym] = m
    basket_sum = sum(mids.values())
    dev = basket_sum - cfg["fv"]
    entry = cfg["entry_threshold"]
    reduce_buf = cfg["reduce_buffer"]
    limit = cfg["limit"]
    orders: List[Order] = []
    if dev > entry:
        for sym in cfg["trade_symbols"]:
            depth = state.order_depths[sym]
            pos = state.position.get(sym, 0)
            o = _passive_sell(sym, depth, limit + pos)
            if o:
                orders.append(o)
    elif dev < -entry:
        for sym in cfg["trade_symbols"]:
            depth = state.order_depths[sym]
            pos = state.position.get(sym, 0)
            o = _passive_buy(sym, depth, limit - pos)
            if o:
                orders.append(o)
    elif abs(dev) <= reduce_buf:
        for sym in cfg["trade_symbols"]:
            depth = state.order_depths[sym]
            pos = state.position.get(sym, 0)
            if pos > 0:
                o = _passive_sell(sym, depth, pos)
                if o:
                    orders.append(o)
            elif pos < 0:
                o = _passive_buy(sym, depth, -pos)
                if o:
                    orders.append(o)
    return orders


class Trader:
    def bid(self, state=None) -> int:
        return 0

    def run(self, state: TradingState):
        histories = self._load_histories(state.traderData)
        result: Dict[str, List[Order]] = {}
        fair_value = self._snackpack_mean(state)

        for product in SNACKPACK_TRADES:
            order_depth = state.order_depths.get(product)
            if fair_value is None or order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                result[product] = []
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mid = (best_bid + best_ask) / 2.0

            history = histories.setdefault(product, [])
            history.append(mid)
            if len(history) > HISTORY_LIMIT:
                histories[product] = history[-HISTORY_LIMIT:]
                history = histories[product]

            position = state.position.get(product, 0)
            orders: List[Order] = []
            buy_room = POSITION_LIMIT - position
            sell_room = POSITION_LIMIT + position

            product_fair = fair_value + PRODUCT_OFFSETS.get(product, 0)

            if position > 0 and mid >= product_fair + EXIT_THRESHOLD and sell_room > 0:
                quantity = min(ORDER_SIZE, sell_room, position)
                orders.append(Order(product, best_bid, -quantity))
                sell_room -= quantity

            if position < 0 and mid <= product_fair - EXIT_THRESHOLD and buy_room > 0:
                quantity = min(ORDER_SIZE, buy_room, -position)
                orders.append(Order(product, best_ask, quantity))
                buy_room -= quantity

            if mid <= product_fair - ENTRY_THRESHOLD and buy_room > 0:
                quantity = min(ORDER_SIZE, buy_room)
                orders.append(Order(product, best_ask, quantity))
                buy_room -= quantity

            if mid >= product_fair + ENTRY_THRESHOLD and sell_room > 0:
                quantity = min(ORDER_SIZE, sell_room)
                orders.append(Order(product, best_bid, -quantity))
                sell_room -= quantity

            result[product] = orders

        result.update(self._trade_pebbles_pair(state))
        result.update(self._trade_pebbles_ms_pair(state))
        result.update(self._trade_snackpack_pair(state))
        result.update(self._trade_chocolate_signal(state))
        result.update(self._trade_translator_cluster(state))
        result.update(self._trade_panel_cluster(state))
        result.update(self._trade_panel44_cluster(state))
        result.update(self._trade_panel_1x_sum(state, histories))
        result.update(self._trade_uv_ao_pair(state))
        result.update(self._trade_iron_peb_pair(state))
        result.update(self._trade_pebbles_l_meanrev(state))
        result.update(self._trade_chip_ct_pair(state))
        result.update(self._trade_robot_ld_pair(state, histories))
        result.update(self._trade_robot_md_pair(state, histories))
        result.update(self._trade_suede_cotton(state))
        result.update(self._trade_nylon_chocolate_signal(state, histories))
        result.update(self._trade_polyester_mm(state, histories))
        result.update(self._trade_uv_rm(state))
        result.update(self._trade_uv_yo(state))
        result.update(self._trade_uv_amber(state))
        result.update(self._trade_translator_eclipse_avg(state))
        result.update(self._trade_translator_void_basket(state))
        result.update(self._trade_galaxy_dm_pr(state))
        result.update(self._trade_galaxy_sw_dm(state))
        # ── New strategies for previously zero-profit products ──
        result.update(self._trade_robot_vacuuming(state, histories))
        result.update(self._trade_solar_flames(state))
        result.update(self._trade_lamb_wool(state))
        result.update(self._trade_mint(state))
        result.update(self._trade_uv_yellow(state))
        result.update(self._trade_microchip_square(state))
        result.update(self._trade_panel_2x4(state))
        result.update(self._trade_panel_1x4(state))

        t_saved = histories.setdefault("_t", {})
        for fn in [_trade_black_holes, _trade_planetary_rings, _trade_garlic, _trade_morning_breath, _trade_evening_breath, _trade_oxygen_basket]:
            for o in fn(state, t_saved):
                result.setdefault(o.symbol, []).append(o)

        t2 = histories.setdefault("_t2", {})
        tr_hist, tr_tgt = _translator_module.load_state(t2.get("tr", {}))
        next_tr_tgt = _translator_module.run(state, tr_hist, tr_tgt, ("TRANSLATOR_ASTRO_BLACK", "TRANSLATOR_GRAPHITE_MIST"), result)
        t2["tr"] = _translator_module.dump_state(tr_hist, next_tr_tgt)

        mc_hist, mc_tgt = _microchip_module.load_state(t2.get("mc", {}))
        next_mc_tgt = _microchip_module.run(state, mc_hist, mc_tgt, result)
        t2["mc"] = _microchip_module.dump_state(mc_hist, next_mc_tgt)

        mcr_hist, mcr_tgt = _microchip_rect_module.load_state(t2.get("mcr", {}))
        next_mcr_tgt = _microchip_rect_module.run(state, mcr_hist, mcr_tgt, result)
        t2["mcr"] = _microchip_rect_module.dump_state(mcr_hist, next_mcr_tgt)

        result.update(self._trade_xs_rect_pair(state, histories))

        trader_data = json.dumps(histories, separators=(",", ":"))
        conversions = 0
        return result, conversions, trader_data

    def _trade_uv_amber(self, state: TradingState) -> Dict[str, List[Order]]:
        group_mids: List[float] = []
        for product in UV_AMBER_OTHERS:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {"UV_VISOR_AMBER": []}
            group_mids.append((max(od.buy_orders) + min(od.sell_orders)) / 2.0)
        group_mean = sum(group_mids) / len(group_mids)

        od = state.order_depths.get("UV_VISOR_AMBER")
        if od is None or not od.buy_orders or not od.sell_orders:
            return {"UV_VISOR_AMBER": []}
        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        amber_mid = (best_bid + best_ask) / 2.0
        amber_sum = amber_mid + group_mean

        position = state.position.get("UV_VISOR_AMBER", 0)
        buy_room  = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if position > 0 and abs(amber_sum - UV_AMBER_FAIR) <= UV_AMBER_EXIT and sell_room > 0:
            orders.append(Order("UV_VISOR_AMBER", best_bid, -min(sell_room, position)))
        elif position < 0 and abs(amber_sum - UV_AMBER_FAIR) <= UV_AMBER_EXIT and buy_room > 0:
            orders.append(Order("UV_VISOR_AMBER", best_ask, min(buy_room, -position)))

        if amber_sum <= UV_AMBER_FAIR - UV_AMBER_ENTRY and buy_room > 0:
            orders.append(Order("UV_VISOR_AMBER", best_ask, buy_room))
        elif amber_sum >= UV_AMBER_FAIR + UV_AMBER_ENTRY and sell_room > 0:
            orders.append(Order("UV_VISOR_AMBER", best_bid, -sell_room))

        return {"UV_VISOR_AMBER": orders}

    def _trade_translator_eclipse_avg(self, state: TradingState) -> Dict[str, List[Order]]:
        mids: List[float] = []
        for product in TRANSLATOR_AVG_PRODUCTS:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {TRANSLATOR_ECLIPSE_TARGET: []}
            mids.append((max(od.buy_orders) + min(od.sell_orders)) / 2.0)

        od = state.order_depths.get(TRANSLATOR_ECLIPSE_TARGET)
        if od is None or not od.buy_orders or not od.sell_orders:
            return {TRANSLATOR_ECLIPSE_TARGET: []}

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        mid = (best_bid + best_ask) / 2.0
        deviation = mid - (sum(mids) / len(mids))

        position = state.position.get(TRANSLATOR_ECLIPSE_TARGET, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if position > 0 and abs(deviation) <= TRANSLATOR_ECLIPSE_AVG_EXIT and sell_room > 0:
            quantity = min(TRANSLATOR_ECLIPSE_AVG_SIZE, sell_room, position)
            orders.append(Order(TRANSLATOR_ECLIPSE_TARGET, best_bid, -quantity))
            sell_room -= quantity
        elif position < 0 and abs(deviation) <= TRANSLATOR_ECLIPSE_AVG_EXIT and buy_room > 0:
            quantity = min(TRANSLATOR_ECLIPSE_AVG_SIZE, buy_room, -position)
            orders.append(Order(TRANSLATOR_ECLIPSE_TARGET, best_ask, quantity))
            buy_room -= quantity

        if deviation > TRANSLATOR_ECLIPSE_AVG_ENTRY and sell_room > 0:
            quantity = min(TRANSLATOR_ECLIPSE_AVG_SIZE, sell_room)
            orders.append(Order(TRANSLATOR_ECLIPSE_TARGET, best_bid, -quantity))
        elif deviation < -TRANSLATOR_ECLIPSE_AVG_ENTRY and buy_room > 0:
            quantity = min(TRANSLATOR_ECLIPSE_AVG_SIZE, buy_room)
            orders.append(Order(TRANSLATOR_ECLIPSE_TARGET, best_ask, quantity))

        return {TRANSLATOR_ECLIPSE_TARGET: orders}

    def _trade_translator_void_basket(self, state: TradingState) -> Dict[str, List[Order]]:
        mids: List[float] = []
        for product in TRANSLATOR_VOID_SIGNAL_PRODUCTS:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {TRANSLATOR_VOID_TARGET: []}
            mids.append((max(od.buy_orders) + min(od.sell_orders)) / 2.0)

        od = state.order_depths.get(TRANSLATOR_VOID_TARGET)
        if od is None or not od.buy_orders or not od.sell_orders:
            return {TRANSLATOR_VOID_TARGET: []}

        basket_sum = sum(mids)
        dev = basket_sum - TRANSLATOR_VOID_FV

        position = state.position.get(TRANSLATOR_VOID_TARGET, 0)
        orders: List[Order] = []

        if dev > TRANSLATOR_VOID_ENTRY:
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            price = best_ask - 1
            if price > best_bid:
                size = POSITION_LIMIT + position
                if size > 0:
                    orders.append(Order(TRANSLATOR_VOID_TARGET, price, -size))
        elif dev < -TRANSLATOR_VOID_ENTRY:
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            price = best_bid + 1
            if price < best_ask:
                size = POSITION_LIMIT - position
                if size > 0:
                    orders.append(Order(TRANSLATOR_VOID_TARGET, price, size))
        elif abs(dev) <= TRANSLATOR_VOID_EXIT:
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            if position > 0:
                price = best_ask - 1
                if price > best_bid:
                    orders.append(Order(TRANSLATOR_VOID_TARGET, price, -position))
            elif position < 0:
                price = best_bid + 1
                if price < best_ask:
                    orders.append(Order(TRANSLATOR_VOID_TARGET, price, -position))

        return {TRANSLATOR_VOID_TARGET: orders}

    def _trade_uv_yo(self, state: TradingState) -> Dict[str, List[Order]]:
        sig_od = state.order_depths.get(UV_YO_SIGNAL)
        tgt_od = state.order_depths.get(UV_YO_TARGET)
        if not sig_od or not tgt_od or not sig_od.buy_orders or not sig_od.sell_orders or not tgt_od.buy_orders or not tgt_od.sell_orders:
            return {UV_YO_TARGET: []}

        sig_mid = (max(sig_od.buy_orders) + min(sig_od.sell_orders)) / 2.0
        tgt_bid = max(tgt_od.buy_orders)
        tgt_ask = min(tgt_od.sell_orders)
        tgt_mid = (tgt_bid + tgt_ask) / 2.0

        pair_mean = (sig_mid + tgt_mid) / 2.0
        yel_dev = sig_mid - pair_mean  # positive = yellow expensive, orange cheap

        position = state.position.get(UV_YO_TARGET, 0)
        buy_room  = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if position > 0 and abs(yel_dev) <= UV_YO_EXIT and sell_room > 0:
            orders.append(Order(UV_YO_TARGET, tgt_bid, -min(sell_room, position)))
        elif position < 0 and abs(yel_dev) <= UV_YO_EXIT and buy_room > 0:
            orders.append(Order(UV_YO_TARGET, tgt_ask, min(buy_room, -position)))

        if yel_dev < -UV_YO_ENTRY and sell_room > 0:
            orders.append(Order(UV_YO_TARGET, tgt_bid, -sell_room))
        elif yel_dev > UV_YO_ENTRY and buy_room > 0:
            orders.append(Order(UV_YO_TARGET, tgt_ask, buy_room))

        return {UV_YO_TARGET: orders}

    def _trade_uv_rm(self, state: TradingState) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in UV_RM_TRADES:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {p: [] for p in UV_RM_TRADES}
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        red, mag = UV_RM_TRADES
        pair_mean = (mids[red] + mids[mag]) / 2.0
        red_dev = mids[red] - pair_mean

        result: Dict[str, List[Order]] = {}
        for product in UV_RM_TRADES:
            best_bid, best_ask = depths[product]
            position = state.position.get(product, 0)
            buy_room = POSITION_LIMIT - position
            sell_room = POSITION_LIMIT + position
            orders: List[Order] = []
            is_red = product == red

            if position > 0 and abs(red_dev) <= UV_RM_EXIT and sell_room > 0:
                orders.append(Order(product, best_bid, -min(sell_room, position)))
            elif position < 0 and abs(red_dev) <= UV_RM_EXIT and buy_room > 0:
                orders.append(Order(product, best_ask, min(buy_room, -position)))

            if red_dev > UV_RM_ENTRY:
                if is_red and sell_room > 0:
                    orders.append(Order(product, best_bid, -sell_room))
                elif not is_red and buy_room > 0:
                    orders.append(Order(product, best_ask, buy_room))
            elif red_dev < -UV_RM_ENTRY:
                if is_red and buy_room > 0:
                    orders.append(Order(product, best_ask, buy_room))
                elif not is_red and sell_room > 0:
                    orders.append(Order(product, best_bid, -sell_room))

            result[product] = orders
        return result

    def _trade_nylon_chocolate_signal(self, state: TradingState, histories: dict) -> Dict[str, List[Order]]:
        nylon_od = state.order_depths.get(NYLON_CHOCOLATE_TARGET)
        chocolate_od = state.order_depths.get(NYLON_CHOCOLATE_SIGNAL)
        if (
            nylon_od is None
            or chocolate_od is None
            or not nylon_od.buy_orders
            or not nylon_od.sell_orders
            or not chocolate_od.buy_orders
            or not chocolate_od.sell_orders
        ):
            return {NYLON_CHOCOLATE_TARGET: []}

        nylon_bid = max(nylon_od.buy_orders)
        nylon_ask = min(nylon_od.sell_orders)
        nylon_mid = (nylon_bid + nylon_ask) / 2.0
        chocolate_mid = (max(chocolate_od.buy_orders) + min(chocolate_od.sell_orders)) / 2.0
        spread = nylon_mid - chocolate_mid

        history = histories.setdefault(NYLON_CHOCOLATE_HISTORY_KEY, [])
        history.append(spread)
        if len(history) > NYLON_CHOCOLATE_HISTORY_LIMIT:
            histories[NYLON_CHOCOLATE_HISTORY_KEY] = history[-NYLON_CHOCOLATE_HISTORY_LIMIT:]
            history = histories[NYLON_CHOCOLATE_HISTORY_KEY]

        if len(history) < NYLON_CHOCOLATE_WARMUP:
            return {NYLON_CHOCOLATE_TARGET: []}

        mean = sum(history) / len(history)
        variance = sum((value - mean) ** 2 for value in history) / max(1, len(history) - 1)
        stdev = variance ** 0.5
        if stdev < 1:
            return {NYLON_CHOCOLATE_TARGET: []}

        z = (spread - mean) / stdev
        position = state.position.get(NYLON_CHOCOLATE_TARGET, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if abs(z) <= NYLON_CHOCOLATE_EXIT_Z:
            if position > 0 and sell_room > 0:
                quantity = min(NYLON_CHOCOLATE_SIZE, sell_room, position)
                orders.append(Order(NYLON_CHOCOLATE_TARGET, nylon_bid, -quantity))
                sell_room -= quantity
            elif position < 0 and buy_room > 0:
                quantity = min(NYLON_CHOCOLATE_SIZE, buy_room, -position)
                orders.append(Order(NYLON_CHOCOLATE_TARGET, nylon_ask, quantity))
                buy_room -= quantity

        if z <= -NYLON_CHOCOLATE_ENTRY_Z and buy_room > 0:
            quantity = min(NYLON_CHOCOLATE_SIZE, buy_room)
            orders.append(Order(NYLON_CHOCOLATE_TARGET, nylon_ask, quantity))
        elif z >= NYLON_CHOCOLATE_ENTRY_Z and sell_room > 0:
            quantity = min(NYLON_CHOCOLATE_SIZE, sell_room)
            orders.append(Order(NYLON_CHOCOLATE_TARGET, nylon_bid, -quantity))

        return {NYLON_CHOCOLATE_TARGET: orders}

    def _trade_polyester_mm(self, state: TradingState, histories: dict) -> Dict[str, List[Order]]:
        product = "SLEEP_POD_POLYESTER"
        leader = "GALAXY_SOUNDS_BLACK_HOLES"
        LOOKBACK = 100
        ENTRY_THRESH = 20
        EXIT_THRESH = 10
        MAX_HOLD = 500
        SIZE = 10

        od_lag = state.order_depths.get(product)
        od_ldr = state.order_depths.get(leader)
        if not od_lag or not od_lag.buy_orders or not od_lag.sell_orders:
            return {product: []}
        if not od_ldr or not od_ldr.buy_orders or not od_ldr.sell_orders:
            return {product: []}

        lag_mid = (max(od_lag.buy_orders) + min(od_lag.sell_orders)) / 2.0
        ldr_mid = (max(od_ldr.buy_orders) + min(od_ldr.sell_orders)) / 2.0

        bh_hist = histories.setdefault("poly_bh", [])
        bh_hist.append(ldr_mid)
        if len(bh_hist) > LOOKBACK + 1:
            del bh_hist[:len(bh_hist) - (LOOKBACK + 1)]

        s = histories.setdefault("poly_ll", {"pos": 0, "entry": None, "hold": 0})
        pos = state.position.get(product, 0)
        orders: List[Order] = []

        if len(bh_hist) < LOOKBACK + 1:
            return {product: []}

        ldr_move = ldr_mid - bh_hist[0]
        s_pos = s["pos"]

        if s_pos != 0 and s["entry"] is not None:
            s["hold"] += 1
            lag_move = lag_mid - s["entry"]
            take_profit = (s_pos > 0 and lag_move >= EXIT_THRESH) or (s_pos < 0 and lag_move <= -EXIT_THRESH)
            if s["hold"] >= MAX_HOLD or take_profit:
                if s_pos > 0 and pos > 0:
                    qty = min(pos, s_pos)
                    orders.append(Order(product, max(od_lag.buy_orders), -qty))
                elif s_pos < 0 and pos < 0:
                    qty = min(-pos, -s_pos)
                    orders.append(Order(product, min(od_lag.sell_orders), qty))
                s["pos"] = 0
                s["entry"] = None
                s["hold"] = 0
                return {product: orders}

        if s_pos == 0:
            if ldr_move > ENTRY_THRESH and pos < SIZE:
                room = SIZE - pos
                orders.append(Order(product, min(od_lag.sell_orders), room))
                s["pos"] = SIZE
                s["entry"] = lag_mid
                s["hold"] = 0
            elif ldr_move < -ENTRY_THRESH and pos > -SIZE:
                room = SIZE + pos
                orders.append(Order(product, max(od_lag.buy_orders), -room))
                s["pos"] = -SIZE
                s["entry"] = lag_mid
                s["hold"] = 0

        return {product: orders}

    def _trade_suede_cotton(self, state: TradingState) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in SUEDE_COTTON_TRADES:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {p: [] for p in SUEDE_COTTON_TRADES}
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        suede, cotton = SUEDE_COTTON_TRADES
        pair_mean = (mids[suede] + mids[cotton]) / 2.0
        suede_dev = mids[suede] - pair_mean  # positive = suede expensive

        result: Dict[str, List[Order]] = {}
        for product in SUEDE_COTTON_TRADES:
            best_bid, best_ask = depths[product]
            position = state.position.get(product, 0)
            buy_room = POSITION_LIMIT - position
            sell_room = POSITION_LIMIT + position
            orders: List[Order] = []
            is_suede = product == suede

            if position > 0 and abs(suede_dev) <= SUEDE_COTTON_EXIT and sell_room > 0:
                orders.append(Order(product, best_bid, -min(sell_room, position)))
            elif position < 0 and abs(suede_dev) <= SUEDE_COTTON_EXIT and buy_room > 0:
                orders.append(Order(product, best_ask, min(buy_room, -position)))

            if suede_dev > SUEDE_COTTON_ENTRY:
                if is_suede and sell_room > 0:
                    orders.append(Order(product, best_bid, -sell_room))
                elif not is_suede and buy_room > 0:
                    orders.append(Order(product, best_ask, buy_room))
            elif suede_dev < -SUEDE_COTTON_ENTRY:
                if is_suede and buy_room > 0:
                    orders.append(Order(product, best_ask, buy_room))
                elif not is_suede and sell_room > 0:
                    orders.append(Order(product, best_bid, -sell_room))

            result[product] = orders
        return result

    def _trade_robot_ld_pair(self, state: TradingState, histories: dict) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in ROBOT_LD_TRADES:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {p: [] for p in ROBOT_LD_TRADES}
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        pair_sum = mids[ROBOT_LD_TRADES[0]] + mids[ROBOT_LD_TRADES[1]]
        history = histories.setdefault(ROBOT_LD_HISTORY_KEY, [])
        history.append(pair_sum)
        if len(history) > ROBOT_LD_HISTORY_LIMIT:
            histories[ROBOT_LD_HISTORY_KEY] = history[-ROBOT_LD_HISTORY_LIMIT:]
            history = histories[ROBOT_LD_HISTORY_KEY]

        if len(history) < ROBOT_LD_WARMUP:
            return {p: [] for p in ROBOT_LD_TRADES}

        window = history[-ROBOT_LD_WARMUP:]
        mean = sum(window) / len(window)
        variance = sum((value - mean) ** 2 for value in window) / max(1, len(window) - 1)
        stdev = variance ** 0.5
        if stdev < 0.1:
            return {p: [] for p in ROBOT_LD_TRADES}

        z = (pair_sum - mean) / stdev
        result: Dict[str, List[Order]] = {}

        for product in ROBOT_LD_TRADES:
            best_bid, best_ask = depths[product]
            position = state.position.get(product, 0)
            buy_room = POSITION_LIMIT - position
            sell_room = POSITION_LIMIT + position
            orders: List[Order] = []

            if abs(z) <= ROBOT_LD_EXIT_Z and position != 0:
                if position > 0 and sell_room > 0:
                    quantity = min(ROBOT_LD_ORDER_SIZE, sell_room, position)
                    orders.append(Order(product, best_bid, -quantity))
                elif position < 0 and buy_room > 0:
                    quantity = min(ROBOT_LD_ORDER_SIZE, buy_room, -position)
                    orders.append(Order(product, best_ask, quantity))
            elif z >= ROBOT_LD_ENTRY_Z and sell_room > 0:
                quantity = min(ROBOT_LD_ORDER_SIZE, sell_room)
                orders.append(Order(product, best_bid, -quantity))
            elif z <= -ROBOT_LD_ENTRY_Z and buy_room > 0:
                quantity = min(ROBOT_LD_ORDER_SIZE, buy_room)
                orders.append(Order(product, best_ask, quantity))

            result[product] = orders

        return result

    def _trade_robot_md_pair(self, state: TradingState, histories: dict) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in ROBOT_MD_TRADES:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {ROBOT_MD_TRADES[0]: []}
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        pair_sum = mids[ROBOT_MD_TRADES[0]] + mids[ROBOT_MD_TRADES[1]]
        history = histories.setdefault(ROBOT_MD_HISTORY_KEY, [])
        history.append(pair_sum)
        if len(history) > ROBOT_MD_HISTORY_LIMIT:
            histories[ROBOT_MD_HISTORY_KEY] = history[-ROBOT_MD_HISTORY_LIMIT:]
            history = histories[ROBOT_MD_HISTORY_KEY]

        if len(history) < ROBOT_MD_WARMUP:
            return {ROBOT_MD_TRADES[0]: []}

        mean = sum(history) / len(history)
        variance = sum((value - mean) ** 2 for value in history) / max(1, len(history) - 1)
        stdev = variance ** 0.5
        if stdev < 1:
            return {ROBOT_MD_TRADES[0]: []}

        z = (pair_sum - mean) / stdev
        product = ROBOT_MD_TRADES[0]
        best_bid, best_ask = depths[product]
        position = state.position.get(product, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if abs(z) <= ROBOT_MD_EXIT_Z:
            if position > 0 and sell_room > 0:
                quantity = min(ROBOT_MD_ORDER_SIZE, sell_room, position)
                orders.append(Order(product, best_bid, -quantity))
                sell_room -= quantity
            elif position < 0 and buy_room > 0:
                quantity = min(ROBOT_MD_ORDER_SIZE, buy_room, -position)
                orders.append(Order(product, best_ask, quantity))
                buy_room -= quantity

        if z <= -ROBOT_MD_ENTRY_Z and buy_room > 0:
            quantity = min(ROBOT_MD_ORDER_SIZE, buy_room)
            orders.append(Order(product, best_ask, quantity))
        elif z >= ROBOT_MD_ENTRY_Z and sell_room > 0:
            quantity = min(ROBOT_MD_ORDER_SIZE, sell_room)
            orders.append(Order(product, best_bid, -quantity))

        return {product: orders}

    def _trade_chip_ct_pair(self, state: TradingState) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in CHIP_CT_TRADES:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {p: [] for p in CHIP_CT_TRADES}
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        pair_sum = mids[CHIP_CT_TRADES[0]] + mids[CHIP_CT_TRADES[1]]
        result: Dict[str, List[Order]] = {}

        circle = CHIP_CT_TRADES[0]
        best_bid, best_ask = depths[circle]
        position = state.position.get(circle, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if position > 0 and CHIP_CT_PAIR_FAIR - CHIP_CT_EXIT <= pair_sum <= CHIP_CT_PAIR_FAIR + CHIP_CT_EXIT and sell_room > 0:
            orders.append(Order(circle, best_bid, -min(sell_room, position)))
        elif position < 0 and CHIP_CT_PAIR_FAIR - CHIP_CT_EXIT <= pair_sum <= CHIP_CT_PAIR_FAIR + CHIP_CT_EXIT and buy_room > 0:
            orders.append(Order(circle, best_ask, min(buy_room, -position)))

        if pair_sum <= CHIP_CT_PAIR_FAIR - CHIP_CT_ENTRY and buy_room > 0:
            orders.append(Order(circle, best_ask, buy_room))
        elif pair_sum >= CHIP_CT_PAIR_FAIR + CHIP_CT_ENTRY and sell_room > 0:
            orders.append(Order(circle, best_bid, -sell_room))

        return {circle: orders}

    def _trade_pebbles_l_meanrev(self, state: TradingState) -> Dict[str, List[Order]]:
        fair_mids: List[float] = []
        for product in PEBBLES_L_FAIR_PRODUCTS:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {"PEBBLES_L": []}
            fair_mids.append((max(od.buy_orders) + min(od.sell_orders)) / 2.0)
        fair = sum(fair_mids) / len(fair_mids)

        od = state.order_depths.get("PEBBLES_L")
        if od is None or not od.buy_orders or not od.sell_orders:
            return {"PEBBLES_L": []}

        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        mid = (best_bid + best_ask) / 2.0
        position = state.position.get("PEBBLES_L", 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if position > 0 and mid >= fair - PEBBLES_L_EXIT_THRESHOLD and sell_room > 0:
            orders.append(Order("PEBBLES_L", best_bid, -min(sell_room, position)))
        elif position < 0 and mid <= fair + PEBBLES_L_EXIT_THRESHOLD and buy_room > 0:
            orders.append(Order("PEBBLES_L", best_ask, min(buy_room, -position)))

        if mid < fair - PEBBLES_L_ENTRY_THRESHOLD and buy_room > 0:
            orders.append(Order("PEBBLES_L", best_ask, buy_room))
        elif mid > fair + PEBBLES_L_ENTRY_THRESHOLD and sell_room > 0:
            orders.append(Order("PEBBLES_L", best_bid, -sell_room))

        return {"PEBBLES_L": orders}

    def _trade_iron_peb_pair(self, state: TradingState) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in IRON_PEB_TRADES:
            order_depth = state.order_depths.get(product)
            if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                return {product: [] for product in IRON_PEB_TRADES}

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        ir, ps = IRON_PEB_TRADES
        dev = (mids[ir] - mids[ps]) / 2.0  # positive = ironing expensive
        result: Dict[str, List[Order]] = {}

        for product in IRON_PEB_TRADES:
            best_bid, best_ask = depths[product]
            position = state.position.get(product, 0)
            buy_room = POSITION_LIMIT - position
            sell_room = POSITION_LIMIT + position
            orders: List[Order] = []

            if abs(dev) <= IRON_PEB_EXIT and position != 0:
                if position > 0 and sell_room > 0:
                    orders.append(Order(product, best_bid, -min(sell_room, position)))
                elif position < 0 and buy_room > 0:
                    orders.append(Order(product, best_ask, min(buy_room, -position)))

            if dev > IRON_PEB_ENTRY:
                if product == ir and sell_room > 0:
                    orders.append(Order(product, best_bid, -sell_room))
                elif product == ps and buy_room > 0:
                    orders.append(Order(product, best_ask, buy_room))
            elif dev < -IRON_PEB_ENTRY:
                if product == ir and buy_room > 0:
                    orders.append(Order(product, best_ask, buy_room))
                elif product == ps and sell_room > 0:
                    orders.append(Order(product, best_bid, -sell_room))

            result[product] = orders

        return result

    def _trade_uv_ao_pair(self, state: TradingState) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in UV_AO_TRADES:
            order_depth = state.order_depths.get(product)
            if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                return {product: [] for product in UV_AO_TRADES}

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        pair_mid = mids[UV_AO_TRADES[0]] + mids[UV_AO_TRADES[1]]

        # Only trade orange; amber is handled by _trade_uv_amber with the richer group signal
        orange = UV_AO_TRADES[1]
        best_bid, best_ask = depths[orange]
        position = state.position.get(orange, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if (
            position > 0
            and UV_AO_PAIR_FAIR - UV_AO_EXIT_THRESHOLD <= pair_mid <= UV_AO_PAIR_FAIR + UV_AO_EXIT_THRESHOLD
            and sell_room > 0
        ):
            quantity = min(POSITION_LIMIT, sell_room, position)
            orders.append(Order(orange, best_bid, -quantity))
            sell_room -= quantity

        if (
            position < 0
            and UV_AO_PAIR_FAIR - UV_AO_EXIT_THRESHOLD <= pair_mid <= UV_AO_PAIR_FAIR + UV_AO_EXIT_THRESHOLD
            and buy_room > 0
        ):
            quantity = min(POSITION_LIMIT, buy_room, -position)
            orders.append(Order(orange, best_ask, quantity))
            buy_room -= quantity

        if pair_mid <= UV_AO_PAIR_FAIR - UV_AO_ENTRY_THRESHOLD and buy_room > 0:
            quantity = min(POSITION_LIMIT, buy_room)
            orders.append(Order(orange, best_ask, quantity))

        if pair_mid >= UV_AO_PAIR_FAIR + UV_AO_ENTRY_THRESHOLD and sell_room > 0:
            quantity = min(POSITION_LIMIT, sell_room)
            orders.append(Order(orange, best_bid, -quantity))

        return {orange: orders}

    def _trade_panel44_cluster(self, state: TradingState) -> Dict[str, List[Order]]:
        target_depth = state.order_depths.get(PANEL44_CLUSTER_TARGET)
        if target_depth is None or not target_depth.buy_orders or not target_depth.sell_orders:
            return {PANEL44_CLUSTER_TARGET: []}

        cluster_mids: List[float] = []
        for product in PANEL44_CLUSTER_PRODUCTS:
            order_depth = state.order_depths.get(product)
            if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                return {PANEL44_CLUSTER_TARGET: []}

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            cluster_mids.append((best_bid + best_ask) / 2.0)

        best_bid = max(target_depth.buy_orders.keys())
        best_ask = min(target_depth.sell_orders.keys())
        target_mid = (best_bid + best_ask) / 2.0
        cluster_avg = sum(cluster_mids) / len(cluster_mids)
        deviation = target_mid - cluster_avg

        position = state.position.get(PANEL44_CLUSTER_TARGET, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if deviation < -PANEL44_CLUSTER_THRESHOLD and buy_room > 0:
            orders.append(Order(PANEL44_CLUSTER_TARGET, best_ask, buy_room))

        if deviation > PANEL44_CLUSTER_THRESHOLD and sell_room > 0:
            orders.append(Order(PANEL44_CLUSTER_TARGET, best_bid, -sell_room))

        return {PANEL44_CLUSTER_TARGET: orders}

    def _trade_panel_cluster(self, state: TradingState) -> Dict[str, List[Order]]:
        target_depth = state.order_depths.get(PANEL_CLUSTER_TARGET)
        if target_depth is None or not target_depth.buy_orders or not target_depth.sell_orders:
            return {PANEL_CLUSTER_TARGET: []}

        cluster_mids: List[float] = []
        for product in PANEL_CLUSTER_PRODUCTS:
            order_depth = state.order_depths.get(product)
            if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                return {PANEL_CLUSTER_TARGET: []}

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            cluster_mids.append((best_bid + best_ask) / 2.0)

        best_bid = max(target_depth.buy_orders.keys())
        best_ask = min(target_depth.sell_orders.keys())
        target_mid = (best_bid + best_ask) / 2.0
        cluster_avg = sum(cluster_mids) / len(cluster_mids)
        deviation = target_mid - cluster_avg

        position = state.position.get(PANEL_CLUSTER_TARGET, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if deviation < -PANEL_CLUSTER_THRESHOLD and buy_room > 0:
            orders.append(Order(PANEL_CLUSTER_TARGET, best_ask, buy_room))

        if deviation > PANEL_CLUSTER_THRESHOLD and sell_room > 0:
            orders.append(Order(PANEL_CLUSTER_TARGET, best_bid, -sell_room))

        return {PANEL_CLUSTER_TARGET: orders}

    def _trade_panel_1x_sum(self, state: TradingState, histories: dict) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in (PANEL_1X_TARGET, PANEL_1X_SIGNAL):
            order_depth = state.order_depths.get(product)
            if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                return {PANEL_1X_TARGET: []}

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        panel_sum = mids[PANEL_1X_TARGET] + mids[PANEL_1X_SIGNAL]
        history = histories.setdefault(PANEL_1X_HISTORY_KEY, [])
        history.append(panel_sum)
        if len(history) > PANEL_1X_HISTORY_LIMIT:
            histories[PANEL_1X_HISTORY_KEY] = history[-PANEL_1X_HISTORY_LIMIT:]
            history = histories[PANEL_1X_HISTORY_KEY]

        if len(history) < PANEL_1X_WARMUP:
            return {PANEL_1X_TARGET: []}

        mean = sum(history) / len(history)
        variance = sum((value - mean) ** 2 for value in history) / max(1, len(history) - 1)
        stdev = variance ** 0.5
        if stdev < 1:
            return {PANEL_1X_TARGET: []}

        z = (panel_sum - mean) / stdev
        best_bid, best_ask = depths[PANEL_1X_TARGET]
        position = state.position.get(PANEL_1X_TARGET, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if abs(z) <= PANEL_1X_EXIT_Z:
            if position > 0 and sell_room > 0:
                quantity = min(PANEL_1X_ORDER_SIZE, sell_room, position)
                orders.append(Order(PANEL_1X_TARGET, best_bid, -quantity))
                sell_room -= quantity
            elif position < 0 and buy_room > 0:
                quantity = min(PANEL_1X_ORDER_SIZE, buy_room, -position)
                orders.append(Order(PANEL_1X_TARGET, best_ask, quantity))
                buy_room -= quantity

        if z <= -PANEL_1X_ENTRY_Z and buy_room > 0:
            quantity = min(PANEL_1X_ORDER_SIZE, buy_room)
            orders.append(Order(PANEL_1X_TARGET, best_ask, quantity))
        elif z >= PANEL_1X_ENTRY_Z and sell_room > 0:
            quantity = min(PANEL_1X_ORDER_SIZE, sell_room)
            orders.append(Order(PANEL_1X_TARGET, best_bid, -quantity))

        return {PANEL_1X_TARGET: orders}

    def _trade_translator_cluster(self, state: TradingState) -> Dict[str, List[Order]]:
        target_depth = state.order_depths.get(TRANSLATOR_TARGET)
        if target_depth is None or not target_depth.buy_orders or not target_depth.sell_orders:
            return {TRANSLATOR_TARGET: []}

        cluster_mids: List[float] = []
        for product in TRANSLATOR_CLUSTER_PRODUCTS:
            order_depth = state.order_depths.get(product)
            if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                return {TRANSLATOR_TARGET: []}

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            cluster_mids.append((best_bid + best_ask) / 2.0)

        best_bid = max(target_depth.buy_orders.keys())
        best_ask = min(target_depth.sell_orders.keys())
        target_mid = (best_bid + best_ask) / 2.0
        cluster_avg = sum(cluster_mids) / len(cluster_mids)
        deviation = target_mid - cluster_avg

        position = state.position.get(TRANSLATOR_TARGET, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if deviation < -TRANSLATOR_CLUSTER_THRESHOLD and buy_room > 0:
            orders.append(Order(TRANSLATOR_TARGET, best_ask, buy_room))

        if deviation > TRANSLATOR_CLUSTER_THRESHOLD and sell_room > 0:
            orders.append(Order(TRANSLATOR_TARGET, best_bid, -sell_room))

        return {TRANSLATOR_TARGET: orders}

    def _trade_chocolate_signal(self, state: TradingState) -> Dict[str, List[Order]]:
        chocolate_depth = state.order_depths.get("SNACKPACK_CHOCOLATE")
        vanilla_depth = state.order_depths.get("SNACKPACK_VANILLA")
        if (
            chocolate_depth is None
            or vanilla_depth is None
            or not chocolate_depth.buy_orders
            or not chocolate_depth.sell_orders
            or not vanilla_depth.buy_orders
            or not vanilla_depth.sell_orders
        ):
            return {"SNACKPACK_CHOCOLATE": []}

        best_bid = max(chocolate_depth.buy_orders.keys())
        best_ask = min(chocolate_depth.sell_orders.keys())
        chocolate_mid = (best_bid + best_ask) / 2.0
        vanilla_mid = (max(vanilla_depth.buy_orders.keys()) + min(vanilla_depth.sell_orders.keys())) / 2.0
        spread = chocolate_mid - vanilla_mid  # signal: CHOC cheap vs VANILLA when strongly negative

        position = state.position.get("SNACKPACK_CHOCOLATE", 0)
        orders: List[Order] = []

        if position > 0 and spread >= CHOCOLATE_EXIT_CENTER:
            qty = min(CHOCOLATE_SIGNAL_SIZE, position)
            orders.append(Order("SNACKPACK_CHOCOLATE", best_bid, -qty))
        elif position < 0 and spread <= CHOCOLATE_EXIT_CENTER:
            qty = min(CHOCOLATE_SIGNAL_SIZE, -position)
            orders.append(Order("SNACKPACK_CHOCOLATE", best_ask, qty))
        elif spread <= CHOCOLATE_BUY_ENTRY:
            buy_room = POSITION_LIMIT - position
            if buy_room > 0:
                orders.append(Order("SNACKPACK_CHOCOLATE", best_ask, min(CHOCOLATE_SIGNAL_SIZE, buy_room)))
        elif spread >= CHOCOLATE_SELL_ENTRY:
            sell_room = POSITION_LIMIT + position
            if sell_room > 0:
                orders.append(Order("SNACKPACK_CHOCOLATE", best_bid, -min(CHOCOLATE_SIGNAL_SIZE, sell_room)))

        return {"SNACKPACK_CHOCOLATE": orders}

    def _trade_pebbles_ms_pair(self, state: TradingState) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in PEBBLES_MS_TRADES:
            order_depth = state.order_depths.get(product)
            if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                return {product: [] for product in PEBBLES_MS_TRADES}

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        pair_mid = mids["PEBBLES_M"] + mids["PEBBLES_S"]
        pair_fair = PEBBLES_MS_PAIR_FAIR
        result: Dict[str, List[Order]] = {}

        for product in PEBBLES_MS_TRADES:
            best_bid, best_ask = depths[product]
            position = state.position.get(product, 0)
            buy_room = POSITION_LIMIT - position
            sell_room = POSITION_LIMIT + position
            orders: List[Order] = []

            if position > 0 and pair_mid >= pair_fair + PEBBLES_MS_EXIT_THRESHOLD and sell_room > 0:
                quantity = min(PEBBLES_MS_ORDER_SIZE, sell_room, position)
                orders.append(Order(product, best_bid, -quantity))
                sell_room -= quantity

            if position < 0 and pair_mid <= pair_fair - PEBBLES_MS_EXIT_THRESHOLD and buy_room > 0:
                quantity = min(PEBBLES_MS_ORDER_SIZE, buy_room, -position)
                orders.append(Order(product, best_ask, quantity))
                buy_room -= quantity

            if pair_mid <= pair_fair - PEBBLES_MS_ENTRY_THRESHOLD and buy_room > 0:
                quantity = min(PEBBLES_MS_ORDER_SIZE, buy_room)
                orders.append(Order(product, best_ask, quantity))
                buy_room -= quantity

            if pair_mid >= pair_fair + PEBBLES_MS_ENTRY_THRESHOLD and sell_room > 0:
                quantity = min(PEBBLES_MS_ORDER_SIZE, sell_room)
                orders.append(Order(product, best_bid, -quantity))
                sell_room -= quantity

            result[product] = orders

        return result

    def _trade_snackpack_pair(self, state: TradingState) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in SNACKPAIR_TRADES:
            order_depth = state.order_depths.get(product)
            if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                return {product: [] for product in SNACKPAIR_TRADES}

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        pair_mid = mids["SNACKPACK_STRAWBERRY"] + mids["SNACKPACK_PISTACHIO"]
        pair_fair = SNACKPAIR_FAIR
        result: Dict[str, List[Order]] = {}

        for product in SNACKPAIR_TRADES:
            best_bid, best_ask = depths[product]
            position = state.position.get(product, 0)
            buy_room = POSITION_LIMIT - position
            sell_room = POSITION_LIMIT + position
            orders: List[Order] = []

            if position > 0 and pair_mid >= pair_fair + SNACKPAIR_EXIT_THRESHOLD and sell_room > 0:
                quantity = min(SNACKPAIR_ORDER_SIZE, sell_room, position)
                orders.append(Order(product, best_bid, -quantity))
                sell_room -= quantity

            if position < 0 and pair_mid <= pair_fair - SNACKPAIR_EXIT_THRESHOLD and buy_room > 0:
                quantity = min(SNACKPAIR_ORDER_SIZE, buy_room, -position)
                orders.append(Order(product, best_ask, quantity))
                buy_room -= quantity

            if pair_mid <= pair_fair - SNACKPAIR_ENTRY_THRESHOLD and buy_room > 0:
                quantity = min(SNACKPAIR_ORDER_SIZE, buy_room)
                orders.append(Order(product, best_ask, quantity))
                buy_room -= quantity

            if pair_mid >= pair_fair + SNACKPAIR_ENTRY_THRESHOLD and sell_room > 0:
                quantity = min(SNACKPAIR_ORDER_SIZE, sell_room)
                orders.append(Order(product, best_bid, -quantity))
                sell_room -= quantity

            result[product] = orders

        return result

    def _trade_rasp_pis_spread(self, state: TradingState, histories: dict) -> Dict[str, List[Order]]:
        pis_od = state.order_depths.get("SNACKPACK_PISTACHIO")
        ras_od = state.order_depths.get("SNACKPACK_RASPBERRY")
        empty = {"SNACKPACK_PISTACHIO": [], "SNACKPACK_RASPBERRY": []}
        if not pis_od or not ras_od or not pis_od.buy_orders or not pis_od.sell_orders or not ras_od.buy_orders or not ras_od.sell_orders:
            return empty

        pis_bid = max(pis_od.buy_orders)
        pis_ask = min(pis_od.sell_orders)
        ras_bid = max(ras_od.buy_orders)
        ras_ask = min(ras_od.sell_orders)
        pis_mid = (pis_bid + pis_ask) / 2.0
        ras_mid = (ras_bid + ras_ask) / 2.0

        spread = pis_mid - ras_mid
        ema = histories.get("rasp_pis_ema", spread)
        ema = RASP_PIS_EMA_ALPHA * spread + (1 - RASP_PIS_EMA_ALPHA) * ema
        histories["rasp_pis_ema"] = ema
        dev = spread - ema

        pos_pis = state.position.get("SNACKPACK_PISTACHIO", 0)
        pos_ras = state.position.get("SNACKPACK_RASPBERRY", 0)
        buy_pis = POSITION_LIMIT - pos_pis
        sell_pis = POSITION_LIMIT + pos_pis
        buy_ras = POSITION_LIMIT - pos_ras
        sell_ras = POSITION_LIMIT + pos_ras

        pis_orders: List[Order] = []
        ras_orders: List[Order] = []

        # Exit when spread reverts toward EMA
        if pos_pis < 0 and abs(dev) <= RASP_PIS_EXIT:
            pis_orders.append(Order("SNACKPACK_PISTACHIO", pis_ask, min(buy_pis, -pos_pis)))
        elif pos_pis > 0 and abs(dev) <= RASP_PIS_EXIT:
            pis_orders.append(Order("SNACKPACK_PISTACHIO", pis_bid, -min(sell_pis, pos_pis)))

        if pos_ras < 0 and abs(dev) <= RASP_PIS_EXIT:
            ras_orders.append(Order("SNACKPACK_RASPBERRY", ras_ask, min(buy_ras, -pos_ras)))
        elif pos_ras > 0 and abs(dev) <= RASP_PIS_EXIT:
            ras_orders.append(Order("SNACKPACK_RASPBERRY", ras_bid, -min(sell_ras, pos_ras)))

        # Entry: spread too high → pistachio expensive vs raspberry → sell pis, buy ras
        if dev > RASP_PIS_ENTRY and pos_pis == 0 and pos_ras == 0:
            qty = min(RASP_PIS_ORDER_SIZE, sell_pis, buy_ras)
            if qty > 0:
                pis_orders.append(Order("SNACKPACK_PISTACHIO", pis_bid, -qty))
                ras_orders.append(Order("SNACKPACK_RASPBERRY", ras_ask, qty))

        # Entry: spread too low → pistachio cheap vs raspberry → buy pis, sell ras
        elif dev < -RASP_PIS_ENTRY and pos_pis == 0 and pos_ras == 0:
            qty = min(RASP_PIS_ORDER_SIZE, buy_pis, sell_ras)
            if qty > 0:
                pis_orders.append(Order("SNACKPACK_PISTACHIO", pis_ask, qty))
                ras_orders.append(Order("SNACKPACK_RASPBERRY", ras_bid, -qty))

        return {"SNACKPACK_PISTACHIO": pis_orders, "SNACKPACK_RASPBERRY": ras_orders}

    def _trade_galaxy_dm_pr(self, state: TradingState) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in GALAXY_DM_PR_TRADES:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {p: [] for p in GALAXY_DM_PR_TRADES}
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        dm, pr = GALAXY_DM_PR_TRADES
        pair_mean = (mids[dm] + mids[pr]) / 2.0
        dm_dev = mids[dm] - pair_mean  # positive = DM expensive, PR cheap

        best_bid, best_ask = depths[dm]
        position = state.position.get(dm, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if position > 0 and abs(dm_dev) <= GALAXY_DM_PR_EXIT and sell_room > 0:
            orders.append(Order(dm, best_bid, -min(sell_room, position)))
        elif position < 0 and abs(dm_dev) <= GALAXY_DM_PR_EXIT and buy_room > 0:
            orders.append(Order(dm, best_ask, min(buy_room, -position)))

        if dm_dev > GALAXY_DM_PR_ENTRY and sell_room > 0:
            orders.append(Order(dm, best_bid, -sell_room))
        elif dm_dev < -GALAXY_DM_PR_ENTRY and buy_room > 0:
            orders.append(Order(dm, best_ask, buy_room))

        return {dm: orders}

    def _trade_galaxy_sw_dm(self, state: TradingState) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in GALAXY_SW_DM_TRADES:
            od = state.order_depths.get(product)
            if od is None or not od.buy_orders or not od.sell_orders:
                return {p: [] for p in GALAXY_SW_DM_TRADES}
            best_bid = max(od.buy_orders)
            best_ask = min(od.sell_orders)
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        sw, dm = GALAXY_SW_DM_TRADES
        sw_dev = (mids[sw] - mids[dm]) / 2.0  # positive = SW expensive, DM cheap

        result: Dict[str, List[Order]] = {}
        for product in GALAXY_SW_DM_TRADES:
            best_bid, best_ask = depths[product]
            position = state.position.get(product, 0)
            buy_room = POSITION_LIMIT - position
            sell_room = POSITION_LIMIT + position
            orders: List[Order] = []

            if abs(sw_dev) <= GALAXY_SW_DM_EXIT and position != 0:
                if position > 0 and sell_room > 0:
                    orders.append(Order(product, best_bid, -min(sell_room, position)))
                elif position < 0 and buy_room > 0:
                    orders.append(Order(product, best_ask, min(buy_room, -position)))

            if sw_dev > GALAXY_SW_DM_ENTRY:
                if product == sw and sell_room > 0:
                    orders.append(Order(product, best_bid, -sell_room))
                elif product == dm and buy_room > 0:
                    orders.append(Order(product, best_ask, buy_room))
            elif sw_dev < -GALAXY_SW_DM_ENTRY:
                if product == sw and buy_room > 0:
                    orders.append(Order(product, best_ask, buy_room))
                elif product == dm and sell_room > 0:
                    orders.append(Order(product, best_bid, -sell_room))

            result[product] = orders
        return result

    def _trade_galaxy_sw_bh(self, state: TradingState) -> Dict[str, List[Order]]:
        sig_od = state.order_depths.get(GALAXY_SW_BH_SIGNAL)
        tgt_od = state.order_depths.get(GALAXY_SW_BH_TARGET)
        if not sig_od or not tgt_od or not sig_od.buy_orders or not sig_od.sell_orders or not tgt_od.buy_orders or not tgt_od.sell_orders:
            return {GALAXY_SW_BH_TARGET: []}

        sw_mid = (max(sig_od.buy_orders) + min(sig_od.sell_orders)) / 2.0
        bh_bid = max(tgt_od.buy_orders)
        bh_ask = min(tgt_od.sell_orders)
        bh_mid = (bh_bid + bh_ask) / 2.0
        sw_dev = (sw_mid - bh_mid) / 2.0  # negative = SW cheap vs BH

        position = state.position.get(GALAXY_SW_BH_TARGET, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if abs(sw_dev) <= GALAXY_SW_BH_EXIT:
            if position > 0 and sell_room > 0:
                orders.append(Order(GALAXY_SW_BH_TARGET, bh_bid, -min(sell_room, position)))
            elif position < 0 and buy_room > 0:
                orders.append(Order(GALAXY_SW_BH_TARGET, bh_ask, min(buy_room, -position)))

        if sw_dev > -GALAXY_SW_BH_ENTRY and buy_room > 0:
            orders.append(Order(GALAXY_SW_BH_TARGET, bh_ask, buy_room))
        elif sw_dev < -GALAXY_SW_BH_ENTRY and sell_room > 0:
            orders.append(Order(GALAXY_SW_BH_TARGET, bh_bid, -sell_room))

        return {GALAXY_SW_BH_TARGET: orders}

    # ─────────────────────────── New zero-profit strategies ───────────────────────────

    def _trade_signal_target_pair(
        self,
        state: TradingState,
        signal_product: str,
        target_product: str,
        fair_diff: float,
        entry: float,
        exit_thresh: float,
        size: int,
    ) -> Dict[str, List[Order]]:
        sig_od = state.order_depths.get(signal_product)
        tgt_od = state.order_depths.get(target_product)
        if not sig_od or not tgt_od or not sig_od.buy_orders or not sig_od.sell_orders or not tgt_od.buy_orders or not tgt_od.sell_orders:
            return {target_product: []}
        sig_mid = (max(sig_od.buy_orders) + min(sig_od.sell_orders)) / 2.0
        tgt_bid = max(tgt_od.buy_orders)
        tgt_ask = min(tgt_od.sell_orders)
        tgt_mid = (tgt_bid + tgt_ask) / 2.0
        deviation = tgt_mid - sig_mid - fair_diff  # positive = target expensive vs fair
        position = state.position.get(target_product, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []
        if position > 0 and deviation >= -exit_thresh and sell_room > 0:
            qty = min(size, sell_room, position)
            orders.append(Order(target_product, tgt_bid, -qty))
        elif position < 0 and deviation <= exit_thresh and buy_room > 0:
            qty = min(size, buy_room, -position)
            orders.append(Order(target_product, tgt_ask, qty))
        if deviation < -entry and buy_room > 0:
            qty = min(size, buy_room)
            orders.append(Order(target_product, tgt_ask, qty))
        elif deviation > entry and sell_room > 0:
            qty = min(size, sell_room)
            orders.append(Order(target_product, tgt_bid, -qty))
        return {target_product: orders}

    def _trade_group_mean_target(
        self,
        state: TradingState,
        target_product: str,
        group_products: tuple,
        fair_diff: float,
        entry: float,
        exit_thresh: float,
        size: int,
    ) -> Dict[str, List[Order]]:
        group_mids: List[float] = []
        for p in group_products:
            od = state.order_depths.get(p)
            if not od or not od.buy_orders or not od.sell_orders:
                return {target_product: []}
            group_mids.append((max(od.buy_orders) + min(od.sell_orders)) / 2.0)
        tgt_od = state.order_depths.get(target_product)
        if not tgt_od or not tgt_od.buy_orders or not tgt_od.sell_orders:
            return {target_product: []}
        group_avg = sum(group_mids) / len(group_mids)
        tgt_bid = max(tgt_od.buy_orders)
        tgt_ask = min(tgt_od.sell_orders)
        tgt_mid = (tgt_bid + tgt_ask) / 2.0
        deviation = tgt_mid - group_avg - fair_diff  # positive = target expensive vs fair
        position = state.position.get(target_product, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []
        if position > 0 and deviation >= -exit_thresh and sell_room > 0:
            qty = min(size, sell_room, position)
            orders.append(Order(target_product, tgt_bid, -qty))
        elif position < 0 and deviation <= exit_thresh and buy_room > 0:
            qty = min(size, buy_room, -position)
            orders.append(Order(target_product, tgt_ask, qty))
        if deviation < -entry and buy_room > 0:
            qty = min(size, buy_room)
            orders.append(Order(target_product, tgt_ask, qty))
        elif deviation > entry and sell_room > 0:
            qty = min(size, sell_room)
            orders.append(Order(target_product, tgt_bid, -qty))
        return {target_product: orders}

    def _trade_robot_vacuuming(self, state: TradingState, histories: dict) -> Dict[str, List[Order]]:
        vac_od = state.order_depths.get(ROBOT_VAC_TARGET)
        rect_od = state.order_depths.get(ROBOT_VAC_SIGNAL)
        if (
            vac_od is None
            or rect_od is None
            or not vac_od.buy_orders
            or not vac_od.sell_orders
            or not rect_od.buy_orders
            or not rect_od.sell_orders
        ):
            return {ROBOT_VAC_TARGET: []}

        vac_bid = max(vac_od.buy_orders)
        vac_ask = min(vac_od.sell_orders)
        vac_mid = (vac_bid + vac_ask) / 2.0
        rect_mid = (max(rect_od.buy_orders) + min(rect_od.sell_orders)) / 2.0
        signal_sum = vac_mid + rect_mid

        history = histories.setdefault(ROBOT_VAC_HISTORY_KEY, [])
        history.append(signal_sum)
        if len(history) > ROBOT_VAC_HISTORY_LIMIT:
            histories[ROBOT_VAC_HISTORY_KEY] = history[-ROBOT_VAC_HISTORY_LIMIT:]
            history = histories[ROBOT_VAC_HISTORY_KEY]

        if len(history) < ROBOT_VAC_WARMUP:
            return {ROBOT_VAC_TARGET: []}

        mean = sum(history) / len(history)
        variance = sum((value - mean) ** 2 for value in history) / max(1, len(history) - 1)
        stdev = variance ** 0.5
        if stdev < 1:
            return {ROBOT_VAC_TARGET: []}

        z = (signal_sum - mean) / stdev
        position = state.position.get(ROBOT_VAC_TARGET, 0)
        buy_room = POSITION_LIMIT - position
        sell_room = POSITION_LIMIT + position
        orders: List[Order] = []

        if abs(z) <= ROBOT_VAC_EXIT_Z:
            if position > 0 and sell_room > 0:
                quantity = min(ROBOT_VAC_SIZE, sell_room, position)
                orders.append(Order(ROBOT_VAC_TARGET, vac_bid, -quantity))
                sell_room -= quantity
            elif position < 0 and buy_room > 0:
                quantity = min(ROBOT_VAC_SIZE, buy_room, -position)
                orders.append(Order(ROBOT_VAC_TARGET, vac_ask, quantity))
                buy_room -= quantity

        if z <= -ROBOT_VAC_ENTRY_Z and buy_room > 0:
            quantity = min(ROBOT_VAC_SIZE, buy_room)
            orders.append(Order(ROBOT_VAC_TARGET, vac_ask, quantity))
        elif z >= ROBOT_VAC_ENTRY_Z and sell_room > 0:
            quantity = min(ROBOT_VAC_SIZE, sell_room)
            orders.append(Order(ROBOT_VAC_TARGET, vac_bid, -quantity))

        return {ROBOT_VAC_TARGET: orders}

    def _trade_solar_flames(self, state: TradingState) -> Dict[str, List[Order]]:
        return self._trade_signal_target_pair(
            state, SOLAR_FLAMES_SIGNAL, SOLAR_FLAMES_TARGET,
            SOLAR_FLAMES_FAIR_DIFF, SOLAR_FLAMES_ENTRY, SOLAR_FLAMES_EXIT, SOLAR_FLAMES_SIZE)

    def _trade_lamb_wool(self, state: TradingState) -> Dict[str, List[Order]]:
        return self._trade_signal_target_pair(
            state, LAMB_WOOL_SIGNAL, LAMB_WOOL_TARGET,
            LAMB_WOOL_FAIR_DIFF, LAMB_WOOL_ENTRY, LAMB_WOOL_EXIT, LAMB_WOOL_SIZE)

    def _trade_mint(self, state: TradingState) -> Dict[str, List[Order]]:
        return self._trade_group_mean_target(
            state, MINT_TARGET, MINT_GROUP,
            MINT_FAIR_DIFF, MINT_ENTRY, MINT_EXIT, MINT_SIZE)

    def _trade_uv_yellow(self, state: TradingState) -> Dict[str, List[Order]]:
        return self._trade_group_mean_target(
            state, UV_YELLOW_TARGET, UV_YELLOW_GROUP,
            UV_YELLOW_FAIR_DIFF, UV_YELLOW_ENTRY, UV_YELLOW_EXIT, UV_YELLOW_SIZE)

    def _trade_microchip_square(self, state: TradingState) -> Dict[str, List[Order]]:
        return self._trade_signal_target_pair(
            state, MC_SQ_SIGNAL, MC_SQ_TARGET,
            MC_SQ_FAIR_DIFF, MC_SQ_ENTRY, MC_SQ_EXIT, MC_SQ_SIZE)

    def _trade_panel_2x4(self, state: TradingState) -> Dict[str, List[Order]]:
        return self._trade_signal_target_pair(
            state, PANEL2X4_SIGNAL, PANEL2X4_TARGET,
            PANEL2X4_FAIR_DIFF, PANEL2X4_ENTRY, PANEL2X4_EXIT, PANEL2X4_SIZE)

    def _trade_panel_1x4(self, state: TradingState) -> Dict[str, List[Order]]:
        return self._trade_group_mean_target(
            state, PANEL1X4_TARGET, PANEL1X4_GROUP,
            PANEL1X4_FAIR_DIFF, PANEL1X4_ENTRY, PANEL1X4_EXIT, PANEL1X4_SIZE)

    def _trade_xs_rect_pair(self, state: TradingState, histories: dict) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in XS_RECT_TRADES:
            order_depth = state.order_depths.get(product)
            if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                return {p: [] for p in XS_RECT_TRADES}

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        xs, rect = XS_RECT_TRADES
        spread = mids[xs] - mids[rect]
        history = histories.setdefault(XS_RECT_HISTORY_KEY, [])
        history.append(spread)
        if len(history) > XS_RECT_HISTORY_LIMIT:
            histories[XS_RECT_HISTORY_KEY] = history[-XS_RECT_HISTORY_LIMIT:]
            history = histories[XS_RECT_HISTORY_KEY]

        if len(history) < XS_RECT_WARMUP:
            return {p: [] for p in XS_RECT_TRADES}

        mean = sum(history) / len(history)
        variance = sum((value - mean) ** 2 for value in history) / max(1, len(history) - 1)
        stdev = variance ** 0.5
        if stdev < 1:
            return {p: [] for p in XS_RECT_TRADES}

        z = (spread - mean) / stdev
        result: Dict[str, List[Order]] = {}

        for product in XS_RECT_TRADES:
            best_bid, best_ask = depths[product]
            position = state.position.get(product, 0)
            buy_room = POSITION_LIMIT - position
            sell_room = POSITION_LIMIT + position
            orders: List[Order] = []

            if abs(z) <= XS_RECT_EXIT_Z:
                if position > 0 and sell_room > 0:
                    quantity = min(XS_RECT_ORDER_SIZE, sell_room, position)
                    orders.append(Order(product, best_bid, -quantity))
                    sell_room -= quantity
                elif position < 0 and buy_room > 0:
                    quantity = min(XS_RECT_ORDER_SIZE, buy_room, -position)
                    orders.append(Order(product, best_ask, quantity))
                    buy_room -= quantity

            if z >= XS_RECT_ENTRY_Z:
                if product == xs and sell_room > 0:
                    quantity = min(XS_RECT_ORDER_SIZE, sell_room)
                    orders.append(Order(product, best_bid, -quantity))
                elif product == rect and buy_room > 0:
                    quantity = min(XS_RECT_ORDER_SIZE, buy_room)
                    orders.append(Order(product, best_ask, quantity))
            elif z <= -XS_RECT_ENTRY_Z:
                if product == xs and buy_room > 0:
                    quantity = min(XS_RECT_ORDER_SIZE, buy_room)
                    orders.append(Order(product, best_ask, quantity))
                elif product == rect and sell_room > 0:
                    quantity = min(XS_RECT_ORDER_SIZE, sell_room)
                    orders.append(Order(product, best_bid, -quantity))

            result[product] = orders

        return result

    def _trade_pebbles_pair(self, state: TradingState) -> Dict[str, List[Order]]:
        depths = {}
        mids = {}
        for product in PEBBLES_TRADES:
            order_depth = state.order_depths.get(product)
            if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                return {product: [] for product in PEBBLES_TRADES}

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            depths[product] = (best_bid, best_ask)
            mids[product] = (best_bid + best_ask) / 2.0

        pair_mid = mids["PEBBLES_XS"] + mids["PEBBLES_XL"]
        pair_fair = PEBBLES_PAIR_FAIR
        result: Dict[str, List[Order]] = {}

        for product in PEBBLES_TRADES:
            best_bid, best_ask = depths[product]
            position = state.position.get(product, 0)
            buy_room = POSITION_LIMIT - position
            sell_room = POSITION_LIMIT + position
            orders: List[Order] = []

            if position > 0 and pair_mid >= pair_fair + PEBBLES_EXIT_THRESHOLD and sell_room > 0:
                quantity = min(PEBBLES_ORDER_SIZE, sell_room, position)
                orders.append(Order(product, best_bid, -quantity))
                sell_room -= quantity

            if position < 0 and pair_mid <= pair_fair - PEBBLES_EXIT_THRESHOLD and buy_room > 0:
                quantity = min(PEBBLES_ORDER_SIZE, buy_room, -position)
                orders.append(Order(product, best_ask, quantity))
                buy_room -= quantity

            if pair_mid <= pair_fair - PEBBLES_ENTRY_THRESHOLD and buy_room > 0:
                quantity = min(PEBBLES_ORDER_SIZE, buy_room)
                orders.append(Order(product, best_ask, quantity))
                buy_room -= quantity

            if pair_mid >= pair_fair + PEBBLES_ENTRY_THRESHOLD and sell_room > 0:
                quantity = min(PEBBLES_ORDER_SIZE, sell_room)
                orders.append(Order(product, best_bid, -quantity))
                sell_room -= quantity

            result[product] = orders

        return result

    def _snackpack_mean(self, state: TradingState):
        mids: List[float] = []
        for product in SNACKPACK_PRODUCTS:
            order_depth = state.order_depths.get(product)
            if order_depth is None or not order_depth.buy_orders or not order_depth.sell_orders:
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mids.append((best_bid + best_ask) / 2.0)

        if not mids:
            return None

        return sum(mids) / len(mids)

    def _load_histories(self, trader_data: str) -> Dict[str, List[float]]:
        if not trader_data:
            return {product: [] for product in SNACKPACK_TRADES}

        try:
            decoded = json.loads(trader_data)
        except json.JSONDecodeError:
            return {product: [] for product in SNACKPACK_TRADES}

        histories: Dict[str, List[float]] = {}
        for product in SNACKPACK_TRADES:
            values = decoded.get(product, [])
            if not isinstance(values, list):
                values = []
            histories[product] = [float(value) for value in values[-HISTORY_LIMIT:]]

        values = decoded.get(ROBOT_MD_HISTORY_KEY, [])
        if not isinstance(values, list):
            values = []
        histories[ROBOT_MD_HISTORY_KEY] = [float(value) for value in values[-ROBOT_MD_HISTORY_LIMIT:]]

        values = decoded.get(ROBOT_LD_HISTORY_KEY, [])
        if not isinstance(values, list):
            values = []
        histories[ROBOT_LD_HISTORY_KEY] = [float(value) for value in values[-ROBOT_LD_HISTORY_LIMIT:]]

        values = decoded.get(PANEL_1X_HISTORY_KEY, [])
        if not isinstance(values, list):
            values = []
        histories[PANEL_1X_HISTORY_KEY] = [float(value) for value in values[-PANEL_1X_HISTORY_LIMIT:]]

        values = decoded.get(XS_RECT_HISTORY_KEY, [])
        if not isinstance(values, list):
            values = []
        histories[XS_RECT_HISTORY_KEY] = [float(value) for value in values[-XS_RECT_HISTORY_LIMIT:]]

        values = decoded.get(ROBOT_VAC_HISTORY_KEY, [])
        if not isinstance(values, list):
            values = []
        histories[ROBOT_VAC_HISTORY_KEY] = [float(value) for value in values[-ROBOT_VAC_HISTORY_LIMIT:]]

        values = decoded.get(NYLON_CHOCOLATE_HISTORY_KEY, [])
        if not isinstance(values, list):
            values = []
        histories[NYLON_CHOCOLATE_HISTORY_KEY] = [float(value) for value in values[-NYLON_CHOCOLATE_HISTORY_LIMIT:]]

        t_saved = decoded.get("_t")
        if isinstance(t_saved, dict):
            histories["_t"] = t_saved

        t2 = decoded.get("_t2")
        if isinstance(t2, dict):
            histories["_t2"] = t2

        values = decoded.get("poly_bh", [])
        if not isinstance(values, list):
            values = []
        histories["poly_bh"] = [float(v) for v in values[-101:]]

        poly_ll = decoded.get("poly_ll")
        if isinstance(poly_ll, dict):
            histories["poly_ll"] = poly_ll

        return histories
