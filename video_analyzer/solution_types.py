"""
Shared result types and interface used by desktop Solution filters.

Individual Solution filters all return SolutionResult so the rest of the
Analyzer can handle different rejection rules uniformly. SolutionRule is a
Python Protocol describing the evaluate() method a filter must provide; a class
does not need to inherit from SolutionRule as long as it implements that
compatible method.

The category constants provide stable names used by the GUI and batch
classifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


CATEGORY_TRUE_FLASH = "TRUE_FLASH"
CATEGORY_FRAME_DROPOUT = "FRAME_DROPOUT"
CATEGORY_BRIGHT_NOISE = "BRIGHT_NOISE"
CATEGORY_STEADY_STATE_CHANGE = "STEADY_STATE_CHANGE"


@dataclass(frozen=True)
class SolutionResult:
    """Result returned by a solution filter."""

    is_solution: bool
    category: str
    reason: str


class SolutionRule(Protocol):
    """Interface implemented by individual solution filters."""

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        ...
