"""
parsers/registry.py
-------------------
Adapter registry: let us add new log formats without touching the pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from .base import Parser
from .imc_log import ImcLogParser
from .imc_submission_log import ImcSubmissionLogParser

_PARSERS: List[Parser] = [ImcSubmissionLogParser(), ImcLogParser()]


def register_parser(parser: Parser) -> None:
    """Add a new parser. Earliest-registered wins among ties in can_parse."""
    _PARSERS.insert(0, parser)


def get_parser(path: Path) -> Parser:
    for p in _PARSERS:
        if p.can_parse(path):
            return p
    raise ValueError(f"No parser can handle {path}. "
                     "Register one via results_analyzer.parsers.register_parser.")
