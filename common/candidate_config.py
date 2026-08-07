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
    # Primary lightning trigger.
    candidate_brightness_delta_threshold: float = 2.5

    # Fraction of pixels that changed.
    # Range: 0.0 - 1.0.
    # 1.0 effectively disables this trigger.
    candidate_changed_pixel_fraction_threshold: float = 1.0

   


CANDIDATE_CONFIG = CandidateConfig()