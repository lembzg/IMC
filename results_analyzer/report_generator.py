"""
report_generator.py
-------------------
Markdown report + JSON summary per run / per product.

Trading decision informed: section H ("Recommended changes") is the reason
this exists — every other section supplies evidence for that list.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pandas as pd


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def _df_to_md(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "_empty_"
    cols = [str(c) for c in df.columns]
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    rows = []
    for _, r in df.iterrows():
        cells = [f"{v:.4f}" if isinstance(v, float) else str(v) for v in r.values]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep, *rows])


def write_product_report(out_dir: Path, *, run_id: str, product: str,
                         sections_present: Dict,
                         pnl_stats: Dict, inv_stats: Dict, fill_rate: pd.DataFrame,
                         exec_summary: Dict, signal_tables: Dict[str, pd.DataFrame],
                         round_trip_stats: Dict, regime_table: pd.DataFrame,
                         tag_attribution: pd.DataFrame,
                         recommendations: list) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# {product} — run `{run_id}`\n"]

    lines.append("## A. Log sections available")
    for k, v in sections_present.items():
        lines.append(f"- **{k}**: {'yes' if v else 'MISSING — diagnostics degraded'}")
    lines.append("")

    lines.append("## B. PnL summary")
    for k, v in (pnl_stats.get(product, {}) or {}).items():
        lines.append(f"- **{k}**: {_fmt(v)}")
    lines.append("")

    lines.append("## C. Inventory stats")
    for k, v in (inv_stats.get(product, {}) or {}).items():
        lines.append(f"- **{k}**: {_fmt(v)}")
    lines.append("")

    lines.append("## D. Fill rate (by side / passive / tag)")
    fr = fill_rate[fill_rate["product"] == product] if not fill_rate.empty else fill_rate
    lines.append(_df_to_md(fr))
    lines.append("")

    lines.append("## E. Execution quality")
    for k, v in (exec_summary.get(product, {}) or {}).items():
        lines.append(f"- **{k}**: {_fmt(v)}")
    lines.append("\n*Decision*: positive `mean_adverse_h*` indicates toxic fills — "
                 "widen edge or de-prioritise that side.\n")

    lines.append("## F. Signal effectiveness (forward PnL by bucket)")
    any_sig = False
    for name, df in signal_tables.items():
        d = df[df["product"] == product] if not df.empty else df
        if d.empty:
            continue
        any_sig = True
        lines.append(f"### {name}")
        lines.append(_df_to_md(d))
        lines.append("")
    if not any_sig:
        lines.append("_No signals matched to fills. Emit `Z`/`OBI`/`SHIFT`/`EMA` in "
                     "your trader's `lambdaLog` per product to enable this section._\n")

    lines.append("## G. Round-trip diagnostics")
    for k, v in (round_trip_stats.get(product, {}) or {}).items():
        lines.append(f"- **{k}**: {_fmt(v)}")
    lines.append("")

    lines.append("## H. PnL attribution by tag")
    if tag_attribution is not None and not tag_attribution.empty:
        lines.append(_df_to_md(tag_attribution[tag_attribution["product"] == product]))
    else:
        lines.append("_No order tags found in log._\n\n"
                     "**How to enable (Phase-2 unlock):** in your trader, when you "
                     "place each `Order`, record the reason tag in your `lambdaLog` "
                     "per product, e.g.:\n\n"
                     "```python\n"
                     "state['TOMATOES']['TAG_BUY'] = 'zscore_buy'\n"
                     "state['TOMATOES']['TAG_SELL'] = 'mm_ask'\n"
                     "```\n\n"
                     "The parser already reads `TAG_BUY` / `TAG_SELL`. Once present, "
                     "this section auto-populates.\n")

    lines.append("## I. Performance by regime")
    if regime_table is not None and not regime_table.empty:
        rt = regime_table[regime_table["product"] == product]
        lines.append(_df_to_md(rt))
    else:
        lines.append("_Not enough market context for regime conditioning._\n")

    lines.append("\n## J. Recommended next changes\n")
    for r in recommendations:
        lines.append(f"- {r}")
    lines.append("")

    path = out_dir / "report.md"
    path.write_text("\n".join(lines))
    return path


def write_run_summary(out_dir: Path, summary: Dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "summary.json"
    p.write_text(json.dumps(summary, indent=2, default=float))
    return p


def build_recommendations(product: str, pnl_stats: Dict, inv_stats: Dict,
                          exec_summary: Dict, round_trip_stats: Dict,
                          fill_rate: pd.DataFrame, sections_present: Dict) -> list:
    """Heuristic post-run recommendations. Decision-useful by construction."""
    recs = []
    ps = pnl_stats.get(product, {}) or {}
    isv = inv_stats.get(product, {}) or {}
    es = exec_summary.get(product, {}) or {}
    rt = round_trip_stats.get(product, {}) or {}

    if ps.get("final_total_pnl", 0) < 0:
        recs.append("Net negative PnL on this product — consider disabling it "
                    "or reducing size until diagnostics improve.")
    if ps.get("max_drawdown", 0) < -max(1.0, abs(ps.get("final_total_pnl", 0)) * 0.5):
        recs.append("Drawdown is large vs final PnL — add a risk cap or tighter stop.")

    if isv.get("pct_time_at_limit", 0) > 0.05:
        recs.append(f"Position at limit {isv['pct_time_at_limit']:.1%} of ticks — "
                    "size down, widen entry threshold, or add inventory-skew quotes.")
    if isv.get("pct_time_flat", 1.0) > 0.9:
        recs.append("Bot flat >90% of the time — signal thresholds may be too strict "
                    "or quotes too far from mid; loosen filters.")

    for h in (1, 5, 10, 20):
        k = f"mean_adverse_h{h}"
        if k in es and es[k] > 0:
            recs.append(f"Adverse selection at h={h}: +{es[k]:.3f} — fills are followed "
                        "by unfavourable moves; widen edge or quote one tick further out.")
            break

    if rt.get("win_rate", 0) and rt["win_rate"] < 0.45:
        recs.append(f"Round-trip win rate {rt['win_rate']:.1%} — either entry signal is "
                    "weak or exits are too late; try earlier exits on MFE retracement.")
    if rt.get("avg_mae", 0) and rt.get("avg_pnl", 0):
        if abs(rt["avg_mae"]) > 3 * abs(rt["avg_pnl"]):
            recs.append("Average MAE >> average PnL — add a per-trade stop or reduce size.")

    if not fill_rate.empty:
        fr = fill_rate[fill_rate["product"] == product]
        if not fr.empty:
            pass_rows = fr[fr.get("was_passive", False) == True]
            if not pass_rows.empty and pass_rows["fill_rate"].mean() < 0.02:
                recs.append("Passive quotes rarely fill — tighten quote distance or "
                            "post one tick inside when spread is wide.")

    if not sections_present.get("trades", True):
        recs.append("Trade History section missing — PnL attribution is limited to "
                    "the Activities-log totals; re-run with a backtester that emits "
                    "Trade History for full diagnostics.")

    if not recs:
        recs.append("No obvious red flags in phase-1 diagnostics. Consider raising "
                    "size incrementally and watch drawdown.")
    return recs
