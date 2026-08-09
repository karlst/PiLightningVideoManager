"""
Configuration values for desktop-only Solution filtering.

A Candidate is a saved clip that might contain lightning. SolutionFilter applies
additional desktop analysis to decide whether the Candidate is a likely true
flash or a known false-positive pattern.

SolutionConfig holds the tunable thresholds used by those filters. The module
constant SOLUTION_CONFIG supplies the normal defaults; Analyzer settings panels
may create temporary SolutionConfig objects without changing these defaults.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SolutionConfig:
    """Tunable parameters used by desktop Solution filters."""

    # --------------------------------------------------------------
    # Brightness noise filtering
    # --------------------------------------------------------------

    # Sliding-window size used to decide whether oscillation is
    # sustained over a significant number of frames.
    brightness_noise_window_frames: int = 100

    # Ignore this many frames before and after the Candidate trigger.
    #
    # This prevents the actual lightning/transient event from being
    # mistaken for sustained brightness noise.
    brightness_noise_trigger_exclusion_frames: int = 10

    # Brightness-delta magnitude required before a sample participates
    # in the noise analysis.
    #
    # Initial experimentally selected value.
    brightness_noise_min_delta_magnitude: float = 0.5

    # Number of meaningful delta samples required inside one window.
    brightness_noise_min_meaningful_samples: int = 50

    # Number of positive/negative sign changes required among those
    # meaningful samples.
    brightness_noise_min_sign_changes: int = 40

    # --------------------------------------------------------------
    # Steady-state anomaly filtering
    # --------------------------------------------------------------

    # Number of frames immediately before the trigger used to define
    # the original brightness baseline.
    steady_state_baseline_frames: int = 10

    # If brightness returns this close to baseline after the trigger,
    # the event is transient and therefore not an SSA.
    steady_state_baseline_tolerance: float = 2.0

    # New steady brightness must be at least this far above baseline.
    steady_state_rise_threshold: float = 4.0

    # Allowed variation around the proposed new steady brightness.
    steady_state_neighborhood: float = 2.0

    # Number of frames required to prove that the elevated state persists.
    steady_state_min_frames: int = 100

    # Maximum number of post-trigger frames inspected for an SSA.
    steady_state_search_frames: int = 200


SOLUTION_CONFIG = SolutionConfig()