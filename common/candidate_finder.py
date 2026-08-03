"""
@file candidate_finder.py

@brief Threshold-based logic for identifying candidates.
"""

import time

from common.candidate_config import CandidateConfig


# ## Evaluates camera metrics against configured trigger thresholds.
class CandidateFinder:
    # ## Initialize trigger state and tracked maximum metric values.
    def __init__(
        self,
        config: CandidateConfig
    ) -> None:
        self._config = config

    # ## Evaluate one metric sample and return whether capture should fire.
    def evaluate(
        self,
        metric: dict
    ) -> tuple[bool, str]:
        brightness = float(
            metric.get(
                "mean_brightness",
                0.0
            )
        )

        # The preferred lightning trigger metric is now adjacent-frame mean
        # brightness delta, computed on every frame by BufferManager. Fall back
        # to the legacy key so older metric records do not break evaluation.
        brightness_delta = float(
            metric.get(
                "brightness_delta_adjacent",
                metric.get(
                    "brightness_delta",
                    0.0
                )
            )
        )

        changed_pixel_fraction = float(
            metric.get(
                "changed_pixel_fraction",
                0.0
            )
        )

        should_fire = False
        reason = ""

        
        should_fire, reason = (
            self._check_brightness(
                brightness
            )
        )

        if not should_fire:
            should_fire, reason = (
                self._check_brightness_delta(
                    brightness_delta
                )
            )

        if not should_fire:
            should_fire, reason = (
                self._check_changed_pixel_fraction(
                    changed_pixel_fraction
                )
            )

        if should_fire:
            self._last_trigger_reason = reason

        return should_fire, reason

    # ## Check absolute mean brightness threshold.
    def _check_brightness(
        self,
        brightness: float
    ) -> tuple[bool, str]:
        should_fire = False
        reason = ""

        if brightness >= self._config.candidate_brightness_threshold:
            should_fire = True
            reason = (
                f"Brightness trigger: "
                f"{brightness:.3f} >= "
                f"{self._config.candidate_brightness_threshold:.3f}"
            )

        return should_fire, reason

    # ## Check adjacent-frame mean brightness delta threshold.
    def _check_brightness_delta(
        self,
        brightness_delta: float
    ) -> tuple[bool, str]:
        should_fire = False
        reason = ""

        if brightness_delta >= self._config.candidate_brightness_delta_threshold:
            should_fire = True
            reason = (
                f"Brightness delta trigger: "
                f"{brightness_delta:.3f} >= "
                f"{self._config.candidate_brightness_delta_threshold:.3f}"
            )

        return should_fire, reason

    # ## Check changed-pixel fraction threshold.
    def _check_changed_pixel_fraction(
        self,
        changed_pixel_fraction: float
    ) -> tuple[bool, str]:
        should_fire = False
        reason = ""

        if (
            changed_pixel_fraction >=
            self._config.candidate_changed_pixel_fraction_threshold
        ):
            should_fire = True
            reason = (
                f"Motion trigger: "
                f"{changed_pixel_fraction:.5f} >= "
                f"{self._config.candidate_changed_pixel_fraction_threshold:.5f}"
            )

        return should_fire, reason

    