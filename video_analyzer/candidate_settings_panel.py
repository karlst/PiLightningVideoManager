"""Candidate threshold controls for the desktop video analyzer."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from common.candidate_config import CandidateConfig


class CandidateSettingsPanel(QGroupBox):
    """Editable replay thresholds, independent of the recorded Pi settings."""

    def __init__(
        self,
        replay_config: CandidateConfig,
        capture_config: CandidateConfig,
        on_apply: Callable[[CandidateConfig], None],
    ) -> None:
        super().__init__("Candidate replay settings")

        self._on_apply = on_apply
        self._capture_config = capture_config

        self._capture_delta_label = QLabel(
            f"{capture_config.candidate_brightness_delta_threshold:.3f}"
        )

        self._brightness_spin = QDoubleSpinBox()
        self._configure_spin_box(
            self._brightness_spin,
            minimum=0.0,
            maximum=999.0,
            decimals=3,
            step=0.1,
            value=replay_config.candidate_brightness_threshold,
        )

        self._brightness_delta_spin = QDoubleSpinBox()
        self._configure_spin_box(
            self._brightness_delta_spin,
            minimum=0.0,
            maximum=999.0,
            decimals=3,
            step=0.1,
            value=replay_config.candidate_brightness_delta_threshold,
        )

        self._changed_pixel_fraction_spin = QDoubleSpinBox()
        self._configure_spin_box(
            self._changed_pixel_fraction_spin,
            minimum=0.0,
            maximum=1.0,
            decimals=5,
            step=0.01,
            value=replay_config.candidate_changed_pixel_fraction_threshold,
        )

        form_layout = QFormLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(8)

        form_layout.addRow(
            "Captured delta threshold:",
            self._capture_delta_label,
        )
        form_layout.addRow(
            "Brightness threshold:",
            self._brightness_spin,
        )
        form_layout.addRow(
            "Replay delta threshold:",
            self._brightness_delta_spin,
        )
        form_layout.addRow(
            "Changed pixel fraction:",
            self._changed_pixel_fraction_spin,
        )

        self._apply_button = QPushButton("Apply replay settings")
        self._apply_button.clicked.connect(
            self._apply
        )

        self._reset_button = QPushButton("Reset to captured settings")
        self._reset_button.clicked.connect(
            self._reset_to_capture
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        layout.addLayout(form_layout)
        layout.addWidget(self._apply_button)
        layout.addWidget(self._reset_button)
        layout.addStretch(1)

    @staticmethod
    def _configure_spin_box(
        spin_box: QDoubleSpinBox,
        minimum: float,
        maximum: float,
        decimals: int,
        step: float,
        value: float,
    ) -> None:
        spin_box.setRange(
            minimum,
            maximum,
        )
        spin_box.setDecimals(decimals)
        spin_box.setSingleStep(step)
        spin_box.setValue(value)
        spin_box.setKeyboardTracking(False)

    def _current_config(self) -> CandidateConfig:
        return CandidateConfig(
            candidate_brightness_threshold=(
                self._brightness_spin.value()
            ),
            candidate_brightness_delta_threshold=(
                self._brightness_delta_spin.value()
            ),
            candidate_changed_pixel_fraction_threshold=(
                self._changed_pixel_fraction_spin.value()
            ),
        )

    def _apply(self) -> None:
        self._on_apply(
            self._current_config()
        )

    def _reset_to_capture(self) -> None:
        config = self._capture_config

        self._brightness_spin.setValue(
            config.candidate_brightness_threshold
        )
        self._brightness_delta_spin.setValue(
            config.candidate_brightness_delta_threshold
        )
        self._changed_pixel_fraction_spin.setValue(
            config.candidate_changed_pixel_fraction_threshold
        )

        self._on_apply(config)
