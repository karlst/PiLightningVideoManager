"""
Candidate replay settings panel for the desktop Video Analyzer.

The Analyzer uses the same CandidateFinder thresholds as Pi Camera Capture,
but presents them as four replay modes:

    High
    Medium
    Low
    Custom

High, Medium, and Low obtain their values from the shared Candidate
configuration used by Pi Camera Capture and make those controls read-only.
Custom leaves the individual thresholds editable for experimental replay.

Absolute brightness is intentionally not exposed here. Candidate replay keeps
that trigger effectively disabled with the existing 999.0 threshold.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from common.candidate_config import CandidateConfig
from common.candidate_config import get_sensitivity_config



class CandidateSettingsPanel(QGroupBox):
    """Editable CandidateFinder replay controls for Analyzer."""

    # ## Build sensitivity controls and remember the replay callback.
    def __init__(
        self,
        config: CandidateConfig,
        apply_callback: Callable[
            [CandidateConfig],
            None,
        ],
    ) -> None:
        super().__init__(
            "Candidate replay settings"
        )

        self._apply_callback = (
            apply_callback
        )

        self._create_ui()
        self._load_initial_config(
            config
        )

    # ## Construct sensitivity radios, threshold controls, and Apply button.
    def _create_ui(self) -> None:
        outer_layout = QVBoxLayout(
            self
        )

        outer_layout.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        outer_layout.setSpacing(
            8
        )

        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(
            18
        )

        # Sensitivity selection appears on the left side of the panel.
        sensitivity_group = QGroupBox(
            "Sensitivity"
        )

        sensitivity_layout = QVBoxLayout(
            sensitivity_group
        )

        sensitivity_layout.setContentsMargins(
            10,
            8,
            10,
            8,
        )

        self.high_radio = QRadioButton(
            "High"
        )

        self.medium_radio = QRadioButton(
            "Medium"
        )

        self.low_radio = QRadioButton(
            "Low"
        )

        self.custom_radio = QRadioButton(
            "Custom"
        )

        self.sensitivity_buttons = (
            QButtonGroup(
                self
            )
        )

        for button in (
            self.high_radio,
            self.medium_radio,
            self.low_radio,
            self.custom_radio,
        ):
            self.sensitivity_buttons.addButton(
                button
            )

            sensitivity_layout.addWidget(
                button
            )

        sensitivity_layout.addStretch(
            1
        )

        settings_layout.addWidget(
            sensitivity_group
        )

        # Numeric replay settings appear on the right side.
        numeric_widget = QWidget()
        numeric_layout = QGridLayout(
            numeric_widget
        )

        numeric_layout.setContentsMargins(
            0,
            2,
            0,
            0,
        )

        numeric_layout.setHorizontalSpacing(
            12
        )

        numeric_layout.setVerticalSpacing(
            8
        )

        self.brightness_delta_spin = (
            QDoubleSpinBox()
        )

        self.brightness_delta_spin.setRange(
            0.0,
            999.0,
        )

        self.brightness_delta_spin.setDecimals(
            3
        )

        self.brightness_delta_spin.setSingleStep(
            0.1
        )

        self.bright_pixel_delta_spin = (
            QDoubleSpinBox()
        )

        self.bright_pixel_delta_spin.setRange(
            0.0,
            255.0,
        )

        self.bright_pixel_delta_spin.setDecimals(
            1
        )

        self.bright_pixel_delta_spin.setSingleStep(
            1.0
        )

        self.bright_pixel_fraction_spin = (
            QDoubleSpinBox()
        )

        self.bright_pixel_fraction_spin.setRange(
            0.0,
            1.0,
        )

        self.bright_pixel_fraction_spin.setDecimals(
            6
        )

        self.bright_pixel_fraction_spin.setSingleStep(
            0.001
        )

        numeric_layout.addWidget(
            QLabel(
                "Brightness delta threshold:"
            ),
            0,
            0,
        )

        numeric_layout.addWidget(
            self.brightness_delta_spin,
            0,
            1,
        )

        numeric_layout.addWidget(
            QLabel(
                "Bright pixel delta:"
            ),
            1,
            0,
        )

        numeric_layout.addWidget(
            self.bright_pixel_delta_spin,
            1,
            1,
        )

        numeric_layout.addWidget(
            QLabel(
                "Bright pixel fraction:"
            ),
            2,
            0,
        )

        numeric_layout.addWidget(
            self.bright_pixel_fraction_spin,
            2,
            1,
        )

        numeric_layout.setColumnStretch(
            0,
            1
        )

        numeric_layout.setColumnStretch(
            1,
            2
        )

        settings_layout.addWidget(
            numeric_widget,
            stretch=1,
        )

        outer_layout.addLayout(
            settings_layout
        )

        self.apply_button = QPushButton(
            "Apply replay settings"
        )

        outer_layout.addWidget(
            self.apply_button
        )

        self.high_radio.toggled.connect(
            lambda checked:
                self._sensitivity_selected(
                    "high",
                    checked,
                )
        )

        self.medium_radio.toggled.connect(
            lambda checked:
                self._sensitivity_selected(
                    "medium",
                    checked,
                )
        )

        self.low_radio.toggled.connect(
            lambda checked:
                self._sensitivity_selected(
                    "low",
                    checked,
                )
        )

        self.custom_radio.toggled.connect(
            lambda checked:
                self._custom_selected(
                    checked
                )
        )

        self.apply_button.clicked.connect(
            self._apply
        )

    # ## Select the matching standard profile, otherwise start in Custom mode.
    def _load_initial_config(
        self,
        config: CandidateConfig,
    ) -> None:
        self._set_numeric_values(
            config.
                candidate_brightness_delta_threshold,
            config.
                candidate_bright_pixel_delta_threshold,
            config.
                candidate_bright_pixel_fraction_threshold,
        )

        profile_name = (
            self._matching_profile(
                config
            )
        )

        if profile_name == "high":
            self.high_radio.setChecked(
                True
            )
        elif profile_name == "medium":
            self.medium_radio.setChecked(
                True
            )
        elif profile_name == "low":
            self.low_radio.setChecked(
                True
            )
        else:
            self.custom_radio.setChecked(
                True
            )

    # ## Return the shared sensitivity profile matching an existing config.
    def _matching_profile(
        self,
        config: CandidateConfig,
    ) -> str | None:
        for profile_name in (
            "high",
            "medium",
            "low",
        ):
            profile = (
                get_sensitivity_config(
                    profile_name
                )
            )

            if (
                abs(
                    config.
                    candidate_brightness_delta_threshold
                    - profile.
                    candidate_brightness_delta_threshold
                ) < 1.0e-9
                and abs(
                    config.
                    candidate_bright_pixel_delta_threshold
                    - profile.
                    candidate_bright_pixel_delta_threshold
                ) < 1.0e-9
                and abs(
                    config.
                    candidate_bright_pixel_fraction_threshold
                    - profile.
                    candidate_bright_pixel_fraction_threshold
                ) < 1.0e-9
            ):
                return profile_name

        return None

    # ## Populate and lock threshold controls for High, Medium, or Low.
    def _sensitivity_selected(
        self,
        profile_name: str,
        checked: bool,
    ) -> None:
        if not checked:
            return

        profile = (
            get_sensitivity_config(
                profile_name
            )
        )

        self._set_numeric_values(
            profile.
                candidate_brightness_delta_threshold,
            profile.
                candidate_bright_pixel_delta_threshold,
            profile.
                candidate_bright_pixel_fraction_threshold,
        )

        self._set_numeric_enabled(
            False
        )

    # ## Enable individual threshold editing when Custom is selected.
    def _custom_selected(
        self,
        checked: bool,
    ) -> None:
        if checked:
            self._set_numeric_enabled(
                True
            )

    # ## Populate all three visible Candidate replay threshold fields.
    def _set_numeric_values(
        self,
        brightness_delta: float,
        bright_pixel_delta: float,
        bright_pixel_fraction: float,
    ) -> None:
        self.brightness_delta_spin.setValue(
            float(
                brightness_delta
            )
        )

        self.bright_pixel_delta_spin.setValue(
            float(
                bright_pixel_delta
            )
        )

        self.bright_pixel_fraction_spin.setValue(
            float(
                bright_pixel_fraction
            )
        )

    # ## Enable or disable all individual threshold editors together.
    def _set_numeric_enabled(
        self,
        enabled: bool,
    ) -> None:
        self.brightness_delta_spin.setEnabled(
            enabled
        )

        self.bright_pixel_delta_spin.setEnabled(
            enabled
        )

        self.bright_pixel_fraction_spin.setEnabled(
            enabled
        )

    # ## Build CandidateConfig from displayed values and rerun Candidate replay.
    def _apply(self) -> None:
        config = CandidateConfig(
            # Absolute-brightness replay remains effectively disabled.
            candidate_brightness_threshold=999.0,

            candidate_brightness_delta_threshold=(
                self.brightness_delta_spin.value()
            ),

            candidate_bright_pixel_delta_threshold=(
                self.bright_pixel_delta_spin.value()
            ),

            candidate_bright_pixel_fraction_threshold=(
                self.bright_pixel_fraction_spin.value()
            ),
        )

        self._apply_callback(
            config
        )
