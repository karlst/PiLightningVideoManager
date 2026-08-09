"""
Qt controls for experimenting with CandidateFinder thresholds.

This panel displays editable numeric controls for CandidateFinder settings.
Pressing Apply constructs a temporary CandidateConfig and sends it back to
AnalyzerWindow through the supplied callback. AnalyzerWindow then replays the
saved capture with the shared CandidateFinder and updates the graphs/result.

These desktop changes are experimental playback settings; they do not change
the configuration that was used by the Pi when the clip was captured.
"""


from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
)

from common.candidate_config import CandidateConfig


class CandidateSettingsPanel(QGroupBox):
    """Editable experimental candidate thresholds."""

    def __init__(
        self,
        config: CandidateConfig,
        on_apply: Callable[[CandidateConfig], None],
    ) -> None:
        super().__init__("Candidate replay settings")

        self._on_apply = on_apply

        self._brightness_spin = QDoubleSpinBox()
        self._configure_spin_box(
            self._brightness_spin,
            minimum=0.0,
            maximum=999.0,
            decimals=3,
            step=0.1,
            value=config.candidate_brightness_threshold,
        )

        self._brightness_delta_spin = QDoubleSpinBox()
        self._configure_spin_box(
            self._brightness_delta_spin,
            minimum=0.0,
            maximum=999.0,
            decimals=3,
            step=0.1,
            value=config.candidate_brightness_delta_threshold,
        )

        self._bright_pixel_delta_spin = QDoubleSpinBox()
        self._configure_spin_box(
            self._bright_pixel_delta_spin,
            minimum=0.0,
            maximum=255.0,
            decimals=1,
            step=1.0,
            value=config.candidate_bright_pixel_delta_threshold,
        )

        self._bright_pixel_fraction_spin = QDoubleSpinBox()
        self._configure_spin_box(
            self._bright_pixel_fraction_spin,
            minimum=0.0,
            maximum=1.0,
            decimals=6,
            step=0.0001,
            value=config.candidate_bright_pixel_fraction_threshold,
        )

        form_layout = QFormLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(8)

        form_layout.addRow(
            "Brightness threshold:",
            self._brightness_spin,
        )
        form_layout.addRow(
            "Brightness delta threshold:",
            self._brightness_delta_spin,
        )
        form_layout.addRow(
            "Bright pixel delta:",
            self._bright_pixel_delta_spin,
        )
        form_layout.addRow(
            "Bright pixel fraction:",
            self._bright_pixel_fraction_spin,
        )

        self._apply_button = QPushButton("Apply replay settings")
        self._apply_button.clicked.connect(
            self._apply
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        layout.addLayout(form_layout)
        layout.addWidget(self._apply_button)
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

    def _apply(self) -> None:
        config = CandidateConfig(
            candidate_brightness_threshold=(
                self._brightness_spin.value()
            ),
            candidate_brightness_delta_threshold=(
                self._brightness_delta_spin.value()
            ),
            candidate_bright_pixel_delta_threshold=(
                self._bright_pixel_delta_spin.value()
            ),
            candidate_bright_pixel_fraction_threshold=(
                self._bright_pixel_fraction_spin.value()
            ),
        )

        self._on_apply(config)
