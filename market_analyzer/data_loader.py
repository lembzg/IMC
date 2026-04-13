"""
data_loader.py
--------------
Load IMC prices + trades CSVs into tidy per-product DataFrames.

Inputs:   directory containing IMC data (default: ``data/prices`` and
          ``data/trades`` — falls back to a flat directory too).
Outputs:  a ``LoadedData`` bundle with prices and trades DataFrames indexed
          by (day, product).

Trading decision informed: guarantees that every downstream module sees the
same clean schema. If a product is missing a column, we log it and skip so we
don't silently analyse nonsense.
"""
from __future__ import annotations

import glob
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from .config import (COL_DAY, COL_PRODUCT, COL_TS, PRICES_FNAME_GLOB,
                     PRICES_SEP, TRADES_FNAME_GLOB, TRADES_SEP)

log = logging.getLogger(__name__)


@dataclass
class LoadedData:
    """Holds all loaded data keyed by (day, product)."""
    prices: Dict[Tuple[int, str], pd.DataFrame]
    trades: Dict[Tuple[int, str], pd.DataFrame]

    @property
    def products(self) -> List[str]:
        return sorted({p for (_d, p) in self.prices.keys()})

    @property
    def days(self) -> List[int]:
        return sorted({d for (d, _p) in self.prices.keys()})

    def get(self, day: int, product: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
        return self.prices[(day, product)], self.trades.get((day, product), _empty_trades())


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "price", "quantity", "symbol"])


def _find_files(data_dir: Path, pattern: str) -> List[Path]:
    """Find CSVs either in ``data_dir`` directly or a nested subfolder."""
    candidates = list(data_dir.glob(pattern))
    for sub in ("prices", "trades"):
        candidates.extend((data_dir / sub).glob(pattern))
    # de-dup while preserving order
    seen = set()
    out = []
    for p in candidates:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _read_prices_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=PRICES_SEP)
    # Coerce depth columns to numeric; empties become NaN.
    for col in df.columns:
        if col not in (COL_PRODUCT,):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _read_trades_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=TRADES_SEP)
    # Normalise: some files use "symbol", we also expose "product" alias.
    if "symbol" in df.columns and COL_PRODUCT not in df.columns:
        df[COL_PRODUCT] = df["symbol"]
    for col in ("timestamp", "price", "quantity"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _infer_day(path: Path, df: pd.DataFrame) -> int:
    if COL_DAY in df.columns and df[COL_DAY].notna().any():
        return int(df[COL_DAY].dropna().iloc[0])
    # fall back to filename: prices_round_0_day_-1.csv
    stem = path.stem
    if "_day_" in stem:
        try:
            return int(stem.split("_day_")[-1])
        except ValueError:
            pass
    return 0


def load(
    data_dir: os.PathLike | str,
    products: List[str] | None = None,
    days: List[int] | None = None,
) -> LoadedData:
    """Load all prices & trades matching filters. Empty filter = include all."""
    data_dir = Path(data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    prices_map: Dict[Tuple[int, str], pd.DataFrame] = {}
    trades_map: Dict[Tuple[int, str], pd.DataFrame] = {}

    for path in _find_files(data_dir, PRICES_FNAME_GLOB):
        df = _read_prices_csv(path)
        day = _infer_day(path, df)
        if days and day not in days:
            continue
        for prod, g in df.groupby(COL_PRODUCT):
            if products and prod not in products:
                continue
            g = g.sort_values(COL_TS).reset_index(drop=True)
            prices_map[(day, prod)] = g
        log.info("Loaded prices %s (day=%d, rows=%d)", path.name, day, len(df))

    for path in _find_files(data_dir, TRADES_FNAME_GLOB):
        df = _read_trades_csv(path)
        day = _infer_day(path, df)
        if days and day not in days:
            continue
        for prod, g in df.groupby(COL_PRODUCT):
            if products and prod not in products:
                continue
            g = g.sort_values(COL_TS).reset_index(drop=True)
            trades_map[(day, prod)] = g
        log.info("Loaded trades %s (day=%d, rows=%d)", path.name, day, len(df))

    if not prices_map:
        raise RuntimeError(
            f"No prices CSVs matched in {data_dir} "
            f"(filters: products={products}, days={days})"
        )

    return LoadedData(prices=prices_map, trades=trades_map)
