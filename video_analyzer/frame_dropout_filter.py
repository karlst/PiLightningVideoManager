"""Reject candidates containing short frame-dropout patterns."""

from __future__ import annotations

import numpy as np

from video_analyzer.solution_types import SolutionResult


class FrameDropoutFilter:
    """Reject candidates with 1-4 very dark frames that recover to baseline."""

    _DROPOUT_BRIGHTNESS_THRESHOLD = 5.0
    _MAX_DROPOUT_FRAMES = 4
    _RETURN_TOLERANCE = 5.0

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        _ = brightness_delta
        _ = trigger_frame_index

        dropout = self._find_dropout(
            brightness
        )

        if dropout is not None:
            (
                start_index,
                dropout_frames,
                baseline_brightness,
                return_brightness,
            ) = dropout

            return SolutionResult(
                is_solution=False,
                reason=(
                    "Frame dropout detected: "
                    f"{dropout_frames} dark frame(s) starting at "
                    f"frame {start_index + 1}; "
                    f"brightness returned from "
                    f"{baseline_brightness:.3f} to "
                    f"{return_brightness:.3f}"
                ),
            )

        return SolutionResult(
            is_solution=True,
            reason="Frame dropout filter passed",
        )

    def _find_dropout(
        self,
        brightness: np.ndarray,
    ) -> tuple[int, int, float, float] | None:
        """Find a short run below threshold followed by recovery to baseline."""

        frame_count = len(brightness)

        if frame_count < 3:
            return None

        index = 1

        while index < frame_count:
            current_brightness = float(
                brightness[index]
            )

            if (
                current_brightness >=
                self._DROPOUT_BRIGHTNESS_THRESHOLD
            ):
                index += 1
                continue

            start_index = index
            baseline_brightness = float(
                brightness[start_index - 1]
            )

            dropout_frames = 0

            while (
                index < frame_count and
                float(brightness[index]) <
                self._DROPOUT_BRIGHTNESS_THRESHOLD and
                dropout_frames <
                self._MAX_DROPOUT_FRAMES
            ):
                dropout_frames += 1
                index += 1

            if dropout_frames == 0:
                continue

            # If the dark run continued beyond four frames, it is not the
            # short-dropout pattern this filter is intended to detect.
            if (
                index < frame_count and
                float(brightness[index]) <
                self._DROPOUT_BRIGHTNESS_THRESHOLD
            ):
                while (
                    index < frame_count and
                    float(brightness[index]) <
                    self._DROPOUT_BRIGHTNESS_THRESHOLD
                ):
                    index += 1

                continue

            if index >= frame_count:
                return None

            return_brightness = float(
                brightness[index]
            )

            if (
                abs(
                    return_brightness -
                    baseline_brightness
                ) <= self._RETURN_TOLERANCE
            ):
                return (
                    start_index,
                    dropout_frames,
                    baseline_brightness,
                    return_brightness,
                )

            index += 1

        return None
