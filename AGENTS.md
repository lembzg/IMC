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

## Common Bugs to Avoid
- Forgetting sell_orders are negative → use `abs(sell_orders[price])`
- Not checking position before ordering → ALL orders get rejected
- Using `list(dict.items())[0]` without sorting → dict order not guaranteed to be price-sorted
- Exceeding traderData 50k limit → state becomes corrupt
- Importing unsupported libraries → submission fails silently
