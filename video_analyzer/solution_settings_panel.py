"""Solution-filter tuning controls for the desktop Analyzer."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from video_analyzer.solution_config import SolutionConfig


class SolutionSettingsPanel(QGroupBox):
    """Allow experimental Solution-filter settings to be changed."""

    def __init__(
        self,
        config: SolutionConfig,
        apply_callback: Callable[[SolutionConfig], None],
    ) -> None:
        super().__init__("Solution filter settings")
        self._apply_callback = apply_callback

        # ----------------------------------------------------------
        # Noise
        # ----------------------------------------------------------

        self._noise_window_frames = QSpinBox()
        self._noise_window_frames.setRange(10, 500)
        self._noise_window_frames.setValue(config.brightness_noise_window_frames)

        self._noise_trigger_exclusion_frames = QSpinBox()
        self._noise_trigger_exclusion_frames.setRange(0, 100)
        self._noise_trigger_exclusion_frames.setValue(config.brightness_noise_trigger_exclusion_frames)

        self._noise_min_delta_magnitude = QDoubleSpinBox()
        self._noise_min_delta_magnitude.setRange(0.0, 100.0)
        self._noise_min_delta_magnitude.setDecimals(3)
        self._noise_min_delta_magnitude.setSingleStep(0.25)
        self._noise_min_delta_magnitude.setValue(config.brightness_noise_min_delta_magnitude)
        self._noise_min_delta_magnitude.setKeyboardTracking(False)

        self._noise_max_delta_fraction = QDoubleSpinBox()
        self._noise_max_delta_fraction.setRange(0.0, 1.0)
        self._noise_max_delta_fraction.setDecimals(3)
        self._noise_max_delta_fraction.setSingleStep(0.005)
        self._noise_max_delta_fraction.setValue(config.brightness_noise_max_delta_fraction)
        self._noise_max_delta_fraction.setKeyboardTracking(False)

        self._noise_min_meaningful_samples = QSpinBox()
        self._noise_min_meaningful_samples.setRange(1, 500)
        self._noise_min_meaningful_samples.setValue(config.brightness_noise_min_meaningful_samples)

        self._noise_min_sign_changes = QSpinBox()
        self._noise_min_sign_changes.setRange(1, 500)
        self._noise_min_sign_changes.setValue(config.brightness_noise_min_sign_changes)

        noise_group = QGroupBox("Noise")
        noise_form = QFormLayout(noise_group)
        noise_form.setContentsMargins(6, 3, 6, 3)
        noise_form.setHorizontalSpacing(8)
        noise_form.setVerticalSpacing(0)
        noise_form.addRow("Window frames:", self._noise_window_frames)
        noise_form.addRow("Trigger exclusion:", self._noise_trigger_exclusion_frames)
        noise_form.addRow("Minimum |delta|:", self._noise_min_delta_magnitude)
        noise_form.addRow("Max-delta fraction:", self._noise_max_delta_fraction)
        noise_form.addRow("Minimum samples:", self._noise_min_meaningful_samples)
        noise_form.addRow("Minimum sign changes:", self._noise_min_sign_changes)

        # ----------------------------------------------------------
        # Stair-step
        # ----------------------------------------------------------

        self._stair_step_transient_recovery_frames = QSpinBox()
        self._stair_step_transient_recovery_frames.setRange(1, 20)
        self._stair_step_transient_recovery_frames.setValue(
            config.stair_step_transient_recovery_frames
        )

        self._stair_step_transient_recovery_fraction = QDoubleSpinBox()
        self._stair_step_transient_recovery_fraction.setRange(0.0, 1.0)
        self._stair_step_transient_recovery_fraction.setDecimals(3)
        self._stair_step_transient_recovery_fraction.setSingleStep(0.05)
        self._stair_step_transient_recovery_fraction.setValue(
            config.stair_step_transient_recovery_fraction
        )
        self._stair_step_transient_recovery_fraction.setKeyboardTracking(False)

        self._stair_step_separation_frames = QSpinBox()
        self._stair_step_separation_frames.setRange(1, 20)
        self._stair_step_separation_frames.setValue(
            config.stair_step_separation_frames
        )

        self._stair_step_rebrightening_fraction = QDoubleSpinBox()
        self._stair_step_rebrightening_fraction.setRange(0.0, 1.0)
        self._stair_step_rebrightening_fraction.setDecimals(3)
        self._stair_step_rebrightening_fraction.setSingleStep(0.05)
        self._stair_step_rebrightening_fraction.setValue(
            config.stair_step_rebrightening_fraction
        )
        self._stair_step_rebrightening_fraction.setKeyboardTracking(False)

        stair_step_group = QGroupBox("Stair-step")
        stair_step_form = QFormLayout(stair_step_group)
        stair_step_form.setContentsMargins(6, 3, 6, 3)
        stair_step_form.setHorizontalSpacing(8)
        stair_step_form.setVerticalSpacing(0)
        stair_step_form.addRow(
            "Transient recovery frames:",
            self._stair_step_transient_recovery_frames,
        )
        stair_step_form.addRow(
            "Transient recovery fraction:",
            self._stair_step_transient_recovery_fraction,
        )
        stair_step_form.addRow(
            "Step separation frames:",
            self._stair_step_separation_frames,
        )
        stair_step_form.addRow(
            "Re-brightening fraction:",
            self._stair_step_rebrightening_fraction,
        )

        # ----------------------------------------------------------
        # SSA (Steady State)
        # ----------------------------------------------------------

        self._steady_state_baseline_frames = QSpinBox()
        self._steady_state_baseline_frames.setRange(1, 200)
        self._steady_state_baseline_frames.setValue(config.steady_state_baseline_frames)

        self._steady_state_baseline_tolerance = QDoubleSpinBox()
        self._steady_state_baseline_tolerance.setRange(0.0, 50.0)
        self._steady_state_baseline_tolerance.setDecimals(3)
        self._steady_state_baseline_tolerance.setSingleStep(0.1)
        self._steady_state_baseline_tolerance.setValue(config.steady_state_baseline_tolerance)
        self._steady_state_baseline_tolerance.setKeyboardTracking(False)

        self._steady_state_rise_threshold = QDoubleSpinBox()
        self._steady_state_rise_threshold.setRange(0.0, 100.0)
        self._steady_state_rise_threshold.setDecimals(3)
        self._steady_state_rise_threshold.setSingleStep(0.5)
        self._steady_state_rise_threshold.setValue(config.steady_state_rise_threshold)
        self._steady_state_rise_threshold.setKeyboardTracking(False)

        self._steady_state_neighborhood = QDoubleSpinBox()
        self._steady_state_neighborhood.setRange(0.0, 50.0)
        self._steady_state_neighborhood.setDecimals(3)
        self._steady_state_neighborhood.setSingleStep(0.1)
        self._steady_state_neighborhood.setValue(config.steady_state_neighborhood)
        self._steady_state_neighborhood.setKeyboardTracking(False)

        self._steady_state_min_frames = QSpinBox()
        self._steady_state_min_frames.setRange(1, 500)
        self._steady_state_min_frames.setValue(config.steady_state_min_frames)

        self._steady_state_search_frames = QSpinBox()
        self._steady_state_search_frames.setRange(1, 1000)
        self._steady_state_search_frames.setValue(config.steady_state_search_frames)

        steady_state_group = QGroupBox("SSA (Steady State)")
        steady_state_form = QFormLayout(steady_state_group)
        steady_state_form.setContentsMargins(6, 3, 6, 3)
        steady_state_form.setHorizontalSpacing(8)
        steady_state_form.setVerticalSpacing(0)
        steady_state_form.addRow("Baseline frames:", self._steady_state_baseline_frames)
        steady_state_form.addRow("Return tolerance:", self._steady_state_baseline_tolerance)
        steady_state_form.addRow("Rise threshold:", self._steady_state_rise_threshold)
        steady_state_form.addRow("Steady tolerance:", self._steady_state_neighborhood)
        steady_state_form.addRow("Minimum steady frames:", self._steady_state_min_frames)
        steady_state_form.addRow("Search frames:", self._steady_state_search_frames)

        self._apply_button = QPushButton("Apply Settings")
        self._apply_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self._apply_button.setMinimumHeight(36)
        self._apply_button.clicked.connect(self._apply)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)
        layout.addWidget(noise_group)
        layout.addWidget(stair_step_group)
        layout.addWidget(steady_state_group)
        layout.addWidget(self._apply_button)

    def set_noise_max_delta_fraction(
        self,
        value: float,
    ) -> None:
        """Update the visible sensitivity-dependent noise fraction."""

        self._noise_max_delta_fraction.setValue(
            float(value)
        )

    def _apply(self) -> None:
        config = SolutionConfig(
            brightness_noise_window_frames=self._noise_window_frames.value(),
            brightness_noise_trigger_exclusion_frames=self._noise_trigger_exclusion_frames.value(),
            brightness_noise_min_delta_magnitude=self._noise_min_delta_magnitude.value(),
            brightness_noise_max_delta_fraction=self._noise_max_delta_fraction.value(),
            brightness_noise_min_meaningful_samples=self._noise_min_meaningful_samples.value(),
            brightness_noise_min_sign_changes=self._noise_min_sign_changes.value(),
            stair_step_transient_recovery_frames=(
                self._stair_step_transient_recovery_frames.value()
            ),
            stair_step_transient_recovery_fraction=(
                self._stair_step_transient_recovery_fraction.value()
            ),
            stair_step_separation_frames=(
                self._stair_step_separation_frames.value()
            ),
            stair_step_rebrightening_fraction=(
                self._stair_step_rebrightening_fraction.value()
            ),
            steady_state_baseline_frames=self._steady_state_baseline_frames.value(),
            steady_state_baseline_tolerance=self._steady_state_baseline_tolerance.value(),
            steady_state_rise_threshold=self._steady_state_rise_threshold.value(),
            steady_state_neighborhood=self._steady_state_neighborhood.value(),
            steady_state_min_frames=self._steady_state_min_frames.value(),
            steady_state_search_frames=self._steady_state_search_frames.value(),
        )
        self._apply_callback(config)

class SolutionSettingsDialog(QDialog):
    """Modeless window containing the Analyzer SolutionFilter tuning controls."""

    def __init__(
        self,
        parent: QWidget,
        config: SolutionConfig,
        apply_callback: Callable[[SolutionConfig], None],
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Solution Filter Settings")
        self.setWindowModality(Qt.WindowModality.NonModal)

        self.settings_panel = SolutionSettingsPanel(
            config,
            apply_callback,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.settings_panel)

    def set_noise_max_delta_fraction(
        self,
        value: float,
    ) -> None:
        """Keep the visible sensitivity-dependent Solution setting synchronized."""

        self.settings_panel.set_noise_max_delta_fraction(
            value
        )

