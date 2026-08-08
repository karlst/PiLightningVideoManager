"""
@file trigger_manager.py

@brief Pi-specific CandidateFinder orchestration and persistent settings.
"""

from dataclasses import asdict
from dataclasses import replace
import json

from common.candidate_config import CANDIDATE_CONFIG
from common.candidate_config import CandidateConfig
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
            self._load_candidate_config()
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
        return asdict(
            self._candidate_config
        )

    def set_candidate_thresholds(
        self,
        brightness_delta_threshold: float,
        bright_pixel_delta_threshold: float,
        bright_pixel_fraction_threshold: float
    ) -> tuple[bool, str]:

        brightness_delta_threshold = float(
            brightness_delta_threshold
        )

        bright_pixel_delta_threshold = float(
            bright_pixel_delta_threshold
        )

        bright_pixel_fraction_threshold = float(
            bright_pixel_fraction_threshold
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

        new_config = replace(
            self._candidate_config,
            candidate_brightness_delta_threshold=(
                brightness_delta_threshold
            ),
            candidate_bright_pixel_delta_threshold=(
                bright_pixel_delta_threshold
            ),
            candidate_bright_pixel_fraction_threshold=(
                bright_pixel_fraction_threshold
            )
        )

        try:
            self._save_candidate_config(
                new_config
            )
        except Exception as error:
            return (
                False,
                f"Candidate settings save failed: {error}"
            )

        self._candidate_config = (
            new_config
        )

        self._candidate_finder = CandidateFinder(
            self._candidate_config
        )

        return (
            True,
            (
                "Candidate settings updated: "
                f"brightness delta "
                f"{brightness_delta_threshold:.3f}, "
                f"bright pixel delta "
                f"{bright_pixel_delta_threshold:.3f}, "
                f"bright pixel fraction "
                f"{bright_pixel_fraction_threshold:.6f}"
            )
        )

    def reset_candidate_config(
        self
    ) -> tuple[bool, str]:
        try:
            self._config.candidate_settings_file.unlink(
                missing_ok=True
            )
        except Exception as error:
            return (
                False,
                f"Candidate settings reset failed: {error}"
            )

        self._candidate_config = (
            CANDIDATE_CONFIG
        )

        self._candidate_finder = CandidateFinder(
            self._candidate_config
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

    def _load_candidate_config(
        self
    ) -> CandidateConfig:
        candidate_config = (
            CANDIDATE_CONFIG
        )

        path = (
            self._config.candidate_settings_file
        )

        if path.exists():
            try:
                data = json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                )

                candidate_config = replace(
                    CANDIDATE_CONFIG,

                    candidate_brightness_delta_threshold=float(
                        data.get(
                            "candidate_brightness_delta_threshold",
                            CANDIDATE_CONFIG.
                            candidate_brightness_delta_threshold
                        )
                    ),

                    candidate_bright_pixel_delta_threshold=float(
                        data.get(
                            "candidate_bright_pixel_delta_threshold",
                            CANDIDATE_CONFIG.
                            candidate_bright_pixel_delta_threshold
                        )
                    ),

                    candidate_bright_pixel_fraction_threshold=float(
                        data.get(
                            "candidate_bright_pixel_fraction_threshold",
                            CANDIDATE_CONFIG.
                            candidate_bright_pixel_fraction_threshold
                        )
                    )
                )

            except Exception:
                candidate_config = (
                    CANDIDATE_CONFIG
                )

        return candidate_config

    def _save_candidate_config(
        self,
        candidate_config: CandidateConfig
    ) -> None:
        path = (
            self._config.candidate_settings_file
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        data = {
            "candidate_brightness_delta_threshold":
                candidate_config.
                candidate_brightness_delta_threshold,

            "candidate_bright_pixel_delta_threshold":
                candidate_config.
                candidate_bright_pixel_delta_threshold,

            "candidate_bright_pixel_fraction_threshold":
                candidate_config.
                candidate_bright_pixel_fraction_threshold
        }

        path.write_text(
            json.dumps(
                data,
                indent=4
            ) + "\n",
            encoding="utf-8"
        )

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