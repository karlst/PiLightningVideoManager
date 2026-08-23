"""Run the desktop-only Solution filters."""

from __future__ import annotations
import numpy as np
from video_analyzer.bright_pixel_no_return_filter import BrightPixelNoReturnFilter
from video_analyzer.brightness_noise_filter import BrightnessNoiseFilter
from video_analyzer.frame_dropout_filter import FrameDropoutFilter
from video_analyzer.solution_config import SOLUTION_CONFIG, SolutionConfig
from video_analyzer.stair_step_decay_filter import StairStepDecayFilter
from video_analyzer.steady_state_change_filter import SteadyStateChangeFilter
from video_analyzer.strong_transient_filter import StrongTransientFilter
from video_analyzer.solution_types import CATEGORY_FAILED_CANDIDATE, CATEGORY_TRUE_FLASH, SolutionResult, SolutionRule

def failed_candidate_result() -> SolutionResult:
    return SolutionResult(False, CATEGORY_FAILED_CANDIDATE, "Failed candidate selection")

class SolutionFilter:
    def __init__(self, config: SolutionConfig = SOLUTION_CONFIG) -> None:
        self._frame_dropout_filter = FrameDropoutFilter()
        self._stair_step_decay_filter = StairStepDecayFilter(
            transient_recovery_frames=config.stair_step_transient_recovery_frames,
            transient_recovery_fraction=config.stair_step_transient_recovery_fraction,
            step_separation_frames=config.stair_step_separation_frames,
            rebrightening_fraction=config.stair_step_rebrightening_fraction,
        )
        self._strong_transient_filter = StrongTransientFilter()
        self._bright_pixel_no_return_filter = BrightPixelNoReturnFilter()
        self._rejection_filters: list[SolutionRule] = [
            BrightnessNoiseFilter(
                window_frames=config.brightness_noise_window_frames,
                trigger_exclusion_frames=config.brightness_noise_trigger_exclusion_frames,
                minimum_delta_magnitude=config.brightness_noise_min_delta_magnitude,
                max_delta_fraction=config.brightness_noise_max_delta_fraction,
                minimum_meaningful_samples=config.brightness_noise_min_meaningful_samples,
                minimum_sign_changes=config.brightness_noise_min_sign_changes,
            ),
            SteadyStateChangeFilter(
                baseline_frames=config.steady_state_baseline_frames,
                baseline_tolerance=config.steady_state_baseline_tolerance,
                rise_threshold=config.steady_state_rise_threshold,
                steady_neighborhood=config.steady_state_neighborhood,
                min_steady_frames=config.steady_state_min_frames,
                search_frames=config.steady_state_search_frames,
            ),
        ]

    def evaluate(self, brightness, brightness_delta, trigger_frame_index, trigger_reason=""):
        result = self._frame_dropout_filter.evaluate(brightness, brightness_delta, trigger_frame_index)
        if not result.is_solution: return result
        result = self._stair_step_decay_filter.evaluate(brightness, brightness_delta, trigger_frame_index)
        if not result.is_solution: return result
        result = self._strong_transient_filter.evaluate(brightness, brightness_delta, trigger_frame_index)
        if result.is_solution: return result
        if "bright pixel trigger" in trigger_reason.lower():
            result = self._bright_pixel_no_return_filter.evaluate(brightness, brightness_delta, trigger_frame_index)
            if not result.is_solution: return result
        for solution_filter in self._rejection_filters:
            result = solution_filter.evaluate(brightness, brightness_delta, trigger_frame_index)
            if not result.is_solution: return result
        return SolutionResult(True, CATEGORY_TRUE_FLASH, "All solution filters passed")
