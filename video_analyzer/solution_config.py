"""Configuration for desktop-only Solution filtering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SolutionConfig:
    """Tunable parameters for desktop Solution filtering."""

    pre_trigger_noise_window_frames: int = 50

    max_pre_trigger_mean_abs_delta: float = 0.750

    steady_state_baseline_tolerance: float = 4.0


SOLUTION_CONFIG = SolutionConfig()