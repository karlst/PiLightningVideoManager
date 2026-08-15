"""
@file candidate_config.py

@brief Shared candidate configuration used by live capture and video replay.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateConfig:
    # Triggers on absolute mean frame brightness.
    # Valid image range is normally 0-255.
    # 999.0 effectively disables this trigger.
    candidate_brightness_threshold: float = 999.0

    # Mean brightness increase from the immediately previous frame.
    candidate_brightness_delta_threshold: float = 2.5

    # Per-pixel positive gray-level increase used to define a bright-change
    # pixel. Valid range is 0-255. Example: 30 means a pixel must brighten by
    # at least 30 gray levels between adjacent frames.
    candidate_bright_pixel_delta_threshold: float = 10.0

    # Fraction of all image pixels that must satisfy the bright-pixel delta
    # threshold. Range is 0.0-1.0. Example: 0.001 means 0.1% of image pixels.
    candidate_bright_pixel_fraction_threshold: float = 0.01


CANDIDATE_CONFIG = CandidateConfig()
