# IMC Prosperity 4 - Trading Competition

## Project Overview
Algorithmic trading competition. We submit a single `trader.py` file containing a `Trader` class.
The exchange runs our `run()` method every iteration with market data, we return orders.

## Critical Rules
- **Position limits**: If aggregated buy(sell) orders would breach the limit, ALL orders are rejected. Always check room before ordering.
- **sell_orders quantities are NEGATIVE** in OrderDepth. Use `abs()` when calculating volumes.
- **traderData**: Only way to persist state between iterations. Max 50,000 chars. Use JSON.
- **Supported libraries**: Only stdlib + pandas, numpy, statistics, math, typing, jsonpickle. NO scipy, sklearn, etc.
- **Timeout**: 900ms per `run()` call. Keep algorithms lightweight.
- **bid() method**: Required for Round 2 auction. Include in every submission.
- **Return format**: `return result, conversions, traderData` where result is `Dict[str, List[Order]]`
- **1,000 iterations** for test submissions, **10,000** for final scoring.

## File Structure
- `datamodel.py` - Competition-provided data classes (DO NOT MODIFY)
- `trader.py` - Our submission file (this is what gets uploaded)
- `backtester.py` - Local backtesting against CSV data
- `analysis/` - Jupyter notebooks for data exploration
- `data/` - CSV data capsules from each round

## Key Classes
- `TradingState`: Contains order_depths, position, own_trades, market_trades, observations, traderData
- `OrderDepth`: buy_orders (Dict[int,int] positive qty), sell_orders (Dict[int,int] NEGATIVE qty)
- `Order(symbol, price, quantity)`: positive qty = buy, negative qty = sell
- `Trade`: Records of executed trades with buyer/seller info

## Architecture Pattern
Each product gets its own strategy method: `_trade_stable()`, `_trade_volatile_ema()`, `_trade_spread()`.
Router in `_trade_product()` maps product names to strategies. Add new products by:
1. Adding to POSITION_LIMITS dict
2. Adding to PARAMS dict  
3. Adding strategy mapping in `_trade_product()`

## Backtest Command (Round 5)
```bash
prosperity4btest trader.py 5-2 5-3 5-4 --data data --no-out \
  --limit GALAXY_SOUNDS_DARK_MATTER:10 --limit GALAXY_SOUNDS_BLACK_HOLES:10 \
  --limit GALAXY_SOUNDS_PLANETARY_RINGS:10 --limit GALAXY_SOUNDS_SOLAR_WINDS:10 \
  --limit GALAXY_SOUNDS_SOLAR_FLAMES:10 --limit SLEEP_POD_SUEDE:10 \
  --limit SLEEP_POD_LAMB_WOOL:10 --limit SLEEP_POD_POLYESTER:10 \
  --limit SLEEP_POD_NYLON:10 --limit SLEEP_POD_COTTON:10 \
  --limit MICROCHIP_CIRCLE:10 --limit MICROCHIP_OVAL:10 \
  --limit MICROCHIP_SQUARE:10 --limit MICROCHIP_RECTANGLE:10 \
  --limit MICROCHIP_TRIANGLE:10 --limit PEBBLES_XS:10 --limit PEBBLES_S:10 \
  --limit PEBBLES_M:10 --limit PEBBLES_L:10 --limit PEBBLES_XL:10 \
  --limit ROBOT_VACUUMING:10 --limit ROBOT_MOPPING:10 --limit ROBOT_DISHES:10 \
  --limit ROBOT_LAUNDRY:10 --limit ROBOT_IRONING:10 --limit UV_VISOR_YELLOW:10 \
  --limit UV_VISOR_AMBER:10 --limit UV_VISOR_ORANGE:10 --limit UV_VISOR_RED:10 \
  --limit UV_VISOR_MAGENTA:10 --limit TRANSLATOR_SPACE_GRAY:10 \
  --limit TRANSLATOR_ASTRO_BLACK:10 --limit TRANSLATOR_ECLIPSE_CHARCOAL:10 \
  --limit TRANSLATOR_GRAPHITE_MIST:10 --limit TRANSLATOR_VOID_BLUE:10 \
  --limit PANEL_1X2:10 --limit PANEL_2X2:10 --limit PANEL_1X4:10 \
  --limit PANEL_2X4:10 --limit PANEL_4X4:10 \
  --limit OXYGEN_SHAKE_MORNING_BREATH:10 --limit OXYGEN_SHAKE_EVENING_BREATH:10 \
  --limit OXYGEN_SHAKE_MINT:10 --limit OXYGEN_SHAKE_CHOCOLATE:10
```
Current Round 5 PnL baseline: ~922,962

## Common Bugs to Avoid
- Forgetting sell_orders are negative → use `abs(sell_orders[price])`
- Not checking position before ordering → ALL orders get rejected
- Using `list(dict.items())[0]` without sorting → dict order not guaranteed to be price-sorted
- Exceeding traderData 50k limit → state becomes corrupt
- Importing unsupported libraries → submission fails silently
