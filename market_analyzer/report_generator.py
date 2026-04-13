"""
report_generator.py
-------------------
Write a markdown research report per product/day and a JSON summary.

Inputs:  all intermediate artefacts for one (day, product).
Outputs: ``report.md`` and ``summary.json`` in the product's output folder.

Trading decision informed: the report is a decision document — each section
ties a statistic to "what should I do about this?".
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
    """Minimal markdown-table renderer (avoids the ``tabulate`` dependency)."""
    if df is None or df.empty:
        return "_empty_"
    cols = [str(c) for c in df.columns]
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    rows = []
    for _, row in df.iterrows():
        cells = []
        for v in row.values:
            if isinstance(v, float):
                cells.append(f"{v:.4f}")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep, *rows])


def _top_rows(df: pd.DataFrame, n: int, by: str = "total_pnl") -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    return df.sort_values(by, ascending=False).head(n)


def write_product_report(
    out_dir: Path,
    day: int,
    product: str,
    *,
    summary_stats: Dict,
    fv_eval: pd.DataFrame,
    reversion_stats: Dict,
    regime_label: str,
    z_predictive: pd.DataFrame,
    obi_predictive: pd.DataFrame,
    obi_corr: Dict,
    exec_stats: Dict,
    sweeps: Dict[str, pd.DataFrame],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- JSON summary (machine-readable) -----------------------------------
    best_fv_row = fv_eval.iloc[0].to_dict() if not fv_eval.empty else {}
    best_strats = {
        name: _top_rows(df, 1).to_dict(orient="records")
        for name, df in sweeps.items()
    }
    summary_json = {
        "day": day,
        "product": product,
        "fingerprint": summary_stats,
        "reversion": reversion_stats,
        "regime": regime_label,
        "best_fair_value": best_fv_row,
        "obi_correlation": obi_corr,
        "execution": exec_stats,
        "best_strategies": best_strats,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary_json, indent=2, default=float))

    # --- Markdown report ---------------------------------------------------
    lines = []
    lines.append(f"# {product} — day {day}\n")
    lines.append("## A. Product fingerprint\n")
    for k, v in summary_stats.items():
        lines.append(f"- **{k}**: {_fmt(v)}")
    lines.append("")

    lines.append("## B. Behavioural classification\n")
    lines.append(f"- **regime label**: `{regime_label}`")
    for k, v in reversion_stats.items():
        lines.append(f"- **{k}**: {_fmt(v)}")
    lines.append("\n*Decision*: `mean_reverting` → favour z-score / EMA-reversion. "
                 "`trending` → avoid reversion takers; consider breakout. "
                 "`random_or_mixed` → rely on spread capture (market making) or OBI tilt.\n")

    lines.append("## C. Fair value ranking\n")
    if not fv_eval.empty:
        lines.append(fv_eval.head(15).pipe(_df_to_md))
    lines.append("\n*Decision*: use the top-ranked FV for the strategy's reference price; "
                 "if MAE is large vs a typical spread, FV-based strategies will struggle.\n")

    lines.append("## D. Signal predictive tests\n")
    if not z_predictive.empty:
        lines.append("### z-score → future return (top by |mean_future_ret|)")
        z_sorted = z_predictive.reindex(
            z_predictive["mean_future_ret"].abs().sort_values(ascending=False).index
        ).head(15)
        lines.append(z_sorted.pipe(_df_to_md))
    if not obi_predictive.empty:
        lines.append("\n### OBI bucket → future return")
        lines.append(obi_predictive.pipe(_df_to_md))
    if obi_corr:
        lines.append("\n### OBI correlation with future returns")
        for k, v in obi_corr.items():
            lines.append(f"- **{k}**: {_fmt(v)}")
    lines.append("\n*Decision*: monotone OBI-bucket returns → directional tilt. "
                 "Strong z-score reversion → threshold strategy is viable.\n")

    lines.append("## E. Execution / fill profile\n")
    for k, v in exec_stats.items():
        lines.append(f"- **{k}**: {_fmt(v)}")
    lines.append("\n*Decision*: wide spread + many trades inside → market-making friendly. "
                 "Most trades at bid/ask and few inside → taker-dominated book.\n")

    lines.append("## F. Benchmark strategy families\n")
    for name, df in sweeps.items():
        lines.append(f"### {name}")
        top = _top_rows(df, 5)
        if top.empty:
            lines.append("_no results_\n")
            continue
        lines.append(top.pipe(_df_to_md))
        lines.append("")
    lines.append("*Decision*: prefer families with several parameter sets giving positive PnL "
                 "(plateau) over a single spiky winner (overfit).\n")

    lines.append("## G. Key risks\n")
    risks = _risk_flags(summary_stats, reversion_stats, exec_stats)
    for r in risks:
        lines.append(f"- {r}")
    lines.append("")

    lines.append("## H. Recommended next experiments\n")
    for e in _recommendations(regime_label, sweeps):
        lines.append(f"- {e}")
    lines.append("")

    path = out_dir / "report.md"
    path.write_text("\n".join(lines))
    return path


def _risk_flags(summary_stats: Dict, rev_stats: Dict, exec_stats: Dict):
    risks = []
    if summary_stats.get("spread_mean", 0) > 5:
        risks.append("Wide average spread — taker PnL will suffer from crossing costs.")
    if summary_stats.get("trade_count_total", 0) < 200:
        risks.append("Low trade activity — maker fill rates will be weak.")
    if rev_stats.get("half_life_ret", 0) > 200:
        risks.append("Very long reversion half-life — threshold strategies will carry inventory too long.")
    if exec_stats.get("pct_inside_spread", 0) and exec_stats["pct_inside_spread"] < 0.05:
        risks.append("Almost no inside-spread trading — price-improving quotes may rarely fill.")
    if not risks:
        risks.append("No obvious structural risk flags from phase-1 diagnostics.")
    return risks


def _recommendations(regime_label: str, sweeps: Dict[str, pd.DataFrame]):
    out = []
    if regime_label == "mean_reverting":
        out.append("Zoom sweep around top z-score (window, entry) region.")
        out.append("Try EMA-reversion takers with alpha 0.1–0.3 and small edges.")
    elif regime_label == "trending":
        out.append("Skip reversion strategies; test momentum / breakout benchmarks (not yet in phase 1).")
    else:
        out.append("Focus on spread capture (market making) and OBI-tilt strategies.")
    # Pull top family by PnL.
    best_family = None
    best_pnl = -1e18
    for name, df in sweeps.items():
        if df is None or df.empty:
            continue
        top = df["total_pnl"].max()
        if top > best_pnl:
            best_pnl = top
            best_family = name
    if best_family:
        out.append(f"Best benchmark family this day: **{best_family}** (top PnL {best_pnl:.1f}) — refine its grid.")
    return out
