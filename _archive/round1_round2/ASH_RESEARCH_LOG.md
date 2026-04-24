# ASH Research Log - Round 2

## Summary
Round 2 intensive search for structural/behavioral edges in ASH_COATED_OSMIUM.

### Best Result
- **Strategy**: One-sided book gap detection (`/tmp/ash_onesided_gap.py`)
- **PnL**: 63,402 total (21,187 + 20,885 + 21,330)
- **vs Baseline**: +453 (+0.72% vs root1's 62,949)

### Key Discovery: ONE-SIDED BOOK PRICE GAPS
**Most robust edge found**. When order book becomes one-sided, price gaps predictably:
- **Bid-only rows**: 375/day, price jumps **+8 ticks** within 110ms (mean +7.86/+8.06/+7.84 across days)
- **Ask-only rows**: 373/day, price jumps **-8 ticks** within 110ms (mean -8.10/-8.24/-8.09)

**Mechanism**: One side gets completely swept → bot replenishes at price ~8 ticks away
**Exploitation**: When bid-only detected, buy at current bid (profit from upcoming gap up). When ask-only, sell at current ask.

### Other Findings

#### Trade Sequence Reversals (NOT EXPLOITABLE LIVE)
- 97.5% of 2+ trade sequences (same direction, <500ms apart) reverse with median -8 tick move
- ~121 sequences/day, consistent across all days
- **Problem**: Can't react fast enough in live trading; by the time sequence detected and gap happens, opportunity gone

#### Z-Score Threshold Optimization
- Tighter z_threshold=3.0 (vs root1's 2.25) gave +366 improvement alone
- Does NOT stack with one-sided detection - covers same edge

#### Spread Narrowing Patterns
- 63% of time spread=16
- When 16→5,8,12: expect +4-6 tick move
- When 16→7,13: expect -4-5 tick move  
- **Problem**: Not actionable in live trading

### Failed Approaches
- Asymmetric buy/sell strategies (based on fill markouts)
- Sweep reversal detection (volume drop detection)
- Post-sequence fading
- Volume spike trading
- Bait quotes after public trades
- Multi-level active taking
- Parameter tuning (SMA windows, FV weights)

### Architecture
One-sided detection runs BEFORE normal FV/z-score logic:
1. Check for bid-only or ask-only book
2. If detected, place aggressive order on that side (vol=30)
3. Otherwise, run normal root1 logic with z=3.0

### Round 2 Diagnostics
- 30,000 ASH rows total
- 2,144 thin-top rows (vol 2-9)
- 1,096 bid-only, 1,143 ask-only
- 1,395 public trades (all at bid1 or ask1)
- No deep book data (level 2/3 mostly empty)

### Next Research Directions (if continuing)
1. Investigate the 52% of public trades that DON'T match visible bid/ask
2. Cross-timestamp state sequences
3. Combine one-sided + spread signals
4. Test on hidden/live data to see if +0.72% compounds with other products
