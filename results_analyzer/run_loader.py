"""
run_loader.py
-------------
Load one or more result logs into ``Run`` objects via the parser registry.

Inputs:   file path or directory.
Outputs:  list[Run].

Trading decision informed: a uniform loading layer so CLI + notebook use the
exact same parser dispatch and degrade identically when sections are absent.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from .parsers import get_parser
from .schema import Run

log = logging.getLogger(__name__)


def load_run(path: Path) -> Run:
    parser = get_parser(path)
    log.info("Parsing %s with %s", path.name, parser.name)
    return parser.parse(path)


def load_runs(path: Path, run_ids: List[str] | None = None) -> List[Run]:
    path = Path(path)
    if path.is_file():
        return [load_run(path)]
    if not path.is_dir():
        raise FileNotFoundError(path)
    logs = sorted(path.glob("*.log"))
    if run_ids:
        logs = [p for p in logs if p.stem in run_ids]
    if not logs:
        raise RuntimeError(f"No .log files found in {path}")
    return [load_run(p) for p in logs]
