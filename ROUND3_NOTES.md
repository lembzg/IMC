# Round 3 — Research Notes & Current Strategy
*Written at end of session. Pick up from here next time.*

---

## Products in Round 3

| Product | Type | Pos limit | Notes |
|---|---|---|---|
| `VELVETFRUIT_EXTRACT` | Spot underlying | 200 | S ≈ 5198–5300 |
| `VEV_4000` – `VEV_6500` | European call options | 300 each | Strikes 4000–6500 |
| `HYDROGEL_PACK` | Separate product | 200 | Handled in `trader.py`, not touched here |

---

## Frankfurt Hedgehogs (2nd place, Prosperity 3) — What they actually did

Source: https://github.com/TimoDiehm/imc-prosperity-3

Their Round 3 strategy (Volcanic Rock Vouchers ≈ our VEV options):
1. **Fitted a volatility smile** across all strikes each tick
2. Found **negative lag-1 autocorrelation in IV** (−0.50) → mean-reversion signal
3. Traded options whose IV deviated from the fitted smile
4. Called it "IV scalping" — earned ~100–150k SeaShells in that round

---

## What we tried and why it failed

### Attempt 1 — IV smile fitting (v1, v2)
- Fit quadratic IV vs log-moneyness across all strikes
- Problem: vol surface is essentially **flat** (all options at the same IV ≈ 0.112 at start)
- Including VEV_5300 in the fit contaminated the curve → made VEV_5000/5100 look artificially cheap → bought them → lost on the wide spread
- **Result: −196k**

### Attempt 2 — Per-option IV EMA mean reversion (v3)
- Track per-option slow IV EMA, trade when IV deviates
- Problem: threshold of 0.010 IV units exceeded the p99 of actual ΔIV for VEV_5200–5500
  - VEV_5100 p90 = 0.005, VEV_5300 p90 = 0.002 (all tiny)
  - Only VEV_5000 fired — and it's numerically unstable (deep ITM, IV explodes)
- **Result: −26k**

### Attempt 3 — BS fair value using spot_mid (v4)
- `fair = bs_call(spot_mid, K, T, iv_ema)`
- First version used `spot_ema` instead of `spot_mid` → options always look expensive when spot rising, always cheap when falling → trend-fighting disaster
- After fix to spot_mid: IV EMA starts at 0.112 but market IV rises to 0.165 as TTE decreases → iv_ema stale → all options look expensive → sell everything → pay spread repeatedly
- **Result: −44k to −142k depending on version**

---

## What actually works — The real edge

### Key data findings (confirmed with py_vollib in `vev_analysis.py`)

| Finding | Value |
|---|---|
| Vol surface at t=0 | Completely flat — all options IV ≈ 0.112 |
| Vol surface at end of round | IV ≈ 0.88–0.90 (TTE compression, not tradeable via smile) |
| Lag-1 IV autocorrelation | **−0.49 to −0.51** across VEV_5100–5500 |
| Spot lag-1 return ACF | −0.16 (weak, lags 2+ ≈ 0) |
| VEV_5400 persistent BS deviation | −2.63 price units (structurally cheap vs ATM ref) |
| VEV_5300 persistent BS deviation | +0.33 (slightly expensive) |
| VEV_5500 persistent BS deviation | +0.57 (slightly expensive) |

### Why the simple EMA approach wins

The option prices **mean-revert around their initial fair value** throughout the round. When spot makes large moves, ITM options (VEV_4000–5100) reprice by 30–80 units. The strategy:
- Anchors a reference price at the initial observed price (via near-zero ALPHA_SLOW)
- Sells when current price is above the anchor → captures the overshot
- Buys when current price is below the anchor → captures the undershoot

For VEV_5400/5500 (OTM, spread=1): earns the small oscillation premium.
For VEV_4000–5100 (ITM, spread 5–20): earns huge swings when spot moves 30–80 units — spread cost is trivial.

### Spread breakdown (day 0, p50)
| Option | Spread |
|---|---|
| VEV_4000 | ~20 |
| VEV_4500 | ~16 |
| VEV_5000 | ~6 |
| VEV_5100 | 4–5 |
| VEV_5200 | 3 |
| VEV_5300 | 2 |
| VEV_5400 | 1 |
| VEV_5500 | 1 |

### Why spot trading loses
- Spread is 5–6 wide
- Slow EMA fights intra-day trends (e.g., day 1 spot swings 5198–5283)
- Every version of spot MM lost −2k to −7.5k per day
- **Skip spot trading entirely**

---

## Current strategy: `trader_vev_smile.py`

### Final parameters (grid-searched)
```python
OPT_LIMITS = {
    "VEV_4000": 300, "VEV_4500": 300,
    "VEV_5000": 300, "VEV_5100": 300,
    "VEV_5200": 300, "VEV_5300": 300,
    "VEV_5400": 300, "VEV_5500": 300,
}
ALPHA_FAST    = 0.97    # fast EMA (momentum — rarely fires with threshold 8)
ALPHA_SLOW    = 0.0001  # near-constant — anchors at initial price level
EXT_ALPHA     = 0.01    # extrinsic EMA alpha
EXT_THR       = 10.0    # extrinsic deviation threshold
MARGIN        = 0.01    # basically 0 — fires whenever price ≠ EMA
OPT_TRADE_QTY = 1       # 1 lot per signal — maximises signal frequency
STOP_LOSS     = -10000  # per-product stop-loss on own_trades P&L
```

### Backtest results (all 3 round-3 days, prosperity4btest)
| Day | P&L |
|---|---|
| Day 0 | +20,114 |
| Day 1 | +35,633 |
| Day 2 | +14,088 |
| **Total** | **+69,835** |
| Sharpe | 2.09 (annualised 33.2) |
| Max drawdown | 14,256 |
| Calmar | 4.90 |

Compare: original `trader_vev.py` = **−24,019** on same data.

### Per-product contribution (typical day 1)
| Product | P&L |
|---|---|
| VEV_4000 | +3,004 |
| VEV_4500 | +3,653 |
| VEV_5000 | +7,473 |
| VEV_5100 | +8,385 |
| VEV_5200 | +6,548 |
| VEV_5300 | +4,311 |
| VEV_5400 | +1,831 |
| VEV_5500 | +428 |

### Parameter sweep findings
- `ALPHA_SLOW`: plateau at ≤0.0001 (any smaller is equivalent — EMA barely moves)
- `OPT_TRADE_QTY`: lower is better (1 < 3 < 5 < 10 < 15 < 30) — smaller qty prevents hitting position limit and allows more signals
- `EXT_THR`: plateau at ≥10 (higher = same); 5 is too low (noise)
- VEV_6000/6500: no fills (bid=0, ask=1), skip

---

## File inventory

| File | Status | Notes |
|---|---|---|
| `trader.py` | Active submission | Handles HYDROGEL_PACK + VELVETFRUIT_EXTRACT + VEV options (original strategy) |
| `trader_vev_smile.py` | **New — ready to merge** | Improved VEV strategy, +69k |
| `trader_vev.py` | Old baseline | Original VEV strategy, −24k |
| `vev_analysis.py` | Analysis only | Uses py_vollib; NOT for submission |
| `backtester.py` | Backtesting tool | Points to `trader_diagnostic.py` by default; change `TRADER_FILE` |
| `data_bt/round3/` | Data | 6 CSVs (prices + trades, days 0–1–2) |

---

## How to run backtests

```bash
# Single file, all 3 days
prosperity4btest trader_vev_smile.py 3-0 3-1 3-2 --no-out --data data_bt

# Specific day
prosperity4btest trader_vev_smile.py 3-1 --no-out --data data_bt

# With visualiser
prosperity4btest trader_vev_smile.py 3-1 --data data_bt --vis
```

Run analysis:
```bash
python3 vev_analysis.py
```

---

## Current `trader.py` backtest results (post-merge)

| Day | VEV P&L | HYDRO P&L | Spot P&L | Total |
|---|---|---|---|---|
| Day 0 | ~+18k | ~+16k | ~−2k | +32,250 |
| Day 1 | +35,620 | +6,880 | ~−2k | +39,634 |
| Day 2 | ~+12k | +15,852 | −2,866 | +27,074 |
| **Total** | | | | **+98,958** |

Sharpe: 5.23 (annualised 82.9) | Max drawdown: 16,184 | Calmar: 6.11

---

## TODO / What to try next

1. ~~**Merge `trader_vev_smile.py` into `trader.py`**~~ **DONE** — `trader.py` now uses ALPHA_SLOW=0.0001 and OPT_TRADE_QTY=1. Total +98,958.

2. **Per-product ALPHA_SLOW tuning**
   - Currently one global ALPHA_SLOW for all products
   - Deeper ITM options (4000/4500) might benefit from a slightly faster anchor to avoid stale reference when the option decays significantly

3. **Asymmetric sizing**
   - Size up on ITM options (bigger swings per unit = more alpha per trade)
   - Size down on OTM options (smaller swings, need more precision)

4. **Investigate VEV_5400 structural cheapness**
   - Section 5 shows VEV_5400 has mean BS deviation of −2.63 (always cheap vs ATM ref)
   - Could lean into this: buy VEV_5400 more aggressively, sell VEV_5300/5500 (which are +0.33/+0.57 expensive)
   - This is closer to what Frankfurt Hedgehogs intended with "smile scalping"

5. **HYDROGEL_PACK** — not explored in this session at all

6. **Spot mean reversion** — lag-1 ACF of −0.16 is real but too weak to overcome the 5–6 spread; skip unless you find a smarter entry

---

## Data structure reminder

```
data_bt/round3/
  prices_round_3_day_0.csv   # columns: day;timestamp;product;bid_price_1;...;mid_price;profit_and_loss
  trades_round_3_day_0.csv
  prices_round_3_day_1.csv
  trades_round_3_day_1.csv
  prices_round_3_day_2.csv
  trades_round_3_day_2.csv
```

Timestamps: 0 to 999,900 in steps of 100 (10,000 per day).
TTE formula used in `trader_vev_smile.py`:
```python
T = max(0.001, 0.10 * (1 - steps / 30000))
```
where `steps` is a counter that accumulates across days (persisted in traderData).
