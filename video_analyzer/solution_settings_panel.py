"""Solution-filter settings panel for the desktop analyzer."""

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
    """Allow experimental SolutionFilter settings to be changed."""

    def __init__(
        self,
        config: SolutionConfig,
        apply_callback: Callable[
            [SolutionConfig],
            None,
        ],
    ) -> None:
        super().__init__("Solution filter settings")

        self._apply_callback = apply_callback

        self._pre_trigger_window = QSpinBox()
        self._pre_trigger_window.setRange(
            1,
            500,
        )
        self._pre_trigger_window.setValue(
            config.pre_trigger_noise_window_frames
        )

        self._max_mean_abs_delta = QDoubleSpinBox()
        self._max_mean_abs_delta.setRange(
            0.0,
            100.0,
        )
        self._max_mean_abs_delta.setDecimals(3)
        self._max_mean_abs_delta.setSingleStep(0.05)
        self._max_mean_abs_delta.setValue(
            config.max_pre_trigger_mean_abs_delta
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
            0.5
        )
        self._steady_state_baseline_tolerance.setValue(
            config.steady_state_baseline_tolerance
        )

        form_layout = QFormLayout()

        form_layout.addRow(
            "Pre-trigger noise window:",
            self._pre_trigger_window,
        )

        form_layout.addRow(
            "Max mean |brightness delta|:",
            self._max_mean_abs_delta,
        )

        form_layout.addRow(
            "Steady-state baseline tolerance:",
            self._steady_state_baseline_tolerance,
        )

        self._apply_button = QPushButton(
            "Apply solution settings"
        )

        self._apply_button.clicked.connect(
            self._apply
        )

        layout = QVBoxLayout(self)

        layout.addLayout(
            form_layout
        )

        layout.addWidget(
            self._apply_button
        )

    def _apply(
        self,
    ) -> None:
        config = SolutionConfig(
            pre_trigger_noise_window_frames=(
                self._pre_trigger_window.value()
            ),
            max_pre_trigger_mean_abs_delta=(
                self._max_mean_abs_delta.value()
            ),
            steady_state_baseline_tolerance=(
                self._steady_state_baseline_tolerance.value()
            ),
        )

        self._apply_callback(
            config
        )