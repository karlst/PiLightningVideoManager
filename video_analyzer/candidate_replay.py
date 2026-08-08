"""Replay archived/reconstructed frame metrics through CandidateFinder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from common.candidate_config import CANDIDATE_CONFIG
from common.candidate_config import CandidateConfig
from common.candidate_finder import CandidateFinder
from video_analyzer.capture_data import CaptureData
from video_analyzer.capture_data import build_bright_pixel_fraction


@dataclass(frozen=True)
class CandidateReplayResult:
    frame_index: int | None
    reason: str

    @property
    def found(self) -> bool:
        return self.frame_index is not None


def replay_candidate_finder(
    capture_data: CaptureData,
    config: CandidateConfig = CANDIDATE_CONFIG,
) -> CandidateReplayResult:
    """Return the first trigger frame found using the supplied config."""

    candidate_finder = CandidateFinder(
        config
    )

    bright_pixel_fraction = build_bright_pixel_fraction(
        capture_data.positive_delta_histograms,
        config.candidate_bright_pixel_delta_threshold,
    )

    for frame_index in range(
        capture_data.frame_count
    ):
        metric = {
            "mean_brightness": _array_value(
                capture_data.pi_brightness,
                capture_data.replay_brightness,
                frame_index,
            ),
            "brightness_delta_adjacent": _array_value(
                capture_data.pi_brightness_delta,
                capture_data.replay_brightness_delta,
                frame_index,
            ),
            "bright_pixel_fraction": _array_item(
                bright_pixel_fraction,
                frame_index,
                0.0,
            ),
        }

        found, reason = candidate_finder.evaluate(
            metric
        )

        if found:
            return CandidateReplayResult(
                frame_index=frame_index,
                reason=reason,
            )

    return CandidateReplayResult(
        frame_index=None,
        reason="",
    )


def get_bright_pixel_fraction(
    capture_data: CaptureData,
    config: CandidateConfig,
) -> np.ndarray:
    """Build the playback bright-pixel fraction array for display/inspection."""

    return build_bright_pixel_fraction(
        capture_data.positive_delta_histograms,
        config.candidate_bright_pixel_delta_threshold,
    )


def _array_value(
    preferred: np.ndarray,
    fallback: np.ndarray,
    frame_index: int,
) -> float:
    value = _array_item(
        preferred,
        frame_index,
        np.nan,
    )

    if np.isfinite(value):
        return value

    return _array_item(
        fallback,
        frame_index,
        0.0,
    )


def _array_item(
    values: np.ndarray,
    frame_index: int,
    default: float,
) -> float:
    if 0 <= frame_index < len(values):
        try:
            return float(
                values[frame_index]
            )
        except (TypeError, ValueError):
            pass

    return float(default)
