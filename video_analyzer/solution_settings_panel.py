"""
Solution-filter tuning controls for the desktop Analyzer.

Changing these values affects Analyzer playback classification only.
Pressing Apply constructs a new SolutionConfig and reruns SolutionFilter.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from video_analyzer.solution_config import SolutionConfig


class SolutionSettingsPanel(QGroupBox):
    """Allow experimental Solution-filter settings to be changed."""

    def __init__(
        self,
        config: SolutionConfig,
        apply_callback: Callable[
            [SolutionConfig],
            None,
        ],
    ) -> None:
        super().__init__(
            "Solution filter settings"
        )

        self._apply_callback = (
            apply_callback
        )

        # ----------------------------------------------------------
        # Brightness-noise settings
        # ----------------------------------------------------------

        self._noise_window_frames = (
            QSpinBox()
        )
        self._noise_window_frames.setRange(
            10,
            500,
        )
        self._noise_window_frames.setValue(
            config.
            brightness_noise_window_frames
        )

        self._noise_trigger_exclusion_frames = (
            QSpinBox()
        )
        self._noise_trigger_exclusion_frames.setRange(
            0,
            100,
        )
        self._noise_trigger_exclusion_frames.setValue(
            config.
            brightness_noise_trigger_exclusion_frames
        )

        self._noise_min_delta_magnitude = (
            QDoubleSpinBox()
        )
        self._noise_min_delta_magnitude.setRange(
            0.0,
            100.0,
        )
        self._noise_min_delta_magnitude.setDecimals(
            3
        )
        self._noise_min_delta_magnitude.setSingleStep(
            0.25
        )
        self._noise_min_delta_magnitude.setValue(
            config.
            brightness_noise_min_delta_magnitude
        )
        self._noise_min_delta_magnitude.setKeyboardTracking(
            False
        )

        self._noise_min_meaningful_samples = (
            QSpinBox()
        )
        self._noise_min_meaningful_samples.setRange(
            1,
            500,
        )
        self._noise_min_meaningful_samples.setValue(
            config.
            brightness_noise_min_meaningful_samples
        )

        self._noise_min_sign_changes = (
            QSpinBox()
        )
        self._noise_min_sign_changes.setRange(
            1,
            500,
        )
        self._noise_min_sign_changes.setValue(
            config.
            brightness_noise_min_sign_changes
        )

        # ----------------------------------------------------------
        # Steady-state anomaly settings
        # ----------------------------------------------------------

        self._steady_state_baseline_frames = (
            QSpinBox()
        )
        self._steady_state_baseline_frames.setRange(
            1,
            200,
        )
        self._steady_state_baseline_frames.setValue(
            config.
            steady_state_baseline_frames
        )

        self._steady_state_baseline_tolerance = (
            QDoubleSpinBox()
        )
        self._steady_state_baseline_tolerance.setRange(
            0.0,
            50.0,
        )
        self._steady_state_baseline_tolerance.setDecimals(
            3
        )
        self._steady_state_baseline_tolerance.setSingleStep(
            0.1
        )
        self._steady_state_baseline_tolerance.setValue(
            config.
            steady_state_baseline_tolerance
        )
        self._steady_state_baseline_tolerance.setKeyboardTracking(
            False
        )

        self._steady_state_rise_threshold = (
            QDoubleSpinBox()
        )
        self._steady_state_rise_threshold.setRange(
            0.0,
            100.0,
        )
        self._steady_state_rise_threshold.setDecimals(
            3
        )
        self._steady_state_rise_threshold.setSingleStep(
            0.5
        )
        self._steady_state_rise_threshold.setValue(
            config.
            steady_state_rise_threshold
        )
        self._steady_state_rise_threshold.setKeyboardTracking(
            False
        )

        self._steady_state_neighborhood = (
            QDoubleSpinBox()
        )
        self._steady_state_neighborhood.setRange(
            0.0,
            50.0,
        )
        self._steady_state_neighborhood.setDecimals(
            3
        )
        self._steady_state_neighborhood.setSingleStep(
            0.1
        )
        self._steady_state_neighborhood.setValue(
            config.
            steady_state_neighborhood
        )
        self._steady_state_neighborhood.setKeyboardTracking(
            False
        )

        self._steady_state_min_frames = (
            QSpinBox()
        )
        self._steady_state_min_frames.setRange(
            1,
            500,
        )
        self._steady_state_min_frames.setValue(
            config.
            steady_state_min_frames
        )

        self._steady_state_search_frames = (
            QSpinBox()
        )
        self._steady_state_search_frames.setRange(
            1,
            1000,
        )
        self._steady_state_search_frames.setValue(
            config.
            steady_state_search_frames
        )

        # ----------------------------------------------------------
        # Build the form.
        # ----------------------------------------------------------

        form_layout = QFormLayout()
        form_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        form_layout.setHorizontalSpacing(
            10
        )
        form_layout.setVerticalSpacing(
            8
        )

        form_layout.addRow(
            "Noise window frames:",
            self._noise_window_frames,
        )

        form_layout.addRow(
            "Noise trigger exclusion:",
            self._noise_trigger_exclusion_frames,
        )

        form_layout.addRow(
            "Noise minimum |delta|:",
            self._noise_min_delta_magnitude,
        )

        form_layout.addRow(
            "Noise minimum samples:",
            self._noise_min_meaningful_samples,
        )

        form_layout.addRow(
            "Noise minimum sign changes:",
            self._noise_min_sign_changes,
        )

        form_layout.addRow(
            "SSA baseline frames:",
            self._steady_state_baseline_frames,
        )

        form_layout.addRow(
            "SSA baseline return tolerance:",
            self._steady_state_baseline_tolerance,
        )

        form_layout.addRow(
            "SSA rise above baseline:",
            self._steady_state_rise_threshold,
        )

        form_layout.addRow(
            "SSA steady neighborhood:",
            self._steady_state_neighborhood,
        )

        form_layout.addRow(
            "SSA minimum steady frames:",
            self._steady_state_min_frames,
        )

        form_layout.addRow(
            "SSA post-trigger search frames:",
            self._steady_state_search_frames,
        )

        self._apply_button = QPushButton(
            "Apply solution settings"
        )

        self._apply_button.clicked.connect(
            self._apply
        )

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        layout.setSpacing(
            10
        )

        layout.addLayout(
            form_layout
        )

        layout.addWidget(
            self._apply_button
        )

    def _apply(
        self,
    ) -> None:
        """
        Build one complete SolutionConfig from the UI values.

        The Analyzer callback will rebuild SolutionFilter using this
        temporary configuration and immediately reclassify the clip.
        """

        config = SolutionConfig(

            # Brightness noise settings.
            brightness_noise_window_frames=(
                self._noise_window_frames.value()
            ),
            brightness_noise_trigger_exclusion_frames=(
                self._noise_trigger_exclusion_frames.value()
            ),
            brightness_noise_min_delta_magnitude=(
                self._noise_min_delta_magnitude.value()
            ),
            brightness_noise_min_meaningful_samples=(
                self._noise_min_meaningful_samples.value()
            ),
            brightness_noise_min_sign_changes=(
                self._noise_min_sign_changes.value()
            ),

            # Steady-state settings.
            steady_state_baseline_frames=(
                self._steady_state_baseline_frames.value()
            ),
            steady_state_baseline_tolerance=(
                self._steady_state_baseline_tolerance.value()
            ),
            steady_state_rise_threshold=(
                self._steady_state_rise_threshold.value()
            ),
            steady_state_neighborhood=(
                self._steady_state_neighborhood.value()
            ),
            steady_state_min_frames=(
                self._steady_state_min_frames.value()
            ),
            steady_state_search_frames=(
                self._steady_state_search_frames.value()
            ),
        )

        self._apply_callback(
            config
        )