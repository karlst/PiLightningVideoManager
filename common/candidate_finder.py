"""
@file candidate_finder.py

@brief Threshold-based logic for identifying candidates.

A candidate is a captured video clip that might contain a frame showing
lightning. CandidateFinder examines frame metrics and applies the configured
thresholds to decide whether a frame is interesting enough to create such a
candidate. The same CandidateFinder is used during live capture on the Pi and
by the desktop analyzer when candidate detection is replayed from saved data.

CandidateFinder never performs file I/O. Runtime configuration changes replace
its immutable CandidateConfig object in memory.
"""

from common.candidate_config import CandidateConfig


# ## Evaluates camera metrics against configured trigger thresholds.
class CandidateFinder:
    # ## Store candidate thresholds.
    def __init__(
        self,
        config: CandidateConfig
    ) -> None:
        self._config = config

    # ## Atomically replace the in-memory CandidateFinder configuration.
    def set_config(
        self,
        config: CandidateConfig,
    ) -> None:
        self._config = config

    # ## Return the currently active in-memory configuration.
    def get_config(
        self,
    ) -> CandidateConfig:
        return self._config

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

        brightness_delta = float(
            metric.get(
                "brightness_delta_adjacent",
                metric.get(
                    "brightness_delta",
                    0.0
                )
            )
        )

        bright_pixel_fraction = float(
            metric.get(
                "bright_pixel_fraction",
                0.0
            )
        )

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
                self._check_bright_pixel_fraction(
                    bright_pixel_fraction
                )
            )

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

        if (
            brightness_delta >=
            self._config.candidate_brightness_delta_threshold
        ):
            should_fire = True
            reason = (
                f"Brightness delta trigger: "
                f"{brightness_delta:.3f} >= "
                f"{self._config.candidate_brightness_delta_threshold:.3f}"
            )

        return should_fire, reason

    # ## Check fraction of pixels with a strong positive adjacent-frame change.
    def _check_bright_pixel_fraction(
        self,
        bright_pixel_fraction: float
    ) -> tuple[bool, str]:
        should_fire = False
        reason = ""

        if (
            bright_pixel_fraction >=
            self._config.candidate_bright_pixel_fraction_threshold
        ):
            should_fire = True
            reason = (
                f"Bright pixel trigger: "
                f"{bright_pixel_fraction:.6f} >= "
                f"{self._config.candidate_bright_pixel_fraction_threshold:.6f} "
                f"at pixel delta >= "
                f"{self._config.candidate_bright_pixel_delta_threshold:.1f}"
            )

        return should_fire, reason
