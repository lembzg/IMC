"""
IMC Prosperity 4 - Frankfurt Hedgehogs Architecture Port
=========================================================
Architecture adapted from TimoDiehm/imc-prosperity-3 (2nd place globally).
Bugs fixed vs original source:
  1. constituents.sort() → sorted()          (sort() returns None)
  2. self.spreads[basket.name] → [b_idx]     (spreads is a list, not a dict)
  3. self.new_switch_mean → indicators[...]  (was never assigned)
  4. self.vegas → indicators['vegas']        (was never assigned)
  5. get_underlying_orders used ema_o_dev    (should use ema_u_dev)

Round 0 active strategies:
  EMERALDS → StaticTrader  (fixed fair value, wall-mid)
  TOMATOES → DynamicTrader (Olivia detection, wall-mid MM)

Activate later rounds by adding symbols to PRODUCT_TRADERS in Trader.run().
"""

from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
from statistics import NormalDist
import json
import math
import numpy as np

_N = NormalDist()

# ══════════════════════════════════════════════════════════════════════════════
# SYMBOLS  — update each round
# ══════════════════════════════════════════════════════════════════════════════

STATIC_SYMBOL    = 'EMERALDS'           # fixed fair value (Rainforest Resin analogue)
DYNAMIC_SYMBOL   = 'TOMATOES'           # Olivia + wall-mid MM (Kelp analogue)
INK_SYMBOL       = 'SQUID_INK'          # pure Olivia follower — activate when present

ETF_BASKET_SYMBOLS     = ['PICNIC_BASKET1', 'PICNIC_BASKET2']
ETF_CONSTITUENT_SYMBOLS = ['CROISSANTS', 'JAMS', 'DJEMBES']

OPTION_UNDERLYING_SYMBOL = 'VOLCANIC_ROCK'
OPTION_SYMBOLS = [
    'VOLCANIC_ROCK_VOUCHER_9500',
    'VOLCANIC_ROCK_VOUCHER_9750',
    'VOLCANIC_ROCK_VOUCHER_10000',
    'VOLCANIC_ROCK_VOUCHER_10250',
    'VOLCANIC_ROCK_VOUCHER_10500',
]

COMMODITY_SYMBOL = 'MAGNIFICENT_MACARONS'

# ══════════════════════════════════════════════════════════════════════════════
# POSITION LIMITS  — update each round
# ══════════════════════════════════════════════════════════════════════════════

POS_LIMITS: Dict[str, int] = {
    STATIC_SYMBOL:  80,
    DYNAMIC_SYMBOL: 80,
    INK_SYMBOL:     50,
    ETF_BASKET_SYMBOLS[0]: 60,
    ETF_BASKET_SYMBOLS[1]: 100,
    ETF_CONSTITUENT_SYMBOLS[0]: 250,
    ETF_CONSTITUENT_SYMBOLS[1]: 350,
    ETF_CONSTITUENT_SYMBOLS[2]: 60,
    OPTION_UNDERLYING_SYMBOL: 400,
    **{s: 200 for s in OPTION_SYMBOLS},
    COMMODITY_SYMBOL: 75,
}

CONVERSION_LIMIT = 10

# ══════════════════════════════════════════════════════════════════════════════
# INFORMED TRADER
# ══════════════════════════════════════════════════════════════════════════════

INFORMED_TRADER_ID = 'Olivia'
LONG, NEUTRAL, SHORT = 1, 0, -1

# ══════════════════════════════════════════════════════════════════════════════
# ETF PARAMETERS
# ══════════════════════════════════════════════════════════════════════════════

# BASKET1 = 6·CROISSANTS + 3·JAMS + 1·DJEMBES
# BASKET2 = 4·CROISSANTS + 2·JAMS
ETF_CONSTITUENT_FACTORS = [[6, 3, 1], [4, 2, 0]]
BASKET_THRESHOLDS       = [80, 50]          # spread entry thresholds
INITIAL_ETF_PREMIUMS    = [5, 53]           # starting running-premium estimates
N_HIST_SAMPLES          = 60_000            # initial n for running mean
ETF_INFORMED_CONSTITUENT = ETF_CONSTITUENT_SYMBOLS[0]  # CROISSANTS
ETF_THR_INFORMED_ADJS   = [90, 90]          # threshold shift when Olivia detected
ETF_CLOSE_AT_ZERO       = True
CALCULATE_RUNNING_ETF_PREMIUM = True
ETF_HEDGE_FACTOR        = 0.5

# ══════════════════════════════════════════════════════════════════════════════
# OPTIONS PARAMETERS
# ══════════════════════════════════════════════════════════════════════════════

DAY          = 5        # current competition day — update each round
DAYS_PER_YEAR = 365

THR_OPEN,  THR_CLOSE   = 0.5, 0
LOW_VEGA_THR_ADJ       = 0.5
THEO_NORM_WINDOW       = 20
IV_SCALPING_THR        = 0.7
IV_SCALPING_WINDOW     = 100

UNDERLYING_MR_THR      = 15
UNDERLYING_MR_WINDOW   = 10
OPTIONS_MR_THR         = 5
OPTIONS_MR_WINDOW      = 30

# Fitted IV smile parabola: iv = a·m² + b·m + c  where m = ln(K/S)/√TTE
IV_SMILE_COEFFS = [0.27362531, 0.01007566, 0.14876677]


# ══════════════════════════════════════════════════════════════════════════════
# BASE CLASS
# ══════════════════════════════════════════════════════════════════════════════

class ProductTrader:
    """
    Base class for all per-product traders.
    Handles: order book parsing, wall-mid calculation, position limits,
             order helpers (bid/ask with automatic limit enforcement),
             traderData load/save, Olivia detection.
    """

    def __init__(self, name: str, state: TradingState,
                 prints: dict, new_trader_data: dict,
                 product_group: str = None):

        self.orders: List[Order] = []
        self.name            = name
        self.state           = state
        self.prints          = prints
        self.new_trader_data = new_trader_data
        self.product_group   = name if product_group is None else product_group

        self.last_trader_data = self._load_trader_data()

        self.position_limit    = POS_LIMITS.get(name, 0)
        self.initial_position  = state.position.get(name, 0)
        self.expected_position = self.initial_position  # update when hedging

        self.mkt_buy_orders, self.mkt_sell_orders = self._parse_order_book()
        self.bid_wall, self.wall_mid, self.ask_wall = self._calc_walls()
        self.best_bid, self.best_ask = self._calc_best_bid_ask()
        self.max_buy_vol, self.max_sell_vol = self._calc_max_volumes()
        self.total_mkt_buy_vol, self.total_mkt_sell_vol = self._calc_total_mkt_volume()

    # ── Initialisation helpers ───────────────────────────────────────────────

    def _load_trader_data(self) -> dict:
        try:
            if self.state.traderData:
                return json.loads(self.state.traderData)
        except Exception:
            self.log('ERROR', 'traderData parse failed')
        return {}

    def _parse_order_book(self):
        buy_orders = sell_orders = {}
        try:
            od: OrderDepth = self.state.order_depths[self.name]
            buy_orders  = dict(sorted(od.buy_orders.items(),  key=lambda x: x[0], reverse=True))
            sell_orders = dict(sorted(od.sell_orders.items(), key=lambda x: x[0]))
            # Normalise sell volumes to positive
            sell_orders = {p: abs(v) for p, v in sell_orders.items()}
        except Exception:
            pass
        return buy_orders, sell_orders

    def _calc_walls(self):
        """
        Wall mid = average of outermost (deepest) bid and ask levels.
        For stable products these deep levels anchor the true fair value
        and are far more reliable than best-bid/ask.
        """
        bid_wall = ask_wall = wall_mid = None
        try:
            bid_wall = min(self.mkt_buy_orders.keys())   # lowest (deepest) bid
        except Exception:
            pass
        try:
            ask_wall = max(self.mkt_sell_orders.keys())  # highest (deepest) ask
        except Exception:
            pass
        if bid_wall is not None and ask_wall is not None:
            wall_mid = (bid_wall + ask_wall) / 2
        return bid_wall, wall_mid, ask_wall

    def _calc_best_bid_ask(self):
        best_bid = best_ask = None
        try:
            best_bid = max(self.mkt_buy_orders.keys())
        except Exception:
            pass
        try:
            best_ask = min(self.mkt_sell_orders.keys())
        except Exception:
            pass
        return best_bid, best_ask

    def _calc_max_volumes(self):
        return (self.position_limit - self.initial_position,
                self.position_limit + self.initial_position)

    def _calc_total_mkt_volume(self):
        buy_vol = sell_vol = 0
        try:
            buy_vol  = sum(self.mkt_buy_orders.values())
            sell_vol = sum(self.mkt_sell_orders.values())
        except Exception:
            pass
        return buy_vol, sell_vol

    # ── Order helpers ────────────────────────────────────────────────────────

    def bid(self, price: float, volume: float, logging: bool = True):
        """Place a buy order, capped at remaining buy capacity."""
        vol = min(abs(int(volume)), self.max_buy_vol)
        if vol <= 0:
            return
        order = Order(self.name, int(price), vol)
        self.orders.append(order)
        self.max_buy_vol -= vol
        if logging:
            self.log('BUY', {'p': int(price), 'v': vol})

    def ask(self, price: float, volume: float, logging: bool = True):
        """Place a sell order, capped at remaining sell capacity."""
        vol = min(abs(int(volume)), self.max_sell_vol)
        if vol <= 0:
            return
        order = Order(self.name, int(price), -vol)
        self.orders.append(order)
        self.max_sell_vol -= vol
        if logging:
            self.log('SELL', {'p': int(price), 'v': vol})

    # ── Logging ──────────────────────────────────────────────────────────────

    def log(self, kind: str, message, product_group: str = None):
        pg = product_group or self.product_group
        if pg == 'ORDERS':
            self.prints.setdefault(pg, []).append({kind: message})
        else:
            self.prints.setdefault(pg, {})[kind] = message

    # ── Olivia detection ─────────────────────────────────────────────────────

    def check_for_informed(self):
        """
        Track whether the informed trader (Olivia) has recently bought or sold.
        Returns (direction, bought_ts, sold_ts) where direction ∈ {LONG, NEUTRAL, SHORT}.

        Olivia historically buys at the daily low and sells at the daily high.
        When she's bought but not sold → expect price to keep rising → go LONG.
        When she's sold but not bought → expect price to keep falling → go SHORT.
        """
        bought_ts, sold_ts = self.last_trader_data.get(self.name, [None, None])

        all_trades = (self.state.market_trades.get(self.name, []) +
                      self.state.own_trades.get(self.name, []))

        for trade in all_trades:
            if trade.buyer  == INFORMED_TRADER_ID:
                bought_ts = trade.timestamp
            if trade.seller == INFORMED_TRADER_ID:
                sold_ts   = trade.timestamp

        self.new_trader_data[self.name] = [bought_ts, sold_ts]

        if bought_ts is None and sold_ts is None:
            direction = NEUTRAL
        elif bought_ts is None:
            direction = SHORT
        elif sold_ts is None:
            direction = LONG
        else:
            if   sold_ts   > bought_ts: direction = SHORT
            elif bought_ts > sold_ts:   direction = LONG
            else:                       direction = NEUTRAL

        self.log('OLIVIA_DIR', direction)
        return direction, bought_ts, sold_ts

    def get_orders(self) -> dict:
        """Override in each subclass."""
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# STATIC TRADER  (EMERALDS / Rainforest Resin)
# Fixed fair value anchored by wall-mid. Overbid/underbid to front-run queue.
# ══════════════════════════════════════════════════════════════════════════════

class StaticTrader(ProductTrader):

    def __init__(self, state, prints, new_trader_data):
        super().__init__(STATIC_SYMBOL, state, prints, new_trader_data)

    def get_orders(self) -> dict:
        if self.wall_mid is None:
            return {}

        # ── 1. TAKING: hit clearly mispriced quotes ──────────────────────────
        # Buy everything offered below wall_mid (definitely cheap)
        for sp, sv in self.mkt_sell_orders.items():
            if sp <= self.wall_mid - 1:
                self.bid(sp, sv, logging=False)
            elif sp <= self.wall_mid and self.initial_position < 0:
                # At fair value but we're short → reduce position
                self.bid(sp, min(sv, abs(self.initial_position)), logging=False)

        # Sell everything bid above wall_mid (definitely expensive)
        for bp, bv in self.mkt_buy_orders.items():
            if bp >= self.wall_mid + 1:
                self.ask(bp, bv, logging=False)
            elif bp >= self.wall_mid and self.initial_position > 0:
                # At fair value but we're long → reduce position
                self.ask(bp, min(bv, self.initial_position), logging=False)

        # ── 2. MAKING: quote inside the wall spread ──────────────────────────
        bid_price = int(self.bid_wall + 1)   # default: one tick inside wall
        ask_price = int(self.ask_wall - 1)   # default: one tick inside wall

        # Overbid: find the highest existing bid below wall_mid with size > 1
        # and quote one tick above it (front-runs the queue)
        for bp, bv in self.mkt_buy_orders.items():
            if bv > 1 and bp + 1 < self.wall_mid:
                bid_price = max(bid_price, bp + 1)
                break
            elif bp < self.wall_mid:
                bid_price = max(bid_price, bp)
                break

        # Underbid: find the lowest existing ask above wall_mid with size > 1
        for sp, sv in self.mkt_sell_orders.items():
            if sv > 1 and sp - 1 > self.wall_mid:
                ask_price = min(ask_price, sp - 1)
                break
            elif sp > self.wall_mid:
                ask_price = min(ask_price, sp)
                break

        self.bid(bid_price, self.max_buy_vol)
        self.ask(ask_price, self.max_sell_vol)

        return {self.name: self.orders}


# ══════════════════════════════════════════════════════════════════════════════
# DYNAMIC TRADER  (TOMATOES / Kelp)
# Wall-mid market making with Olivia signal overlay.
# When Olivia bought recently → lean bullish (bigger bids, tighter asks).
# When Olivia sold  recently → lean bearish (bigger asks, tighter bids).
# ══════════════════════════════════════════════════════════════════════════════

OLIVIA_SIGNAL_WINDOW = 500   # ticks: how long Olivia's signal stays active
OLIVIA_TARGET_POS    = 40    # position to hold when following Olivia

class DynamicTrader(ProductTrader):

    def __init__(self, state, prints, new_trader_data):
        super().__init__(DYNAMIC_SYMBOL, state, prints, new_trader_data)
        self.informed_dir, self.bought_ts, self.sold_ts = self.check_for_informed()

    def get_orders(self) -> dict:
        if self.wall_mid is None:
            return {}

        ts = self.state.timestamp

        # ── BID SIDE ─────────────────────────────────────────────────────────
        bid_price  = self.bid_wall + 1
        bid_volume = self.max_buy_vol

        if self.bought_ts is not None and self.bought_ts + OLIVIA_SIGNAL_WINDOW >= ts:
            # Olivia recently bought → aggressively build a long position
            if self.initial_position < OLIVIA_TARGET_POS:
                bid_price  = self.ask_wall                        # take the ask wall
                bid_volume = OLIVIA_TARGET_POS - self.initial_position
        else:
            # No bull signal — if we're in a bear signal, don't bid past wall
            if (self.wall_mid - bid_price < 1 and
                    self.informed_dir == SHORT and
                    self.initial_position > -OLIVIA_TARGET_POS):
                bid_price = self.bid_wall

        self.bid(bid_price, bid_volume)

        # ── ASK SIDE ─────────────────────────────────────────────────────────
        ask_price  = self.ask_wall - 1
        ask_volume = self.max_sell_vol

        if self.sold_ts is not None and self.sold_ts + OLIVIA_SIGNAL_WINDOW >= ts:
            # Olivia recently sold → aggressively build a short position
            if self.initial_position > -OLIVIA_TARGET_POS:
                ask_price  = self.bid_wall                        # hit the bid wall
                ask_volume = OLIVIA_TARGET_POS + self.initial_position
        else:
            # No bear signal — if we're in a bull signal, don't ask below wall
            if (ask_price - self.wall_mid < 1 and
                    self.informed_dir == LONG and
                    self.initial_position < OLIVIA_TARGET_POS):
                ask_price = self.ask_wall

        self.ask(ask_price, ask_volume)

        return {self.name: self.orders}


# ══════════════════════════════════════════════════════════════════════════════
# TOMATO TRADER  (TOMATOES — mean-reversion market maker)
#
# From analyze.py output:
#   Hurst = 0.254  → mean-reverting
#   AR(1) half-life = 161 ticks  → inventory should flip within ~241 ticks
#   Optimal EMA alpha = 0.4
#   σ = 14.58,  Z-score entry threshold = ±1.5σ
#   OBI predictive r = 0.314  → skew quotes toward order-book pressure
#   Recommended spread = 7-10 ticks
#
# Logic:
#   1. Update EMA(α=0.4) each tick → fair value
#   2. Z = (mid − EMA) / σ
#      |Z| > 1.5 → aggressively take the book on the reversion side
#   3. Passive quotes at EMA ± SPREAD_HALF
#      shifted by OBI signal + inventory skew
# ══════════════════════════════════════════════════════════════════════════════

TOMATO_EMA_ALPHA   = 0.7
TOMATO_SIGMA       = 14.58   # σ from historical data (fixed — more stable than rolling)
TOMATO_Z_ENTRY     = 1.0    # |Z| threshold to take aggressively
TOMATO_SPREAD_HALF = 6       # half-spread → total spread = 8 (within recommended 7-10)
TOMATO_OBI_SKEW    = 0.0     # ticks to shift quotes per unit of OBI  (OBI ∈ [-1,+1])
TOMATO_INV_SKEW    = 2.0     # max ticks to shift quotes for inventory management


class TomatoTrader(ProductTrader):
    """
    Mean-reversion market maker for TOMATOES.

    Quote skew formula:
        total_shift = obi_shift + inv_shift
        obi_shift   = OBI × TOMATO_OBI_SKEW
            positive OBI (buy pressure) → shift quotes UP  (buy less, sell higher)
            negative OBI (sell pressure) → shift quotes DOWN
        inv_shift   = -(pos / limit) × TOMATO_INV_SKEW
            long position → shift DOWN  (discourage more buys, sell cheaper)
            short position → shift UP   (discourage more sells, buy dearer)

        bid = EMA − SPREAD_HALF + total_shift
        ask = EMA + SPREAD_HALF + total_shift
    """

    def __init__(self, state, prints, new_trader_data):
        super().__init__(DYNAMIC_SYMBOL, state, prints, new_trader_data)

    def _obi(self) -> float:
        """Level-1 order book imbalance: (bid_vol − ask_vol) / (bid_vol + ask_vol)."""
        bv = self.mkt_buy_orders.get(self.best_bid, 0) if self.best_bid else 0
        av = self.mkt_sell_orders.get(self.best_ask, 0) if self.best_ask else 0
        total = bv + av
        return (bv - av) / total if total > 0 else 0.0

    def get_orders(self) -> dict:
        if self.wall_mid is None:
            return {}

        mid   = self.wall_mid
        pos   = self.initial_position
        limit = self.position_limit

        # ── EMA (persisted across ticks) ──────────────────────────────────────
        key     = f'{self.name}_ema'
        old_ema = self.last_trader_data.get(key, mid)
        ema_val = TOMATO_EMA_ALPHA * mid + (1 - TOMATO_EMA_ALPHA) * old_ema
        self.new_trader_data[key] = ema_val

        # ── Z-score ───────────────────────────────────────────────────────────
        z   = (mid - ema_val) / TOMATO_SIGMA
        obi = self._obi()

        # ── Phase 1: Aggressive taking on extreme Z ───────────────────────────
        # Z > +1.5: price is high, expect reversion down → sell into existing bids
        if z > TOMATO_Z_ENTRY:
            entry_thr = ema_val + TOMATO_Z_ENTRY * TOMATO_SIGMA
            for bp, bv in self.mkt_buy_orders.items():
                if bp >= entry_thr:
                    self.ask(bp, bv, logging=False)

        # Z < -1.5: price is low, expect reversion up → buy from existing asks
        elif z < -TOMATO_Z_ENTRY:
            entry_thr = ema_val - TOMATO_Z_ENTRY * TOMATO_SIGMA
            for sp, sv in self.mkt_sell_orders.items():
                if sp <= entry_thr:
                    self.bid(sp, sv, logging=False)

        # ── Phase 2: Passive market making with skews ─────────────────────────
        obi_shift = obi * TOMATO_OBI_SKEW
        inv_shift = -(pos / limit) * TOMATO_INV_SKEW
        shift     = obi_shift + inv_shift

        bid_price = round(ema_val - TOMATO_SPREAD_HALF + shift)
        ask_price = round(ema_val + TOMATO_SPREAD_HALF + shift)

        # Never cross the spread
        if bid_price >= ask_price:
            bid_price = round(ema_val) - 1
            ask_price = round(ema_val) + 1

        # Don't passively bid above best_ask or ask below best_bid
        if self.best_ask is not None and bid_price >= self.best_ask:
            bid_price = self.best_ask - 1
        if self.best_bid is not None and ask_price <= self.best_bid:
            ask_price = self.best_bid + 1

        # Size: skew toward the side that reduces inventory
        if pos > limit * 0.5:       # overlong → prioritise selling
            bid_size = max(1, self.max_buy_vol  // 3)
            ask_size = self.max_sell_vol
        elif pos < -limit * 0.5:    # overshort → prioritise buying
            bid_size = self.max_buy_vol
            ask_size = max(1, self.max_sell_vol // 3)
        else:
            bid_size = self.max_buy_vol
            ask_size = self.max_sell_vol

        self.bid(bid_price, bid_size)
        self.ask(ask_price, ask_size)

        self.log('EMA',    round(ema_val,  2))
        self.log('Z',      round(z,        3))
        self.log('OBI',    round(obi,      3))
        self.log('SHIFT',  round(shift,    2))
        self.log('QUOTES', [bid_price, ask_price])

        return {self.name: self.orders}


# ══════════════════════════════════════════════════════════════════════════════
# INK TRADER  (SQUID_INK or similar high-volatility product)
# Pure Olivia follower: hold max long when Olivia bought, max short when sold.
# ══════════════════════════════════════════════════════════════════════════════

class InkTrader(ProductTrader):

    def __init__(self, state, prints, new_trader_data):
        super().__init__(INK_SYMBOL, state, prints, new_trader_data)
        self.informed_dir, _, _ = self.check_for_informed()

    def get_orders(self) -> dict:
        target = {
            LONG:    self.position_limit,
            SHORT:  -self.position_limit,
            NEUTRAL: 0,
        }[self.informed_dir]

        delta = target - self.initial_position

        if delta > 0 and self.ask_wall is not None:
            self.bid(self.ask_wall, delta)
        elif delta < 0 and self.bid_wall is not None:
            self.ask(self.bid_wall, -delta)

        return {self.name: self.orders}


# ══════════════════════════════════════════════════════════════════════════════
# ETF TRADER  (PICNIC_BASKET1/2 + constituents CROISSANTS/JAMS/DJEMBES)
# Spread arbitrage: ETF price vs weighted component prices.
# Uses a running mean premium to account for structural ETF premium.
# Olivia's constituent signal shifts entry threshold.
# 50% hedge ratio on constituents.
# ══════════════════════════════════════════════════════════════════════════════

class EtfTrader:

    def __init__(self, state, prints, new_trader_data):
        self.state           = state
        self.prints          = prints
        self.new_trader_data = new_trader_data

        pg = 'ETF'
        self.baskets = [ProductTrader(s, state, prints, new_trader_data, pg)
                        for s in ETF_BASKET_SYMBOLS]

        self.informed_constituent = ProductTrader(
            ETF_INFORMED_CONSTITUENT, state, prints, new_trader_data, pg)

        self.hedging_constituents = [
            ProductTrader(s, state, prints, new_trader_data, pg)
            for s in ETF_CONSTITUENT_SYMBOLS if s != ETF_INFORMED_CONSTITUENT
        ]

        self.last_trader_data = self.informed_constituent.last_trader_data

        self.informed_dir, _, _ = self.informed_constituent.check_for_informed()
        self.spreads = [self._calc_spread(basket) for basket in self.baskets]

    def _calc_spread(self, basket) -> float | None:
        b_idx = ETF_BASKET_SYMBOLS.index(basket.name)
        try:
            # Sort constituents into the canonical ETF order
            all_consts = [self.informed_constituent] + self.hedging_constituents
            ordered = sorted(all_consts,
                             key=lambda c: ETF_CONSTITUENT_SYMBOLS.index(c.name))  # BUG FIX 1

            const_prices = [c.wall_mid for c in ordered]
            if any(p is None for p in const_prices) or basket.wall_mid is None:
                raise ValueError("missing wall_mid")

            index_price = float(np.dot(const_prices, ETF_CONSTITUENT_FACTORS[b_idx]))
            raw_spread  = basket.wall_mid - index_price

            if CALCULATE_RUNNING_ETF_PREMIUM:
                premium, n = self.last_trader_data.get(
                    f'ETF_{b_idx}_P', [INITIAL_ETF_PREMIUMS[b_idx], N_HIST_SAMPLES])
                n += 1
                premium += (raw_spread - premium) / n
                self.new_trader_data[f'ETF_{b_idx}_P'] = [premium, n]
            else:
                premium = INITIAL_ETF_PREMIUMS[b_idx]

            spread = raw_spread - premium
            basket.log(f'ETF_{b_idx}_SPREAD', round(spread, 2))
            return spread

        except Exception:
            # Preserve last premium estimate across ticks
            self.new_trader_data[f'ETF_{b_idx}_P'] = self.last_trader_data.get(
                f'ETF_{b_idx}_P', [INITIAL_ETF_PREMIUMS[b_idx], N_HIST_SAMPLES])
            return None

    def _get_basket_orders(self) -> dict:
        out = {}
        for b_idx, basket in enumerate(self.baskets):
            spread = self.spreads[b_idx]       # BUG FIX 2: index by int, not name
            if spread is None:
                continue

            # Shift threshold when Olivia is active on constituents
            thr_adj = {LONG: ETF_THR_INFORMED_ADJS[b_idx],
                       SHORT: -ETF_THR_INFORMED_ADJS[b_idx]}.get(self.informed_dir, 0)
            thr = BASKET_THRESHOLDS[b_idx]

            if spread > thr + thr_adj and basket.max_sell_vol > 0:
                # ETF overpriced vs components → sell basket
                basket.ask(basket.bid_wall, basket.max_sell_vol)
                basket.expected_position -= min(basket.total_mkt_sell_vol, basket.max_sell_vol)

            elif spread < -(thr) + thr_adj and basket.max_buy_vol > 0:
                # ETF underpriced vs components → buy basket
                basket.bid(basket.ask_wall, basket.max_buy_vol)
                basket.expected_position += min(basket.total_mkt_buy_vol, basket.max_buy_vol)

            elif ETF_CLOSE_AT_ZERO:
                # Spread near zero — close any existing position
                if spread > thr_adj and basket.initial_position > 0:
                    basket.ask(basket.bid_wall, basket.initial_position)
                    basket.expected_position -= min(basket.total_mkt_sell_vol,
                                                    basket.initial_position)
                elif spread < thr_adj and basket.initial_position < 0:
                    basket.bid(basket.ask_wall, -basket.initial_position)
                    basket.expected_position += min(basket.total_mkt_buy_vol,
                                                    -basket.initial_position)

            out[basket.name] = basket.orders
        return out

    def _get_constituent_orders(self) -> dict:
        # Informed constituent: follow Olivia signal
        ic = self.informed_constituent
        ic_target = {LONG: ic.position_limit, SHORT: -ic.position_limit,
                     NEUTRAL: 0}[self.informed_dir]
        delta = ic_target - ic.initial_position
        if delta > 0:
            ic.bid(ic.ask_wall, delta)
        elif delta < 0:
            ic.ask(ic.bid_wall, -delta)

        out = {ic.name: ic.orders}

        # Hedging constituents: hedge 50% of basket expected position
        for hc in self.hedging_constituents:
            hedge_target = 0
            for b_idx, basket in enumerate(self.baskets):
                factor = ETF_CONSTITUENT_FACTORS[b_idx][ETF_CONSTITUENT_SYMBOLS.index(hc.name)]
                hedge_target += -basket.expected_position * factor * ETF_HEDGE_FACTOR

            delta = round(hedge_target - hc.initial_position)
            if delta > 0 and hc.ask_wall is not None:
                hc.bid(hc.ask_wall, delta)
            elif delta < 0 and hc.bid_wall is not None:
                hc.ask(hc.bid_wall, -delta)

            out[hc.name] = hc.orders

        return out

    def get_orders(self) -> dict:
        # Basket orders first, then hedges (order matters for fills)
        return {**self._get_basket_orders(), **self._get_constituent_orders()}


# ══════════════════════════════════════════════════════════════════════════════
# OPTION TRADER  (VOLCANIC_ROCK + vouchers)
# Black-Scholes pricing with parabolic IV smile fitted from data.
# Two strategies:
#   IV Scalping  — trade when current IV deviates significantly from EMA
#   Mean Reversion — trade underlying + options when price deviates from EMA
# ══════════════════════════════════════════════════════════════════════════════

class OptionTrader:

    def __init__(self, state, prints, new_trader_data):
        self.state           = state
        self.prints          = prints
        self.new_trader_data = new_trader_data

        pg = 'OPTION'
        self.options    = [ProductTrader(s, state, prints, new_trader_data, pg)
                           for s in OPTION_SYMBOLS]
        self.underlying = ProductTrader(OPTION_UNDERLYING_SYMBOL, state, prints,
                                        new_trader_data, pg)

        self.last_trader_data = self.underlying.last_trader_data
        self.indicators = self._calc_indicators()

    # ── Black-Scholes + IV smile ─────────────────────────────────────────────

    @staticmethod
    def _fitted_iv(S: float, K: float, TTE: float) -> float:
        """Parabolic IV smile: iv = a·m² + b·m + c  where m = ln(K/S)/√TTE."""
        m = math.log(K / S) / math.sqrt(TTE)
        return float(np.poly1d(IV_SMILE_COEFFS)(m))

    @staticmethod
    def _bs_call(S: float, K: float, TTE: float, sigma: float, r: float = 0):
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * TTE) / (sigma * math.sqrt(TTE))
        d2 = d1 - sigma * math.sqrt(TTE)
        price = S * _N.cdf(d1) - K * math.exp(-r * TTE) * _N.cdf(d2)
        delta = _N.cdf(d1)
        return price, delta

    @staticmethod
    def _bs_vega(S: float, K: float, TTE: float, sigma: float, r: float = 0):
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * TTE) / (sigma * math.sqrt(TTE))
        return S * _N.pdf(d1) * math.sqrt(TTE)

    def _get_option_values(self, S, K, TTE):
        iv    = self._fitted_iv(S, K, TTE)
        price, delta = self._bs_call(S, K, TTE, iv)
        vega  = self._bs_vega(S, K, TTE, iv)
        return price, delta, vega

    def _update_ema(self, key: str, window: int, value: float) -> float:
        alpha   = 2 / (window + 1)
        old_val = self.last_trader_data.get(key, 0)
        new_val = alpha * value + (1 - alpha) * old_val
        self.new_trader_data[key] = new_val
        return new_val

    # ── Indicator computation ────────────────────────────────────────────────

    def _calc_indicators(self) -> dict:
        ind = {
            'ema_u_dev':         None,
            'ema_o_dev':         None,
            'current_theo_diffs': {},
            'mean_theo_diffs':    {},
            'switch_means':       {},   # BUG FIX 3: was self.new_switch_mean (undefined)
            'deltas':             {},
            'vegas':              {},   # BUG FIX 4: was self.vegas (undefined)
        }

        if self.underlying.wall_mid is None:
            return ind

        S = self.underlying.wall_mid

        # EMA deviations on the underlying (two different windows for different signals)
        ema_u = self._update_ema('ema_u', UNDERLYING_MR_WINDOW, S)
        ema_o = self._update_ema('ema_o', OPTIONS_MR_WINDOW,    S)
        ind['ema_u_dev'] = S - ema_u
        ind['ema_o_dev'] = S - ema_o

        for option in self.options:
            K = int(option.name.split('_')[-1])

            # Handle one-sided books by synthesising a wall_mid
            if option.wall_mid is None:
                if option.ask_wall is not None:
                    option.wall_mid  = option.ask_wall - 0.5
                    option.bid_wall  = option.ask_wall - 1
                    option.best_bid  = option.ask_wall - 1
                elif option.bid_wall is not None:
                    option.wall_mid  = option.bid_wall + 0.5
                    option.ask_wall  = option.bid_wall + 1
                    option.best_ask  = option.bid_wall + 1

            if option.wall_mid is None:
                continue

            # Time to expiry in years
            TTE = 1 - (DAYS_PER_YEAR - 8 + DAY + self.state.timestamp // 100 / 10_000) / DAYS_PER_YEAR
            if TTE <= 0:
                continue

            mid_S = ((self.underlying.best_bid or S) * 0.5 +
                     (self.underlying.best_ask or S) * 0.5)

            theo, delta, vega = self._get_option_values(mid_S, K, TTE)
            diff = option.wall_mid - theo

            ind['current_theo_diffs'][option.name] = diff
            ind['deltas'][option.name]             = delta
            ind['vegas'][option.name]              = vega

            ind['mean_theo_diffs'][option.name]    = self._update_ema(
                f'{option.name}_theo_diff', THEO_NORM_WINDOW, diff)

            ind['switch_means'][option.name]       = self._update_ema(
                f'{option.name}_avg_devs', IV_SCALPING_WINDOW,
                abs(diff - ind['mean_theo_diffs'][option.name]))

        return ind

    # ── IV Scalping ──────────────────────────────────────────────────────────

    def _iv_scalping_orders(self, options) -> dict:
        out = {}
        for option in options:
            name = option.name
            if (name not in self.indicators['mean_theo_diffs'] or
                    name not in self.indicators['current_theo_diffs'] or
                    name not in self.indicators['switch_means']):  # BUG FIX 3
                continue

            switch_mean = self.indicators['switch_means'][name]   # BUG FIX 3

            if switch_mean >= IV_SCALPING_THR:
                cur  = self.indicators['current_theo_diffs'][name]
                mean = self.indicators['mean_theo_diffs'][name]
                vega = self.indicators['vegas'].get(name, 0)       # BUG FIX 4
                low_vega_adj = LOW_VEGA_THR_ADJ if vega <= 1 else 0

                bid, ask = option.best_bid, option.best_ask

                # Option looks expensive → sell
                if (cur - option.wall_mid + bid - mean >= THR_OPEN + low_vega_adj
                        and option.max_sell_vol > 0):
                    option.ask(bid, option.max_sell_vol)
                if (cur - option.wall_mid + bid - mean >= THR_CLOSE
                        and option.initial_position > 0):
                    option.ask(bid, option.initial_position)

                # Option looks cheap → buy
                elif (cur - option.wall_mid + ask - mean <= -(THR_OPEN + low_vega_adj)
                      and option.max_buy_vol > 0):
                    option.bid(ask, option.max_buy_vol)
                if (cur - option.wall_mid + ask - mean <= -THR_CLOSE
                        and option.initial_position < 0):
                    option.bid(ask, -option.initial_position)

            else:
                # Signal too weak → close position
                if option.initial_position > 0:
                    option.ask(option.best_bid, option.initial_position)
                elif option.initial_position < 0:
                    option.bid(option.best_ask, -option.initial_position)

            out[name] = option.orders
        return out

    # ── Mean Reversion ───────────────────────────────────────────────────────

    def _mr_orders(self, options) -> dict:
        out = {}
        for option in options:
            name = option.name
            if (name not in self.indicators['current_theo_diffs'] or
                    self.indicators.get('ema_o_dev') is None):
                continue

            cur_dev  = self.indicators['ema_o_dev']
            iv_dev   = (self.indicators['current_theo_diffs'][name] -
                        self.indicators['mean_theo_diffs'].get(name, 0))
            total_dev = cur_dev + iv_dev

            if total_dev > OPTIONS_MR_THR and option.max_sell_vol > 0:
                option.ask(option.best_bid, option.max_sell_vol)
            elif total_dev < -OPTIONS_MR_THR and option.max_buy_vol > 0:
                option.bid(option.best_ask, option.max_buy_vol)

            out[name] = option.orders
        return out

    def _option_orders(self) -> dict:
        warmup = min(THEO_NORM_WINDOW, UNDERLYING_MR_WINDOW, OPTIONS_MR_WINDOW)
        if self.state.timestamp / 100 < warmup:
            return {}
        iv_options = [o for o in self.options if int(o.name.split('_')[-1]) >= 9750]
        mr_options  = [o for o in self.options if o.name.endswith('9500')]
        return {**self._iv_scalping_orders(iv_options), **self._mr_orders(mr_options)}

    def _underlying_orders(self) -> dict:
        if self.state.timestamp / 100 < UNDERLYING_MR_WINDOW:
            return {}
        dev = self.indicators.get('ema_u_dev')   # BUG FIX 5: was ema_o_dev
        if dev is None:
            return {}
        u = self.underlying
        if dev > UNDERLYING_MR_THR and u.max_sell_vol > 0:
            u.ask(u.bid_wall + 1, u.max_sell_vol)
        elif dev < -UNDERLYING_MR_THR and u.max_buy_vol > 0:
            u.bid(u.ask_wall - 1, u.max_buy_vol)
        return {u.name: u.orders}

    def get_orders(self) -> dict:
        # Options first, then underlying hedge
        return {**self._option_orders(), **self._underlying_orders()}


# ══════════════════════════════════════════════════════════════════════════════
# COMMODITY TRADER  (MAGNIFICENT_MACARONS)
# Conversion arbitrage between local market and external exchange.
# Formula:
#   short_arb = local_sell − (ex_ask + import_tariff + transport_fees)
#   long_arb  = (ex_bid − export_tariff − transport_fees) − local_buy
# Use conversions to flatten position at end of each tick.
# ══════════════════════════════════════════════════════════════════════════════

ARB_HISTORY_WINDOW = 10   # ticks of arb history to smooth over
MIN_ARB_CAPTURE    = 0.58  # only take bids/asks that capture ≥58% of the arb

class CommodityTrader(ProductTrader):

    def __init__(self, state, prints, new_trader_data):
        super().__init__(COMMODITY_SYMBOL, state, prints, new_trader_data)
        self.conversions = 0

    def get_orders(self) -> dict:
        try:
            obs = self.state.observations.conversionObservations[self.name]
        except Exception:
            return {}

        ex_bid_raw  = obs.bidPrice
        ex_ask_raw  = obs.askPrice
        transport   = obs.transportFees
        export_tar  = obs.exportTariff
        import_tar  = obs.importTariff

        # Effective exchange prices after fees
        ex_ask = ex_ask_raw + import_tar + transport
        ex_bid = ex_bid_raw - export_tar  - transport

        # Local prices where the hidden taker bot fills
        local_sell = math.floor(ex_bid_raw + 0.5)  # we sell here, bot buys
        local_buy  = math.ceil(ex_ask_raw  - 0.5)  # we buy  here, bot sells

        short_arb = round(local_sell - ex_ask, 1)  # profit from sell-local/buy-exchange
        long_arb  = round(ex_bid     - local_buy - 0.1, 1)  # profit from buy-local/sell-exchange

        # Smooth over recent history to avoid one-tick noise
        short_hist = self.last_trader_data.get('SA', [])
        long_hist  = self.last_trader_data.get('LA', [])
        short_hist = (short_hist + [short_arb])[-ARB_HISTORY_WINDOW:]
        long_hist  = (long_hist  + [long_arb ])[-ARB_HISTORY_WINDOW:]
        self.new_trader_data['SA'] = short_hist
        self.new_trader_data['LA'] = long_hist

        mean_short = float(np.mean(short_hist))
        mean_long  = float(np.mean(long_hist))

        if short_arb > long_arb:
            if short_arb >= 0 and mean_short > 0:
                # Short arbitrage: sell locally, convert (buy from exchange)
                remaining = CONVERSION_LIMIT
                for bp, bv in self.mkt_buy_orders.items():
                    capture = short_arb - (local_sell - bp)
                    if capture > MIN_ARB_CAPTURE * short_arb:
                        v = min(remaining, bv)
                        self.ask(bp, v)
                        remaining -= v
                    else:
                        break
                if remaining > 0:
                    self.ask(local_sell, remaining)
        else:
            if long_arb >= 0 and mean_long > 0:
                # Long arbitrage: buy locally, convert (sell to exchange)
                remaining = CONVERSION_LIMIT
                for ap, av in self.mkt_sell_orders.items():
                    capture = long_arb - (ap - local_buy)
                    if capture > MIN_ARB_CAPTURE * long_arb:
                        v = min(remaining, av)
                        self.bid(ap, v)
                        remaining -= v
                    else:
                        break
                if remaining > 0:
                    self.bid(local_buy, remaining)

        # Convert to flatten position (up to CONVERSION_LIMIT per tick)
        self.conversions = max(min(-self.initial_position, CONVERSION_LIMIT), -CONVERSION_LIMIT)

        self.log('EX_BID',   ex_bid_raw)
        self.log('EX_ASK',   ex_ask_raw)
        self.log('FEES',      [import_tar, export_tar, transport])
        self.log('ARB',       [long_arb, short_arb])
        self.log('MEAN_ARB',  [round(mean_long, 2), round(mean_short, 2)])
        self.log('SUN_SUGAR', [obs.sunlightIndex, obs.sugarPrice])

        return {self.name: self.orders}

    def get_conversions(self) -> int:
        return self.conversions


# ══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

class Trader:
    """
    Routes each product to its trader class.
    To activate a new product: add its symbol to PRODUCT_TRADERS below.
    ETF, Option, and Commodity traders handle multiple symbols at once —
    their key is the first symbol that triggers them.
    """

    def bid(self) -> int:
        """Required stub for Round 2 auction. Update when spec is released."""
        return 0

    def run(self, state: TradingState):
        result: dict[str, list[Order]] = {}
        new_trader_data = {}
        prints = {'GENERAL': {'TS': state.timestamp, 'POS': state.position}}

        # ── Active traders — comment/uncomment per round ─────────────────────
        PRODUCT_TRADERS = {
            STATIC_SYMBOL:           StaticTrader,     # EMERALDS  (active Round 0)
            DYNAMIC_SYMBOL:          TomatoTrader,     # TOMATOES  mean-reversion MM
            # INK_SYMBOL:            InkTrader,        # activate when product appears
            # ETF_BASKET_SYMBOLS[0]: EtfTrader,        # activate when baskets appear
            # OPTION_UNDERLYING_SYMBOL: OptionTrader,  # activate when options appear
            # COMMODITY_SYMBOL:      CommodityTrader,  # activate when Macarons appear
        }

        conversions = 0

        for symbol, TraderClass in PRODUCT_TRADERS.items():
            if symbol not in state.order_depths:
                continue
            try:
                trader = TraderClass(state, prints, new_trader_data)
                result.update(trader.get_orders())
                if symbol == COMMODITY_SYMBOL:
                    conversions = trader.get_conversions()
            except Exception as e:
                prints.setdefault('ERRORS', {})[symbol] = str(e)

        try:
            trader_data = json.dumps(new_trader_data)
        except Exception:
            trader_data = ''

        try:
            print(json.dumps(prints))
        except Exception:
            pass

        return result, conversions, trader_data
