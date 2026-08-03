"""Shared types for playback solution filtering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class SolutionResult:
    """Result returned by a solution filter."""

    is_solution: bool
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
