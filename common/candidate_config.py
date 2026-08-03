"""
@file trigger_config.py

@brief Shared trigger configuration used by live capture and video replay.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TriggerConfig:
    trigger_enabled: bool = True

    # Triggers on absolute mean frame brightness.
    # Valid image range is normally 0-255.
    # 999.0 effectively disables this trigger.
    trigger_brightness_threshold: float = 999.0

    # Mean brightness increase from the immediately previous frame.
    # Primary lightning trigger.
    trigger_brightness_delta_threshold: float = 5.0

    # Fraction of pixels that changed.
    # Range: 0.0 - 1.0.
    # 1.0 effectively disables this trigger.
    trigger_changed_pixel_fraction_threshold: float = 1.0

    # Minimum time between automatic trigger events.
    trigger_cooldown_seconds: float = 1.0


TRIGGER_CONFIG = TriggerConfig()