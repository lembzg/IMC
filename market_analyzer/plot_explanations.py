"""
plot_explanations.py
--------------------
Short, decision-useful explanations for every graph the analyzer produces.

Keyed by filename patterns so every consumer (PDF export, future markdown
embedder) can annotate plots consistently.

Each entry has:
  - title        : human-readable name (used as caption header)
  - definition   : 1 line, plain-language definition
  - why          : 1 line, what trading decision or insight it informs
  - look_for     : optional, what to scan for when reading the chart

Explanations are intentionally short — if you find yourself writing a
paragraph, trim it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import re


@dataclass(frozen=True)
class PlotExplanation:
    title: str
    definition: str
    why: str
    look_for: Optional[str] = None


# --------------------------------------------------------------------------- #
# Per-product plots (filenames written by plotting.py, prefixed with NN_)
# --------------------------------------------------------------------------- #
_STEM_MAP: dict[str, PlotExplanation] = {
    "price_overview": PlotExplanation(
        title="Price overview",
        definition="Best bid, best ask, mid, weighted-mid, and VWAP over time.",
        why="Shows the trend and regime of the product — drifting, ranging, or jumpy.",
        look_for="Gaps between mid and VWAP, sudden jumps, obvious trends or reverts.",
    ),
    "spread_depth": PlotExplanation(
        title="Spread and depth",
        definition="Bid-ask spread and total depth on each side of the book over time.",
        why="Wide spread and thin depth mean higher crossing costs and worse fills.",
        look_for="Spread widening during volatile periods; one-sided depth imbalances.",
    ),
    "obi": PlotExplanation(
        title="Order book imbalance (OBI)",
        definition="Relative difference between bid-side and ask-side depth.",
        why="Can indicate short-term buy or sell pressure.",
        look_for="Persistent tilt above/below zero, and whether price follows.",
    ),
    "zscore": PlotExplanation(
        title="Mid z-score",
        definition="Number of standard deviations price is away from its recent mean.",
        why="Helps identify when price is unusually stretched and may revert.",
        look_for="How often |z| exceeds 1 or 2 and whether it snaps back.",
    ),
    "return_autocorr": PlotExplanation(
        title="Return autocorrelation",
        definition="Correlation between current returns and future returns at different lags.",
        why="Helps detect mean reversion (negative) or momentum (positive).",
        look_for="Bars clearly above or below zero at short lags.",
    ),
    "return_distribution": PlotExplanation(
        title="Return distribution",
        definition="Distribution of returns over the sample period.",
        why="Shows whether most moves are small, whether tails are fat, and how risky extreme moves are.",
    ),
    "rolling_vol_spread": PlotExplanation(
        title="Rolling volatility and spread",
        definition="Rolling realized volatility of returns and rolling mean spread.",
        why="Higher vol widens optimal quotes; spread sets the floor on taker cost.",
        look_for="Periods where vol and spread spike together.",
    ),
    "obi_vs_future_ret": PlotExplanation(
        title="Mean future return by OBI bucket",
        definition="Average forward return grouped by OBI percentile bucket.",
        why="A monotone pattern suggests OBI can tilt directional trades.",
        look_for="Low buckets → negative returns, high buckets → positive returns.",
    ),
}


# Strategy-specific notes — shown after a generic strategy block.
_STRATEGY_NOTES: dict[str, str] = {
    "zscore": "Enters when mid z-score crosses a threshold, betting on reversion.",
    "ema_reversion": "Reverts toward an EMA fair value when price strays too far.",
    "fv_maker": "Posts quotes around a fair-value model; earns spread when filled.",
    "fv_taker": "Crosses when edge vs the fair-value model exceeds a threshold.",
    "obi_tilt": "Skews aggression by order-book imbalance.",
    "hybrid_make_take": "Combines passive quoting with opportunistic taking.",
}

_HEATMAP_NOTES: dict[str, str] = {
    "zscore": "Grid of total PnL over z-score window × entry threshold.",
    "ema_reversion": "Grid over EMA alpha × reversion edge.",
    "fv_maker": "Grid over quoting edge × inventory skew.",
    "fv_taker": "Grid over taker edge × cooldown.",
    "hybrid_make_take": "Grid over maker edge × taker edge.",
}


# --------------------------------------------------------------------------- #
# Cross-product plots
# --------------------------------------------------------------------------- #
_CROSS_MAP: dict[str, PlotExplanation] = {
    "price_correlation": PlotExplanation(
        title="Price correlation across products",
        definition="Pairwise correlation of mid prices between products.",
        why="High correlation suggests basket/pairs strategies may be viable.",
        look_for="Off-diagonal cells with |corr| above ~0.5.",
    ),
    "return_correlation": PlotExplanation(
        title="Return correlation across products",
        definition="Pairwise correlation of returns between products.",
        why="Return correlation is what drives hedge ratios and basket spreads.",
        look_for="Stable, high-magnitude off-diagonal entries.",
    ),
}


# --------------------------------------------------------------------------- #
# Lookup
# --------------------------------------------------------------------------- #
def _stem(filename: str) -> str:
    """Strip numeric prefix (e.g. `10_`) and extension from a plot filename."""
    name = filename.rsplit(".", 1)[0]
    return re.sub(r"^\d+_", "", name)


def explain(filename: str, *, folder_hint: str = "") -> Optional[PlotExplanation]:
    """Return an explanation for a plot filename, or None if unknown.

    ``folder_hint`` lets the caller distinguish cross_product plots from
    per-product ones when filenames would otherwise collide.
    """
    stem = _stem(filename)

    if folder_hint == "cross_product" and stem in _CROSS_MAP:
        return _CROSS_MAP[stem]

    if stem in _STEM_MAP:
        return _STEM_MAP[stem]

    if stem.startswith("strategy_"):
        family = stem[len("strategy_"):]
        note = _STRATEGY_NOTES.get(family, "Benchmark strategy run on this day's data.")
        return PlotExplanation(
            title=f"Strategy — {family.replace('_', ' ')}",
            definition=note,
            why="Compares a candidate family's fills and cumulative PnL against the price path.",
            look_for="Smooth equity curve vs noisy bleed; fills clustered sensibly vs random.",
        )

    if stem.startswith("heatmap_"):
        family = stem[len("heatmap_"):]
        note = _HEATMAP_NOTES.get(family, "Parameter sweep heatmap of total PnL.")
        return PlotExplanation(
            title=f"Parameter heatmap — {family.replace('_', ' ')}",
            definition=note,
            why="Plateaus of high PnL across neighbouring params suggest a robust edge, not overfit.",
            look_for="Broad warm regions vs isolated hot cells.",
        )

    if stem in _CROSS_MAP:
        return _CROSS_MAP[stem]

    return None
