"""Configuration values for desktop-only Solution filtering.

A Candidate is a saved clip that might contain lightning. SolutionFilter applies
additional desktop analysis to decide whether the Candidate is a likely true
flash or a known false-positive pattern.

SolutionConfig holds the tunable thresholds used by those filters. The module
constant SOLUTION_CONFIG supplies the normal defaults; Analyzer settings panels
may create temporary SolutionConfig objects without changing these defaults.

Brightness-noise max-delta fraction varies with the Candidate sensitivity:
    high   -> 0.01
    medium -> 0.02
    low    -> 0.04
"""

from __future__ import annotations

from dataclasses import dataclass, replace


BRIGHTNESS_NOISE_MAX_DELTA_FRACTIONS = {
    "high": 0.01,
    "medium": 0.02,
    "low": 0.04,
}


@dataclass(frozen=True)
class SolutionConfig:
    """Tunable parameters used by desktop Solution filters."""

    # --------------------------------------------------------------
    # Brightness noise filtering
    # --------------------------------------------------------------

    brightness_noise_window_frames: int = 100
    brightness_noise_trigger_exclusion_frames: int = 10

    # Absolute floor for a meaningful brightness delta.
    brightness_noise_min_delta_magnitude: float = 0.5

    # Relative floor. The effective threshold is the larger of the
    # absolute floor above and this fraction of the largest absolute
    # brightness delta in the clip.
    brightness_noise_max_delta_fraction: float = 0.02

    brightness_noise_min_meaningful_samples: int = 50
    brightness_noise_min_sign_changes: int = 40

    # --------------------------------------------------------------
    # Stair-step decay filtering
    # --------------------------------------------------------------

    # If cumulative negative recovery within this many frames after
    # the rise reaches the configured fraction of the rise, treat the
    # event as an ordinary fast transient rather than stair-step decay.
    stair_step_transient_recovery_frames: int = 4
    stair_step_transient_recovery_fraction: float = 0.70

    # Consecutive qualifying negative deltas are one downward event.
    # A new stair requires this many intervening non-step frames.
    stair_step_separation_frames: int = 1

    # A substantial positive pulse after the initial rise is evidence of
    # a multi-pulse transient rather than a monotonic stair-step decay.
    stair_step_rebrightening_fraction: float = 0.30

    # --------------------------------------------------------------
    # Steady-state anomaly filtering
    # --------------------------------------------------------------

    steady_state_baseline_frames: int = 10
    steady_state_baseline_tolerance: float = 2.0
    steady_state_rise_threshold: float = 3.8
    steady_state_neighborhood: float = 2.0
    steady_state_min_frames: int = 100
    steady_state_search_frames: int = 200


SOLUTION_CONFIG = SolutionConfig()


def solution_config_for_sensitivity(
    sensitivity: str,
    base_config: SolutionConfig = SOLUTION_CONFIG,
) -> SolutionConfig:
    """Return SolutionConfig with the noise fraction for one sensitivity."""

    normalized = str(sensitivity).lower()

    if normalized not in BRIGHTNESS_NOISE_MAX_DELTA_FRACTIONS:
        raise ValueError(
            "Sensitivity must be high, medium, or low"
        )

    return replace(
        base_config,
        brightness_noise_max_delta_fraction=(
            BRIGHTNESS_NOISE_MAX_DELTA_FRACTIONS[
                normalized
            ]
        ),
    )
