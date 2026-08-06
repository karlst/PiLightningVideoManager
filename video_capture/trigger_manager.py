"""
@file trigger_manager.py

@brief Threshold-based logic for identifying candidates.
"""

import time

from video_capture.cam_config import CamConfig
from common.candidate_finder import CandidateFinder


# ## Evaluates camera metrics against configured trigger thresholds.
class TriggerManager:
    # ## Initialize trigger state and tracked maximum metric values.
    def __init__(
        self,
        config: CamConfig
    ) -> None:
        self._config = config
        self._enabled = config.trigger_enabled

        self._last_trigger_time_monotonic: float | None = None
        self._last_trigger_reason: str = ""

    # ## Enable automatic trigger evaluation.
    def enable(self) -> tuple[bool, str]:
        self._enabled = True
        return True, "Trigger enabled"

    # ## Disable automatic trigger evaluation.
    def disable(self) -> tuple[bool, str]:
        self._enabled = False
        return True, "Trigger disabled"

    # ## Return whether automatic triggers are enabled.
    def is_enabled(self) -> bool:
        return self._enabled

    # ## Evaluate one metric sample and return whether capture should fire.
    def evaluate(
        self,
        metric: dict,
        timestamp_monotonic: float
    ) -> tuple[bool, str]:

        should_fire = False
        reason = ""

        if self._enabled and self._cooldown_elapsed(timestamp_monotonic):
            should_fire, reason = CandidateFinder.evaluate(metric)

        if should_fire:
            self._last_trigger_time_monotonic = (
                timestamp_monotonic
            )

            self._last_trigger_reason = reason

        return should_fire, reason

    # ## Return trigger status values for UI and health logging.
    def get_status(self) -> dict:
        return {
            "enabled": self._enabled,
            "state": "Enabled" if self._enabled else "Disabled",
            "max_brightness": self._max_brightness,
            "max_brightness_delta": self._max_brightness_delta,
            "max_changed_pixel_fraction": self._max_changed_pixel_fraction,
            "last_trigger_reason": self._last_trigger_reason,
            "last_trigger_time_monotonic": self._last_trigger_time_monotonic
        }

    # ## Check absolute mean brightness threshold.
    def _check_brightness(
        self,
        brightness: float
    ) -> tuple[bool, str]:
        should_fire = False
        reason = ""

        if brightness >= self._config.trigger_brightness_threshold:
            should_fire = True
            reason = (
                f"Brightness trigger: "
                f"{brightness:.3f} >= "
                f"{self._config.trigger_brightness_threshold:.3f}"
            )

        return should_fire, reason

    # ## Check adjacent-frame mean brightness delta threshold.
    def _check_brightness_delta(
        self,
        brightness_delta: float
    ) -> tuple[bool, str]:
        should_fire = False
        reason = ""

        if brightness_delta >= self._config.trigger_brightness_delta_threshold:
            should_fire = True
            reason = (
                f"Brightness delta trigger: "
                f"{brightness_delta:.3f} >= "
                f"{self._config.trigger_brightness_delta_threshold:.3f}"
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
            self._config.trigger_changed_pixel_fraction_threshold
        ):
            should_fire = True
            reason = (
                f"Motion trigger: "
                f"{changed_pixel_fraction:.5f} >= "
                f"{self._config.trigger_changed_pixel_fraction_threshold:.5f}"
            )

        return should_fire, reason

    
    # ## Return whether trigger cooldown has elapsed.
    def _cooldown_elapsed(
        self,
        timestamp_monotonic: float
    ) -> bool:
        if self._last_trigger_time_monotonic is None:
            return True

        return (
            (
                timestamp_monotonic -
                self._last_trigger_time_monotonic
            ) >= self._config.trigger_cooldown_seconds
        )