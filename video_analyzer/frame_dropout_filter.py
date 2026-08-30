"""
Detect frame-dropout anomalies immediately before or at the Candidate trigger.

Two related dropout signatures are recognized:

1. Hard / near-black dropout

       normal image brightness
           ->
       sudden collapse to nearly black
           ->
       Candidate trigger

2. Relative / short-notch dropout

       stable local brightness
           ->
       one- or two-frame downward excursion
           ->
       immediate return near the original local baseline

The second signature catches partial frame corruption that does not approach
black but is still far larger than the normal local frame-to-frame brightness
variation. Local noise is estimated with median absolute deviation (MAD).

Frame-dropout filtering intentionally runs before strong-transient detection,
because recovery from a dropout can otherwise look like a strong positive
transient.
"""

from __future__ import annotations

import numpy as np

from video_analyzer.solution_types import SolutionResult


class FrameDropoutFilter:
    """Detect hard and relative short-duration frame dropouts."""

    def __init__(
        self,
        pre_trigger_search_frames: int = 10,
        hard_brightness_threshold: float = 5.0,
        hard_minimum_brightness_drop: float = 20.0,
        hard_baseline_frames: int = 3,
        relative_baseline_frames: int = 10,
        relative_minimum_drop: float = 0.25,
        relative_mad_multiplier: float = 8.0,
        relative_max_duration_frames: int = 2,
        relative_recovery_tolerance: float = 0.15,
        relative_recovery_mad_multiplier: float = 3.0,
        relative_recovery_search_frames: int = 2,
    ) -> None:
        self._pre_trigger_search_frames = int(
            pre_trigger_search_frames
        )
        self._hard_brightness_threshold = float(
            hard_brightness_threshold
        )
        self._hard_minimum_brightness_drop = float(
            hard_minimum_brightness_drop
        )
        self._hard_baseline_frames = int(
            hard_baseline_frames
        )
        self._relative_baseline_frames = int(
            relative_baseline_frames
        )
        self._relative_minimum_drop = float(
            relative_minimum_drop
        )
        self._relative_mad_multiplier = float(
            relative_mad_multiplier
        )
        self._relative_max_duration_frames = max(
            1,
            int(relative_max_duration_frames),
        )
        self._relative_recovery_tolerance = float(
            relative_recovery_tolerance
        )
        self._relative_recovery_mad_multiplier = float(
            relative_recovery_mad_multiplier
        )
        self._relative_recovery_search_frames = max(
            1,
            int(relative_recovery_search_frames),
        )

    def evaluate(
        self,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
        trigger_frame_index: int | None,
    ) -> SolutionResult:
        # FDA detection uses absolute brightness. Adjacent-frame delta is not
        # required because the relevant changes are measured directly here.
        _ = brightness_delta

        hard_result = self._find_hard_dropout(
            brightness,
            trigger_frame_index,
        )

        if hard_result is not None:
            (
                dropout_frame,
                pre_dropout_brightness,
                dropout_brightness,
            ) = hard_result

            return SolutionResult(
                is_solution=False,
                category="FRAME_DROPOUT",
                reason=(
                    "Hard frame dropout detected: "
                    f"frame {dropout_frame + 1}, "
                    f"brightness "
                    f"{pre_dropout_brightness:.3f} -> "
                    f"{dropout_brightness:.3f}"
                ),
            )

        relative_result = self._find_relative_dropout(
            brightness,
            trigger_frame_index,
        )

        if relative_result is not None:
            (
                dropout_start,
                dropout_end,
                baseline_brightness,
                dropout_brightness,
                recovery_frame,
                recovery_brightness,
                local_mad,
                required_drop,
                allowed_recovery_error,
            ) = relative_result

            return SolutionResult(
                is_solution=False,
                category="FRAME_DROPOUT",
                reason=(
                    "Relative frame dropout detected: "
                    f"frames {dropout_start + 1}-{dropout_end + 1}, "
                    f"baseline {baseline_brightness:.3f} -> "
                    f"dropout {dropout_brightness:.3f} -> "
                    f"recovery frame {recovery_frame + 1} "
                    f"{recovery_brightness:.3f}; "
                    f"drop {baseline_brightness - dropout_brightness:.3f} "
                    f">= {required_drop:.3f}; "
                    f"MAD {local_mad:.3f}; "
                    f"recovery error "
                    f"{abs(recovery_brightness - baseline_brightness):.3f} "
                    f"<= {allowed_recovery_error:.3f}"
                ),
            )

        return SolutionResult(
            is_solution=True,
            category="TRUE_FLASH",
            reason="Frame dropout filter passed",
        )

    def _find_hard_dropout(
        self,
        brightness: np.ndarray,
        trigger_frame_index: int | None,
    ) -> tuple[int, float, float] | None:
        """Preserve the original near-black dropout test."""
        if trigger_frame_index is None:
            return None

        frame_count = len(
            brightness
        )

        if not (
            0 <= trigger_frame_index < frame_count
        ):
            return None

        search_start = max(
            self._hard_baseline_frames,
            trigger_frame_index -
            self._pre_trigger_search_frames,
        )

        # Include the Candidate trigger frame itself. A partial frame dropout
        # can create the Candidate trigger when the very next frame recovers.
        search_end = min(
            frame_count,
            trigger_frame_index + 1,
        )

        for frame_index in range(
            search_start,
            search_end,
        ):
            dropout_brightness = float(
                brightness[frame_index]
            )

            if not np.isfinite(
                dropout_brightness
            ):
                continue

            if (
                dropout_brightness >=
                self._hard_brightness_threshold
            ):
                continue

            baseline_start = (
                frame_index -
                self._hard_baseline_frames
            )

            pre_dropout_samples = np.asarray(
                brightness[
                    baseline_start:
                    frame_index
                ],
                dtype=np.float64,
            )

            finite_samples = pre_dropout_samples[
                np.isfinite(pre_dropout_samples)
            ]

            if finite_samples.size == 0:
                continue

            pre_dropout_brightness = float(
                np.mean(
                    finite_samples
                )
            )

            brightness_drop = (
                pre_dropout_brightness -
                dropout_brightness
            )

            if (
                brightness_drop >=
                self._hard_minimum_brightness_drop
            ):
                return (
                    frame_index,
                    pre_dropout_brightness,
                    dropout_brightness,
                )

        return None

    def _find_relative_dropout(
        self,
        brightness: np.ndarray,
        trigger_frame_index: int | None,
    ) -> tuple[
        int,
        int,
        float,
        float,
        int,
        float,
        float,
        float,
        float,
    ] | None:
        """
        Find a short downward notch whose magnitude is large relative to the
        local noise and which immediately returns near the pre-dropout level.
        """
        if trigger_frame_index is None:
            return None

        frame_count = len(
            brightness
        )

        if not (
            0 <= trigger_frame_index < frame_count
        ):
            return None

        minimum_history = max(
            1,
            self._relative_baseline_frames,
        )

        search_start = max(
            minimum_history,
            trigger_frame_index -
            self._pre_trigger_search_frames,
        )

        # Include the Candidate trigger frame itself. A partial frame dropout
        # can create the Candidate trigger when the very next frame recovers.
        search_end = min(
            frame_count,
            trigger_frame_index + 1,
        )

        for dropout_start in range(
            search_start,
            search_end,
        ):
            baseline_start = (
                dropout_start -
                self._relative_baseline_frames
            )

            baseline_samples = np.asarray(
                brightness[
                    baseline_start:
                    dropout_start
                ],
                dtype=np.float64,
            )

            finite_baseline = baseline_samples[
                np.isfinite(baseline_samples)
            ]

            if finite_baseline.size < 3:
                continue

            baseline_brightness = float(
                np.median(
                    finite_baseline
                )
            )

            absolute_deviations = np.abs(
                finite_baseline -
                baseline_brightness
            )

            local_mad = float(
                np.median(
                    absolute_deviations
                )
            )

            required_drop = max(
                self._relative_minimum_drop,
                local_mad *
                self._relative_mad_multiplier,
            )

            allowed_recovery_error = max(
                self._relative_recovery_tolerance,
                local_mad *
                self._relative_recovery_mad_multiplier,
            )

            for duration_frames in range(
                1,
                self._relative_max_duration_frames + 1,
            ):
                dropout_end = (
                    dropout_start +
                    duration_frames - 1
                )

                # The notch may begin at the Candidate trigger. Allow the
                # configured one- or two-frame dropout to extend past it so
                # recovery can be verified immediately afterward.
                if dropout_end >= frame_count:
                    break

                dropout_samples = np.asarray(
                    brightness[
                        dropout_start:
                        dropout_end + 1
                    ],
                    dtype=np.float64,
                )

                if not np.all(
                    np.isfinite(dropout_samples)
                ):
                    continue

                # Use the darkest frame in a one- or two-frame notch as the
                # dropout level.
                dropout_brightness = float(
                    np.min(
                        dropout_samples
                    )
                )

                brightness_drop = (
                    baseline_brightness -
                    dropout_brightness
                )

                if brightness_drop < required_drop:
                    continue

                recovery_start = (
                    dropout_end + 1
                )

                recovery_end = min(
                    frame_count,
                    recovery_start +
                    self._relative_recovery_search_frames,
                )

                for recovery_frame in range(
                    recovery_start,
                    recovery_end,
                ):
                    recovery_brightness = float(
                        brightness[
                            recovery_frame
                        ]
                    )

                    if not np.isfinite(
                        recovery_brightness
                    ):
                        continue

                    recovery_error = abs(
                        recovery_brightness -
                        baseline_brightness
                    )

                    if (
                        recovery_error <=
                        allowed_recovery_error
                    ):
                        return (
                            dropout_start,
                            dropout_end,
                            baseline_brightness,
                            dropout_brightness,
                            recovery_frame,
                            recovery_brightness,
                            local_mad,
                            required_drop,
                            allowed_recovery_error,
                        )

        return None
