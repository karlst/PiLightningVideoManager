"""
@file trigger_manager.py

@brief Threshold-based trigger logic for camera metric events.
"""

import time

from cam_config import CamConfig


class TriggerManager:
    def __init__(
        self,
        config: CamConfig
    ) -> None:
        self._config = config
        self._enabled = config.trigger_enabled

        self._max_brightness: float | None = None
        self._max_brightness_delta: float | None = None
        self._max_changed_pixel_fraction: float | None = None

        self._last_trigger_time_monotonic: float = 0.0
        self._last_trigger_reason: str = ""

    def enable(self) -> tuple[bool, str]:
        self._enabled = True
        return True, "Trigger enabled"

    def disable(self) -> tuple[bool, str]:
        self._enabled = False
        return True, "Trigger disabled"

    def is_enabled(self) -> bool:
        return self._enabled

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

        brightness_delta = float(
            metric.get(
                "brightness_delta",
                0.0
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

        if self._enabled and self._cooldown_elapsed():
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

        self._update_max_values(
            brightness,
            brightness_delta,
            changed_pixel_fraction
        )

        if should_fire:
            self._last_trigger_time_monotonic = (
                time.monotonic()
            )

            self._last_trigger_reason = reason

        return should_fire, reason

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

    def _update_max_values(
        self,
        brightness: float,
        brightness_delta: float,
        changed_pixel_fraction: float
    ) -> None:
        if (
            self._max_brightness is None or
            brightness > self._max_brightness
        ):
            self._max_brightness = brightness

        if (
            self._max_brightness_delta is None or
            brightness_delta > self._max_brightness_delta
        ):
            self._max_brightness_delta = brightness_delta

        if (
            self._max_changed_pixel_fraction is None or
            changed_pixel_fraction > self._max_changed_pixel_fraction
        ):
            self._max_changed_pixel_fraction = changed_pixel_fraction

    def _cooldown_elapsed(self) -> bool:
        return (
            (
                time.monotonic() -
                self._last_trigger_time_monotonic
            ) >= self._config.trigger_cooldown_seconds
        )