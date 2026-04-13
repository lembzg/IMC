"""
pipeline.py
-----------
Top-level orchestration: raw CSVs -> per-product analysis artefacts.

Inputs:  ``AnalyzerConfig``.
Outputs: folders under ``config.output_dir / config.round_label / day_<d> /
         <product>/`` containing plots, tables, summary.json, report.md,
         plus a ``cross_product`` folder per day.

Trading decision informed: this is the single entrypoint that turns a raw
data dump into every artefact you need to pick strategy families before
the competition.

Phase 3 hooks: ``_hook_basket_analysis``, ``_hook_options_analysis``,
``_hook_conversions_analysis`` are called from here — currently no-ops.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

from . import (cross_product, data_loader, execution_analysis,
               fair_value_models, market_features, plotting, regime,
               report_generator, reversion_tests, signal_tests, sweeps)
from .config import AnalyzerConfig

log = logging.getLogger(__name__)


def run_pipeline(cfg: AnalyzerConfig) -> Dict:
    log.info("Loading data from %s", cfg.data_dir)
    loaded = data_loader.load(cfg.data_dir, products=cfg.products or None,
                              days=cfg.days or None)
    log.info("Loaded products=%s, days=%s", loaded.products, loaded.days)

    all_results: Dict = {}
    for day in loaded.days:
        day_dir = Path(cfg.output_dir) / cfg.round_label / f"day_{day}"
        features_by_product: Dict[str, pd.DataFrame] = {}
        all_results[day] = {}

        for product in loaded.products:
            key = (day, product)
            if key not in loaded.prices:
                continue
            prices_df, trades_df = loaded.get(day, product)
            log.info("Analyzing %s day=%d (%d ticks, %d trades)",
                     product, day, len(prices_df), len(trades_df))
            prod_dir = day_dir / product
            result = _analyze_one(prices_df, trades_df, cfg, prod_dir, day, product)
            features_by_product[product] = result["features"]
            all_results[day][product] = result["summary_json"]

        if cfg.cross_product and len(features_by_product) >= 2:
            _write_cross_product(day_dir / "cross_product", features_by_product, cfg)

        # Phase 3 extension hooks.
        _hook_basket_analysis(day_dir, features_by_product)
        _hook_options_analysis(day_dir, features_by_product)
        _hook_conversions_analysis(day_dir, features_by_product)

    # Top-level index file
    index_path = Path(cfg.output_dir) / cfg.round_label / "index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(all_results, indent=2, default=float))
    log.info("Wrote index %s", index_path)
    return all_results


def _analyze_one(
    prices_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    cfg: AnalyzerConfig,
    out_dir: Path,
    day: int,
    product: str,
) -> Dict:
    plots_dir = out_dir / "plots"
    tables_dir = out_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    # -- features
    feats = market_features.compute_market_features(prices_df, trades_df, vol_window=cfg.vol_window)
    summary_stats = market_features.summarize(feats)
    feats.to_csv(tables_dir / "features.csv", index=False)

    # -- fair values
    fv_candidates = fair_value_models.build_fair_value_candidates(
        feats, cfg.ema_alphas, cfg.roll_windows)
    for name, series in fv_candidates.items():
        if name not in feats:
            feats[name] = series.values
    fv_eval = fair_value_models.evaluate_fair_values(fv_candidates, feats, cfg.horizons)
    fv_eval.to_csv(tables_dir / "fair_value_eval.csv", index=False)

    # -- reversion / classification
    rev_stats = reversion_tests.run_reversion_tests(feats)
    regime_label = reversion_tests.classify(rev_stats)
    pd.Series(rev_stats).to_csv(tables_dir / "reversion_stats.csv")

    # -- signal predictive tests
    z_pred = signal_tests.zscore_predictive(feats, cfg.z_windows,
                                            cfg.z_thresholds, cfg.horizons)
    z_pred.to_csv(tables_dir / "zscore_predictive.csv", index=False)
    obi_pred = signal_tests.obi_predictive(feats, cfg.horizons)
    obi_pred.to_csv(tables_dir / "obi_predictive.csv", index=False)
    obi_corr = signal_tests.obi_correlation(feats, cfg.horizons)

    # -- execution
    exec_stats = execution_analysis.analyse_execution(feats, trades_df)
    pd.Series(exec_stats).to_csv(tables_dir / "execution_stats.csv")

    # -- regime label series (phase-2 lite)
    reg_series = regime.label_vol_regime(feats)
    reg_series.to_csv(tables_dir / "vol_regime.csv", index=False)

    # -- strategy sweeps
    sweep_tables: Dict[str, pd.DataFrame] = {}
    if cfg.run_sweeps:
        # Choose a small set of FV cols that exist.
        fv_cols = [c for c in ("mid", "weighted_mid", "microprice",
                               "ema_0.1", "ema_0.2", "ema_0.3",
                               "rolling_mean_50", "rolling_mean_100", "vwap")
                   if c in feats and feats[c].notna().any()]
        edges = [0.5, 1.0, 2.0, 3.0]
        widths = [1.0, 2.0, 3.0]
        z_entries = [1.0, 1.5, 2.0, 2.5]
        z_exits = [0.0, 0.3, 0.5]
        obi_thrs = [0.1, 0.2, 0.3, 0.4]
        sweep_tables = sweeps.run_all_sweeps(
            feats,
            fv_cols=fv_cols,
            edges=edges,
            widths=widths,
            ema_alphas=cfg.ema_alphas,
            z_windows=cfg.z_windows,
            z_entries=z_entries,
            z_exits=z_exits,
            obi_thresholds=obi_thrs,
            position_limit=cfg.position_limit,
        )
        for name, df in sweep_tables.items():
            df.to_csv(tables_dir / f"sweep_{name}.csv", index=False)

    # -- plots
    if cfg.make_plots:
        plotting.plot_price_overview(feats, plots_dir / "01_price_overview.png")
        plotting.plot_spread_depth(feats, plots_dir / "02_spread_depth.png")
        plotting.plot_obi(feats, plots_dir / "03_obi.png")
        z_series = signal_tests.zscore_series(feats, cfg.z_windows[len(cfg.z_windows) // 2])
        plotting.plot_zscore(feats, z_series, plots_dir / "04_zscore.png")
        plotting.plot_return_autocorr(feats, plots_dir / "05_return_autocorr.png")
        plotting.plot_return_distribution(feats, plots_dir / "06_return_distribution.png")
        plotting.plot_rolling_vol_spread(feats, plots_dir / "07_rolling_vol_spread.png")
        plotting.plot_obi_vs_future_ret(obi_pred, plots_dir / "08_obi_vs_future_ret.png")

        # Strategy benchmark plots: run the best-of each family and plot it.
        _plot_best_strategies(feats, sweep_tables, plots_dir, cfg)
        # Heatmaps per family.
        _plot_heatmaps(sweep_tables, plots_dir)

    # -- report
    report_generator.write_product_report(
        out_dir,
        day=day,
        product=product,
        summary_stats=summary_stats,
        fv_eval=fv_eval,
        reversion_stats=rev_stats,
        regime_label=regime_label,
        z_predictive=z_pred,
        obi_predictive=obi_pred,
        obi_corr=obi_corr,
        exec_stats=exec_stats,
        sweeps=sweep_tables,
    )

    return {
        "features": feats,
        "summary_json": {
            "fingerprint": summary_stats,
            "regime": regime_label,
            "reversion": rev_stats,
        },
    }


def _plot_best_strategies(feats, sweep_tables, plots_dir: Path, cfg: AnalyzerConfig):
    from . import strategies as S
    # For each family, pick top PnL and re-run to plot.
    specs = {
        "fv_taker": lambda p: S.strat_fv_taker(feats, fv_col=p["fv_col"], edge=p["edge"],
                                                position_limit=cfg.position_limit),
        "fv_maker": lambda p: S.strat_fv_maker(feats, fv_col=p["fv_col"], width=p["width"],
                                                position_limit=cfg.position_limit),
        "ema_reversion": lambda p: S.strat_ema_reversion_taker(feats, alpha=p["alpha"], edge=p["edge"],
                                                                position_limit=cfg.position_limit),
        "zscore": lambda p: S.strat_zscore(feats, window=int(p["window"]), entry=p["entry"],
                                           exit_z=p["exit_z"], position_limit=cfg.position_limit),
        "obi_tilt": lambda p: S.strat_obi_tilt_taker(feats, threshold=p["threshold"],
                                                     position_limit=cfg.position_limit),
        "hybrid_make_take": lambda p: S.strat_hybrid_make_take(feats, fv_col=p["fv_col"], edge=p["edge"],
                                                                width=p["width"],
                                                                position_limit=cfg.position_limit),
    }
    for name, runner in specs.items():
        df = sweep_tables.get(name)
        if df is None or df.empty:
            continue
        top = df.sort_values("total_pnl", ascending=False).iloc[0].to_dict()
        try:
            res = runner(top)
        except Exception as e:
            log.warning("Could not replay top of %s: %s", name, e)
            continue
        plotting.plot_strategy_result(res, feats, plots_dir / f"10_strategy_{name}.png")


def _plot_heatmaps(sweep_tables, plots_dir: Path):
    pairs = {
        "fv_taker": ("edge", "fv_col"),
        "fv_maker": ("width", "fv_col"),
        "ema_reversion": ("edge", "alpha"),
        "zscore": ("entry", "window"),
        "hybrid_make_take": ("edge", "width"),
    }
    for name, (x, y) in pairs.items():
        df = sweep_tables.get(name)
        if df is None or df.empty:
            continue
        plotting.plot_param_heatmap(df, x, y, plots_dir / f"20_heatmap_{name}.png",
                                     title=f"{name}: PnL heatmap")


def _write_cross_product(out_dir: Path, features_by_product, cfg: AnalyzerConfig):
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = cross_product.cross_product_report(features_by_product)
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv")
    if cfg.make_plots:
        if "price_correlation" in tables:
            plotting.plot_cross_corr(tables["price_correlation"],
                                      out_dir / "price_correlation.png",
                                      "Price correlation")
        if "return_correlation" in tables:
            plotting.plot_cross_corr(tables["return_correlation"],
                                      out_dir / "return_correlation.png",
                                      "Return correlation")


# ---- Phase 3 extension hooks (explicit stubs) -----------------------------

def _hook_basket_analysis(day_dir: Path, features_by_product: Dict) -> None:
    """TODO (Phase 3): when a basket product appears, reconstruct its implied
    fair value from its components and analyse basket-vs-components spread.
    """
    return None


def _hook_options_analysis(day_dir: Path, features_by_product: Dict) -> None:
    """TODO (Phase 3): when option-like products appear, compute implied vol
    surface features and moneyness-conditional signals.
    """
    return None


def _hook_conversions_analysis(day_dir: Path, features_by_product: Dict) -> None:
    """TODO (Phase 3): when conversion opportunities appear (round 2+),
    analyse arbitrage windows and required sizing.
    """
    return None
