# ASH Edge Findings

Baseline is `trader_baseline.py`.

## Required Target

- `trader_baseline.py` ASH PnL: `60,020`
  - Day -1: `19,908`
  - Day 0: `20,579`
  - Day 1: `19,533`
- 1.5x target: `90,030` ASH PnL

## Invalidated Bot-Flow Edge

The public Ash bot prints often occur at displayed best bid or displayed best ask. In the local `prosperity4btest` backtester, joining those levels looked better than penny-improving because public trades were matched against our limit price.

This did **not** hold in the actual submission log `334459.log`.

Actual log result:

- Day 1, timestamps `0..99900`
- ASH final PnL: `184.203125`
- ASH own fills: `27`
- ASH net position at end: `+18`

Most actual ASH fills were marketable orders crossing the visible book, not passive joins getting hit by public bot flow:

- Buy fills occurred at current ask.
- Sell fills occurred at current bid.
- Passive touch orders were not filled as generously as local `prosperity4btest` modeled them.

Conclusion: the join-touch rule is a local-backtester fill artifact, not a confirmed competitive edge.

Implemented in `trader_ash_join.py`:

- Passive bid joins the displayed bid instead of `bid + 1`.
- Passive ask joins the displayed ask instead of `ask - 1`.
- Quote size increased to `20`, which was best in the local sweep.

Backtest result:

- Day -1 ASH: `22,423`
- Day 0 ASH: `22,927`
- Day 1 ASH: `22,071`
- Total ASH: `67,421`
- Improvement over baseline ASH: `+7,401` or `1.12x`

These numbers should be treated as local-backtester-only and not predictive of the actual engine.

## Tested But Not Enough

- One-sided book replenishment did not stack with the join rule.
- Daily-high ask prints and daily-low bid prints are real:
  - High ask prints revert about 9 ticks over the next 10 snapshots.
  - Low bid prints bounce about 8-9 ticks over the next 10 snapshots.
  - Fillable quantity is too small to add the required `~30k` PnL.
- A fixed high/low ladder using the 8-tick snapback pattern was unstable; best tested ladder-only result was `19,709`.
- Cross-product ROOT-to-ASH signals did not show usable predictive correlation.

## Conclusion

I found a real Ash bot-flow edge, but I did not find a live-testable Ash edge that reaches `90,030` against `trader_baseline.py`.

## Backtester Validation

`rust_backtester v0.4.3` was tested against the actual portal log `334459.log`.

Actual portal log final PnL:

- `ASH_COATED_OSMIUM`: `184.203125`
- `INTARIAN_PEPPER_ROOT`: `7432.0`
- Total: `7616.203125`

Rust replay of `trader_ash_join.py` on `334459.log`:

- `ASH_COATED_OSMIUM`: `175.0`
- `INTARIAN_PEPPER_ROOT`: `7440.0`
- Total: `7615.0`

That is close enough to treat Rust as the more realistic local checker for this fill issue.

Rust full ROUND_2 comparison:

- `trader_baseline.py` ASH: `60,020`
- `trader_ash_join.py` ASH: `10,305`

This confirms that the join-touch rule is invalid under the more realistic matching model.
