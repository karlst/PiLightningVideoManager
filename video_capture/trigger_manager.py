"""
@file trigger_manager.py

@brief Pi-specific CandidateFinder orchestration and persistent settings.
"""

from dataclasses import asdict

from common.candidate_config import CandidateConfig
from common.candidate_config import SENSITIVITY_INDEX
from common.candidate_config import load_candidate_config
from common.candidate_config import load_candidate_settings
from common.candidate_config import reset_candidate_settings
from common.candidate_config import save_candidate_settings
from common.candidate_config import set_candidate_sensitivity
from common.candidate_finder import CandidateFinder
from video_capture.cam_config import CamConfig


class TriggerManager:
    def __init__(
        self,
        config: CamConfig
    ) -> None:
        self._config = config
        self._enabled = config.trigger_enabled

        self._candidate_config = (
            load_candidate_config()
        )

        self._candidate_finder = CandidateFinder(
            self._candidate_config
        )

        self._last_trigger_time_monotonic: float | None = None
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
        metric: dict,
        timestamp_monotonic: float
    ) -> tuple[bool, str]:
        should_fire = False
        reason = ""

        if (
            self._enabled and
            self._cooldown_elapsed(
                timestamp_monotonic
            )
        ):
            should_fire, reason = (
                self._candidate_finder.evaluate(
                    metric
                )
            )

        if should_fire:
            self._last_trigger_time_monotonic = (
                timestamp_monotonic
            )
            self._last_trigger_reason = reason

        return should_fire, reason

    def get_candidate_config(
        self
    ) -> CandidateConfig:
        return self._candidate_config

    def get_candidate_config_dict(
        self
    ) -> dict:
        # Preserve the effective threshold fields expected by the current
        # web UI, while also exposing the persistent sensitivity settings.
        result = asdict(
            self._candidate_config
        )

        result["settings"] = (
            load_candidate_settings()
        )

        return result

    def set_candidate_thresholds(
        self,
        brightness_delta_threshold: float,
        bright_pixel_delta_threshold: float,
        bright_pixel_fraction_threshold: float
    ) -> tuple[bool, str]:
        """Persist advanced threshold edits and activate them immediately."""

        try:
            brightness_delta_threshold = float(
                brightness_delta_threshold
            )
            bright_pixel_delta_threshold = float(
                bright_pixel_delta_threshold
            )
            bright_pixel_fraction_threshold = float(
                bright_pixel_fraction_threshold
            )
        except (
            TypeError,
            ValueError,
        ):
            return (
                False,
                "Invalid candidate threshold value"
            )

        if brightness_delta_threshold < 0.0:
            return (
                False,
                "Brightness delta threshold must be >= 0"
            )

        if not (
            0.0 <=
            bright_pixel_delta_threshold <=
            255.0
        ):
            return (
                False,
                "Bright pixel delta threshold must be between 0 and 255"
            )

        if not (
            0.0 <=
            bright_pixel_fraction_threshold <=
            1.0
        ):
            return (
                False,
                "Bright pixel fraction threshold must be between 0 and 1"
            )

        try:
            settings = load_candidate_settings()

            sensitivity = settings[
                "sensitivity"
            ]

            sensitivity_index = (
                SENSITIVITY_INDEX[
                    sensitivity
                ]
            )

            # Advanced edits modify the active sensitivity profile only.
            settings[
                "candidate_brightness_delta_thresholds"
            ][sensitivity_index] = (
                brightness_delta_threshold
            )

            settings[
                "candidate_bright_pixel_fraction_thresholds"
            ][sensitivity_index] = (
                bright_pixel_fraction_threshold
            )

            settings[
                "candidate_bright_pixel_delta_threshold"
            ] = (
                bright_pixel_delta_threshold
            )

            new_config = (
                save_candidate_settings(
                    settings
                )
            )

        except Exception as error:
            return (
                False,
                f"Candidate settings save failed: {error}"
            )

        self._candidate_config = (
            new_config
        )

        # CandidateFinder does no file I/O. Swap the immutable config object
        # so the next frame uses the new thresholds immediately.
        self._candidate_finder.set_config(
            new_config
        )

        return (
            True,
            (
                "Candidate settings updated: "
                f"sensitivity {new_config.sensitivity}, "
                f"brightness delta "
                f"{new_config.candidate_brightness_delta_threshold:.3f}, "
                f"bright pixel delta "
                f"{new_config.candidate_bright_pixel_delta_threshold:.3f}, "
                f"bright pixel fraction "
                f"{new_config.candidate_bright_pixel_fraction_threshold:.6f}"
            )
        )

    def set_sensitivity(
        self,
        sensitivity: str
    ) -> tuple[bool, str]:
        """Persist a sensitivity level and activate its thresholds immediately."""

        try:
            new_config = (
                set_candidate_sensitivity(
                    sensitivity
                )
            )
        except Exception as error:
            return (
                False,
                f"Candidate sensitivity update failed: {error}"
            )

        self._candidate_config = (
            new_config
        )

        self._candidate_finder.set_config(
            new_config
        )

        return (
            True,
            (
                "Candidate sensitivity updated: "
                f"{new_config.sensitivity}; "
                f"brightness delta "
                f"{new_config.candidate_brightness_delta_threshold:.3f}, "
                f"bright pixel fraction "
                f"{new_config.candidate_bright_pixel_fraction_threshold:.6f}"
            )
        )

    def reset_candidate_config(
        self
    ) -> tuple[bool, str]:
        try:
            new_config = (
                reset_candidate_settings()
            )
        except Exception as error:
            return (
                False,
                f"Candidate settings reset failed: {error}"
            )

        self._candidate_config = (
            new_config
        )

        self._candidate_finder.set_config(
            new_config
        )

        return (
            True,
            "Candidate settings reset to defaults"
        )

    def get_status(self) -> dict:
        return {
            "enabled": self._enabled,
            "state": (
                "Enabled"
                if self._enabled
                else "Disabled"
            ),
            "candidate_config":
                self.get_candidate_config_dict(),
            "last_trigger_reason":
                self._last_trigger_reason,
            "last_trigger_time_monotonic":
                self._last_trigger_time_monotonic
        }

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
            ) >=
            self._config.trigger_cooldown_seconds
        )