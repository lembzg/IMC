"""
report_generator.py
-------------------
Write a markdown research report per (day, product) plus a JSON summary.

This version replaces the original free-text "Decision" lines and the
generic "top family" pick with rules that actually consult the numbers:

  * fair-value ranking excludes non-causal (oracle) models from any
    recommendation, but still shows them in the reference table;
  * recommendations require positive PnL + at least two parameter sets
    with positive PnL before naming a "best" family;
  * if the behavioural classifier says one thing but the strategy sweeps
    disagree, the report flags the conflict and downgrades the label;
  * the execution-section "Decision" prints the single branch that
    actually matches the execution stats;
  * risk flags cover: Hurst out-of-domain / unreliable, zero-fill families,
    qcut collapse, OBI sign inversion, weighted_mid / microprice collision,
    degenerate zero-spread fills, and classifier-vs-benchmark conflict.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt(v):
    if isinstance(v, float):
        return "nan" if not np.isfinite(v) else f"{v:.4f}"
    return str(v)


def _df_to_md(df: pd.DataFrame) -> str:
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
                cells.append("nan" if not np.isfinite(v) else f"{v:.4f}")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep, *rows])


def _top_rows(df: pd.DataFrame, n: int, by: str = "total_pnl") -> pd.DataFrame:
    if df is None or df.empty or by not in df.columns:
        return pd.DataFrame()
    return df.sort_values(by, ascending=False).head(n)


# ---------------------------------------------------------------------------
# Evidence-based decision helpers
# ---------------------------------------------------------------------------

# Minimum fraction of parameter sets with positive PnL for a family to count
# as "robust enough to recommend".
MIN_ROBUST_POS_FRAC = 0.3
MIN_ROBUST_POS_COUNT = 2


def _family_robustness(df: pd.DataFrame) -> Dict[str, float]:
    """Summarise a sweep's robustness: top PnL, #positive-PnL params, fraction."""
    if df is None or df.empty or "total_pnl" not in df.columns:
        return {"top_pnl": float("nan"), "n_positive": 0, "pos_frac": 0.0,
                "n_total": 0, "n_fills_top": 0, "zero_fill_frac": 1.0}
    top = df.sort_values("total_pnl", ascending=False).iloc[0]
    pos_mask = df["total_pnl"] > 0
    zero_fill_mask = df.get("n_fills", pd.Series([0] * len(df))) == 0
    return {
        "top_pnl": float(top["total_pnl"]),
        "n_positive": int(pos_mask.sum()),
        "pos_frac": float(pos_mask.mean()),
        "n_total": int(len(df)),
        "n_fills_top": int(top.get("n_fills", 0)),
        "zero_fill_frac": float(zero_fill_mask.mean()),
    }


def _best_recommendable_family(sweeps: Dict[str, pd.DataFrame]) -> Optional[str]:
    """Pick a family only if its sweep clears robustness + positive-PnL bars."""
    scored = []
    for name, df in sweeps.items():
        r = _family_robustness(df)
        if (r["top_pnl"] > 0
                and r["n_positive"] >= MIN_ROBUST_POS_COUNT
                and r["pos_frac"] >= MIN_ROBUST_POS_FRAC):
            scored.append((name, r))
    if not scored:
        return None
    # Prefer highest top_pnl × positive fraction (penalizes spiky winners).
    scored.sort(key=lambda kv: kv[1]["top_pnl"] * max(kv[1]["pos_frac"], 0.01),
                reverse=True)
    return scored[0][0]


def _classifier_vs_sweeps_conflict(regime_label: str,
                                   sweeps: Dict[str, pd.DataFrame]) -> Optional[str]:
    """Return a human string describing any classifier-vs-sweep contradiction."""
    rev_families = ("zscore", "ema_reversion")
    trend_families = ()  # none currently
    if regime_label == "mean_reverting_level":
        any_pos = any(_family_robustness(sweeps.get(f)).get("top_pnl", 0) > 0
                      for f in rev_families)
        if not any_pos:
            return ("label says mean_reverting_level but no reversion family "
                    "produced positive PnL on this day")
    if regime_label == "microstructure_noise":
        if any(_family_robustness(sweeps.get(f)).get("top_pnl", 0) > 0
               for f in rev_families):
            return ("label says microstructure_noise but a reversion-family "
                    "benchmark showed positive PnL — re-check the classifier")
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

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
    feature_health: Optional[Dict] = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    feature_health = feature_health or {}

    # --- Robustness summaries + recommendation ---------------------------------
    family_rob = {name: _family_robustness(df) for name, df in sweeps.items()}
    best_family = _best_recommendable_family(sweeps)
    classifier_conflict = _classifier_vs_sweeps_conflict(regime_label, sweeps)
    effective_label = regime_label
    if classifier_conflict:
        if regime_label == "mean_reverting_level":
            effective_label = "mean_reverting_but_unprofitable"

    # --- Causal-only FV subset -----------------------------------------------
    causal_fv = (fv_eval[fv_eval["causal"]] if "causal" in fv_eval.columns
                 else fv_eval)
    reference_fv = (fv_eval[~fv_eval["causal"]] if "causal" in fv_eval.columns
                    else pd.DataFrame())
    best_causal_name = (
        str(causal_fv.sort_values(["horizon", "mae"]).iloc[0]["model"])
        if not causal_fv.empty else "mid"
    )

    # --- JSON summary (machine-readable) -------------------------------------
    summary_json = {
        "day": day,
        "product": product,
        "fingerprint": summary_stats,
        "reversion": reversion_stats,
        "regime_raw": regime_label,
        "regime_effective": effective_label,
        "classifier_vs_sweeps_conflict": classifier_conflict,
        "feature_health": feature_health,
        "best_causal_fair_value": best_causal_name,
        "best_recommendable_family": best_family,
        "family_robustness": family_rob,
        "obi_correlation": obi_corr,
        "execution": exec_stats,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary_json, indent=2, default=float))

    # --- Markdown report -----------------------------------------------------
    L: List[str] = []
    L.append(f"# {product} — day {day}\n")

    # A. Fingerprint
    L.append("## A. Product fingerprint\n")
    for k, v in summary_stats.items():
        L.append(f"- **{k}**: {_fmt(v)}")
    L.append("")

    # B. Behavioural classification
    L.append("## B. Behavioural classification\n")
    L.append(f"- **regime label (raw)**: `{regime_label}`")
    L.append(f"- **regime label (effective)**: `{effective_label}`")
    if classifier_conflict:
        L.append(f"- **classifier/sweep conflict**: {classifier_conflict}")
    for k, v in reversion_stats.items():
        L.append(f"- **{k}**: {_fmt(v)}")
    L.append("")
    L.append(_regime_decision_text(effective_label))
    L.append("")

    # C. Fair value ranking
    L.append("## C. Fair value ranking (causal models only)\n")
    if not causal_fv.empty:
        L.append(causal_fv.head(15).pipe(_df_to_md))
    else:
        L.append("_no causal FV candidates evaluated_")
    L.append("")
    L.append(f"*Top causal FV at h=1*: **{best_causal_name}** — "
             f"use this as the strategy reference price.")
    L.append("")
    if not reference_fv.empty:
        L.append("### Reference / oracle models (NOT for live use — look-ahead):")
        L.append(reference_fv.head(5).pipe(_df_to_md))
        L.append("")

    # D. Signal predictive tests
    L.append("## D. Signal predictive tests\n")
    if not z_predictive.empty:
        L.append("### z-score → future return (top by |mean_future_ret|, "
                 "deduplicated across overlapping thresholds)")
        zp = z_predictive.reindex(
            z_predictive["mean_future_ret"].abs()
            .sort_values(ascending=False).index
        ).head(15)
        L.append(zp.pipe(_df_to_md))
    else:
        L.append("_z-score predictive tests returned no rows above the "
                 "minimum sample size_")
    if not obi_predictive.empty:
        L.append("\n### OBI bucket → future return")
        effective = int(obi_predictive.get("n_buckets_effective",
                                           pd.Series([0])).iloc[0])
        if effective < 3:
            L.append(f"*Warning*: qcut collapsed to {effective} effective "
                     f"buckets — any 'monotone' claim here is trivial.")
        L.append(obi_predictive.pipe(_df_to_md))
    if obi_corr:
        L.append("\n### OBI correlation with future returns")
        for k, v in obi_corr.items():
            L.append(f"- **{k}**: {_fmt(v)}")
        if feature_health.get("obi_signs_inconsistent"):
            L.append("\n*Warning*: `obi_l1` and `obi_total` are negatively "
                     "correlated — at least one OBI definition is likely "
                     "mis-computed. Treat OBI conclusions with caution.")
    L.append("")

    # E. Execution / fill profile
    L.append("## E. Execution / fill profile\n")
    for k, v in exec_stats.items():
        L.append(f"- **{k}**: {_fmt(v)}")
    if "mean_time_between_trades" in exec_stats:
        L.append("- _note_: `mean_time_between_trades` is in timestamp units "
                 "(typically ms).")
    L.append("")
    L.append(_execution_decision_text(exec_stats))
    L.append("")

    # F. Benchmark strategies
    L.append("## F. Benchmark strategy families\n")
    for name, df in sweeps.items():
        L.append(f"### {name}")
        top = _top_rows(df, 5)
        if top.empty:
            L.append("_no results_\n")
            continue
        L.append(top.pipe(_df_to_md))
        r = family_rob[name]
        L.append(f"_{r['n_positive']}/{r['n_total']} parameter sets had "
                 f"positive PnL; top_pnl={r['top_pnl']:.2f}; zero-fill fraction "
                 f"{r['zero_fill_frac']:.2f}_")
        L.append("")

    # G. Risk flags
    L.append("## G. Key risks\n")
    for r in _risk_flags(summary_stats, reversion_stats, exec_stats, sweeps,
                          feature_health, classifier_conflict):
        L.append(f"- {r}")
    L.append("")

    # H. Recommendations
    L.append("## H. Recommended next experiments\n")
    for e in _recommendations(effective_label, best_family, family_rob,
                              classifier_conflict):
        L.append(f"- {e}")
    L.append("")

    path = out_dir / "report.md"
    path.write_text("\n".join(L))
    return path


# ---------------------------------------------------------------------------
# Decision/branch text
# ---------------------------------------------------------------------------

def _regime_decision_text(label: str) -> str:
    mapping = {
        "fixed_anchored":
            "*Decision*: `fixed_anchored` → product barely moves; prefer "
            "passive quoting around the anchor with tight widths; avoid any "
            "strategy that assumes price moves.",
        "mean_reverting_level":
            "*Decision*: `mean_reverting_level` → z-score / EMA reversion "
            "families are worth testing, gated by the benchmark sweeps.",
        "mean_reverting_but_unprofitable":
            "*Decision*: price-level mean-reversion is detectable "
            "statistically but current reversion benchmarks are not "
            "profitable — the spread is likely eating the edge. Consider "
            "passive-only variants or skip.",
        "trending":
            "*Decision*: `trending` → avoid reversion takers; explore "
            "momentum / breakout benchmarks (not yet in this phase).",
        "microstructure_noise":
            "*Decision*: `microstructure_noise` → level is a random walk; "
            "the negative return autocorrelation is bid-ask bounce, not an "
            "exploitable edge. Focus on spread capture (maker) or OBI tilt.",
        "random_or_mixed":
            "*Decision*: signal is ambiguous — rely on spread capture / OBI "
            "tilt and let the benchmarks decide.",
        "unknown":
            "*Decision*: insufficient data to classify; do not draw "
            "conclusions from this report.",
    }
    return mapping.get(label, mapping["random_or_mixed"])


def _execution_decision_text(exec_stats: Dict) -> str:
    spread = exec_stats.get("spread_mean", float("nan"))
    inside = exec_stats.get("pct_inside_spread", float("nan"))
    trades_per_tick = exec_stats.get("trades_per_tick", float("nan"))

    if not np.isfinite(spread) or not np.isfinite(inside):
        return "*Decision*: not enough execution data to judge maker viability."

    if inside < 0.02 and spread >= 3:
        return ("*Decision*: wide spread but essentially 0% of trades print "
                "inside — this is a taker-dominated book; passive quotes at "
                "top-of-book will rarely improve price and maker fill rates "
                "will be low.")
    if inside >= 0.1 and spread >= 3:
        return ("*Decision*: wide spread with material inside-spread trading "
                "→ market-making-friendly conditions; test tight-quote maker "
                "strategies gated by the sweep.")
    if spread < 2 and trades_per_tick > 0.05:
        return ("*Decision*: tight spread and active tape → maker edge is "
                "thin; taker strategies need very high-confidence signals to "
                "clear the cost.")
    return ("*Decision*: execution profile is intermediate — lean on the "
            "sweep results for which style fits this day.")


# ---------------------------------------------------------------------------
# Risk flags + recommendations
# ---------------------------------------------------------------------------

def _risk_flags(summary_stats: Dict, rev_stats: Dict, exec_stats: Dict,
                sweeps: Dict[str, pd.DataFrame], feature_health: Dict,
                classifier_conflict: Optional[str]) -> List[str]:
    risks: List[str] = []

    # Structural data flags.
    if feature_health.get("wm_micro_identical"):
        risks.append("`weighted_mid` and `microprice` collapsed to identical "
                     "series — core feature bug must be fixed before trusting "
                     "any FV result.")
    if feature_health.get("obi_signs_inconsistent"):
        risks.append("`obi_l1` and `obi_total` are negatively correlated — "
                     "at least one OBI definition is mis-computed.")
    zsfill = feature_health.get("zero_spread_frac", 0.0)
    if isinstance(zsfill, float) and zsfill > 0.01:
        risks.append(f"{zsfill:.1%} of ticks have zero or negative spread — "
                     "strategies can fill at degenerate book states; check "
                     "the sweep's zero-spread-fill fractions.")

    # Classic execution flags.
    if summary_stats.get("spread_mean", 0) > 5:
        risks.append("Wide average spread — taker PnL will suffer from "
                     "crossing costs.")
    if summary_stats.get("trade_count_total", 0) < 200:
        risks.append("Low trade activity — maker fill rates will be weak "
                     "and the maker-fill proxy will fire rarely.")
    inside = exec_stats.get("pct_inside_spread", 0.0) or 0.0
    if inside < 0.05:
        risks.append("Almost no inside-spread trading — price-improving "
                     "quotes rarely fill.")

    # Classifier sanity.
    h = rev_stats.get("hurst_mid")
    if h is None or not np.isfinite(h):
        risks.append("Hurst estimator returned NaN (unreliable on near-flat "
                     "price series); regime classification may be weak.")
    hl = rev_stats.get("half_life_level")
    if hl is None or not np.isfinite(hl):
        risks.append("`half_life_level` could not be estimated reliably — "
                     "reversion strategies should not be sized from it.")

    # Sweep flags.
    for name, df in sweeps.items():
        r = _family_robustness(df)
        if r["n_total"] > 0 and r["zero_fill_frac"] == 1.0:
            risks.append(f"Benchmark family `{name}` produced zero fills "
                         "across every parameter set — simulator or signal "
                         "may be mis-aligned with this day's data.")
        elif r["n_total"] > 0 and r["top_pnl"] == 0 and r["n_fills_top"] > 0:
            risks.append(f"Benchmark family `{name}` produced fills but "
                         "exactly-zero PnL — likely every fill occurred at a "
                         "zero-spread / degenerate tick (see `zero_spread_fill_frac`).")

    if classifier_conflict:
        risks.append(f"Classifier conflict: {classifier_conflict}.")

    if not risks:
        risks.append("No structural risk flags triggered.")
    return risks


def _recommendations(effective_label: str, best_family: Optional[str],
                     family_rob: Dict[str, Dict],
                     classifier_conflict: Optional[str]) -> List[str]:
    out: List[str] = []
    if best_family is None:
        out.append("No benchmark family cleared the sanity bar (positive "
                   f"top PnL + >={MIN_ROBUST_POS_COUNT} positive-PnL "
                   f"parameter sets, >={MIN_ROBUST_POS_FRAC:.0%} positive "
                   "fraction). Evidence inconclusive this day — do not "
                   "promote any family yet.")
    else:
        r = family_rob[best_family]
        out.append(f"Best recommendable family: **{best_family}** "
                   f"(top PnL {r['top_pnl']:.1f}, positive in "
                   f"{r['n_positive']}/{r['n_total']} parameter sets). "
                   "Zoom sweep around its winning params.")

    if effective_label == "mean_reverting_level":
        out.append("Test z-score and EMA-reversion variants with smaller "
                   "edges; gate acceptance on positive-fraction in the sweep.")
    elif effective_label == "microstructure_noise":
        out.append("Do not size reversion trades from return autocorrelation. "
                   "Focus on spread capture (maker) and OBI tilt; reconsider "
                   "reversion only after refining the classifier.")
    elif effective_label == "mean_reverting_but_unprofitable":
        out.append("Statistical reversion is present but the spread is eating "
                   "the edge — try passive quoting at tighter widths around a "
                   "reverting FV before resuming taker strategies.")
    elif effective_label == "fixed_anchored":
        out.append("Treat price as pinned; focus on spread capture around "
                   "the anchor with small sizes.")

    if classifier_conflict:
        out.append("Classifier-vs-benchmark conflict present — rely on "
                   "benchmark evidence over the label for this day.")
    return out
