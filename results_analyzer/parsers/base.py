"""
parsers/base.py
---------------
Parser protocol. A parser takes a path and returns a canonical ``Run``.

Extend by writing a new parser that implements ``can_parse`` + ``parse``
and registering it in ``registry.py``. Nothing downstream should change.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..schema import Run


class Parser(Protocol):
    name: str

    def can_parse(self, path: Path) -> bool: ...
    def parse(self, path: Path) -> Run: ...
