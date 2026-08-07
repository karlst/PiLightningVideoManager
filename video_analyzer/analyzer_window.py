"""Qt main window for the desktop video analyzer."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from common.candidate_config import CANDIDATE_CONFIG
from common.candidate_config import CandidateConfig
from video_analyzer.candidate_replay import CandidateReplayResult
from video_analyzer.candidate_replay import replay_candidate_finder
from video_analyzer.candidate_settings_panel import CandidateSettingsPanel
from video_analyzer.capture_data import CaptureData
from video_analyzer.graph_panel import GraphPanel
from video_analyzer.solution_filter import SolutionResult
from video_analyzer.solution_panel import SolutionPanel
from video_analyzer.version import VERSION
from video_analyzer.video_reader import VideoReader


def format_value(
    value: Any,
    default: str = "—",
) -> str:
    if value is None:
        return default

    return str(value)


def format_number(
    value: Any,
    decimals: int = 3,
    suffix: str = "",
) -> str:
    if value is None:
        return "—"

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    return f"{number:.{decimals}f}{suffix}"


class AnalyzerWindow(QMainWindow):
    def __init__(
        self,
        capture_data: CaptureData,
        candidate_result: CandidateReplayResult,
        solution_result: SolutionResult,
    ) -> None:
        super().__init__()

        self.capture_data = capture_data
        self.candidate_result = candidate_result
        self.solution_result = solution_result
        self.candidate_config = CANDIDATE_CONFIG
        self.frame_number = 0
        self.updating_slider = False

        self.video_reader = VideoReader(
            capture_data.video_path
        )

        self.setWindowTitle(
            f"Video Frame Analyzer — v{VERSION}"
        )
        self.resize(1500, 1050)

        self.create_ui()
        self.connect_controls()

        self.update_capture_information()
        self.set_frame(0, force=True)

    def create_information_group(
        self,
        title: str,
        fields: list[tuple[str, str]],
    ) -> tuple[QGroupBox, dict[str, QLabel]]:
        group = QGroupBox(title)
        layout = QGridLayout(group)

        layout.setContentsMargins(8, 6, 8, 6)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(1)

        value_labels: dict[str, QLabel] = {}

        for row, (key, label_text) in enumerate(fields):
            title_label = QLabel(f"{label_text}:")
            value_label = QLabel("—")

            title_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter
            )
            value_label.setAlignment(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter
            )
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )

            layout.addWidget(
                title_label,
                row,
                0,
            )
            layout.addWidget(
                value_label,
                row,
                1,
            )

            value_labels[key] = value_label

        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        return group, value_labels

    def create_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        workspace_layout = QGridLayout()
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setHorizontalSpacing(6)
        workspace_layout.setVerticalSpacing(6)

        workspace_layout.setColumnStretch(0, 7)
        workspace_layout.setColumnStretch(1, 3)
        workspace_layout.setRowStretch(0, 3)
        workspace_layout.setRowStretch(1, 2)

        self.image_label = QLabel()
        self.image_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.image_label.setMinimumHeight(300)
        self.image_label.setStyleSheet(
            "QLabel { background-color: black; }"
        )

        workspace_layout.addWidget(
            self.image_label,
            0,
            0,
        )

        information_widget = QWidget()
        information_layout = QVBoxLayout(
            information_widget
        )
        information_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        information_layout.setSpacing(4)

        capture_fields = [
            ("video", "Video"),
            ("sidecar", "Sidecar"),
            ("capture_start", "Capture start UTC"),
            ("capture_duration", "Duration"),
            ("trigger", "Trigger"),
            ("trigger_frame", "Pi trigger frame"),
            ("replay_trigger_frame", "Replay trigger frame"),
            ("replay_result", "Replay result"),
            ("trigger_offset", "Trigger offset"),
            ("frame_count", "Frame count"),
        ]

        frame_fields = [
            ("frame_number", "Frame"),
            ("timestamp_utc", "Timestamp UTC"),
            ("offset", "Offset"),
            ("sequence", "Sequence"),
            ("picture_type", "Encoded type"),
            ("key_frame", "Key frame"),
            ("pi_brightness", "Pi brightness"),
            ("pi_brightness_delta", "Pi brightness change"),
        ]

        (
            capture_group,
            self.capture_value_labels,
        ) = self.create_information_group(
            "Capture information",
            capture_fields,
        )

        (
            frame_group,
            self.frame_value_labels,
        ) = self.create_information_group(
            "Current frame",
            frame_fields,
        )

        information_layout.addWidget(
            capture_group
        )
        information_layout.addWidget(
            frame_group
        )
        information_layout.addStretch(1)

        workspace_layout.addWidget(
            information_widget,
            0,
            1,
        )

        self.graph_panel = GraphPanel(
            self.capture_data,
            self.candidate_result,
            self.candidate_config,
        )

        workspace_layout.addWidget(
            self.graph_panel,
            1,
            0,
        )

        lower_right_widget = QWidget()
        lower_right_layout = QVBoxLayout(
            lower_right_widget
        )
        lower_right_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        lower_right_layout.setSpacing(6)

        self.solution_panel = SolutionPanel(
            self.solution_result
        )

        self.candidate_settings_panel = (
            CandidateSettingsPanel(
                self.candidate_config,
                self.apply_candidate_settings,
            )
        )

        lower_right_layout.addWidget(
            self.solution_panel
        )
        lower_right_layout.addWidget(
            self.candidate_settings_panel,
            stretch=1,
        )

        workspace_layout.addWidget(
            lower_right_widget,
            1,
            1,
        )

        main_layout.addLayout(
            workspace_layout,
            stretch=1,
        )

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        self.first_button = QPushButton("|<")
        self.previous_button = QPushButton("<")
        self.next_button = QPushButton(">")
        self.last_button = QPushButton(">|")

        self.frame_slider = QSlider(
            Qt.Orientation.Horizontal
        )
        self.frame_slider.setRange(
            0,
            max(0, self.capture_data.frame_count - 1),
        )
        self.frame_slider.setSingleStep(1)
        self.frame_slider.setPageStep(10)

        self.slider_frame_label = QLabel(
            f"0 / {self.capture_data.frame_count - 1}"
        )
        self.slider_frame_label.setMinimumWidth(100)

        controls_layout.addWidget(self.first_button)
        controls_layout.addWidget(self.previous_button)
        controls_layout.addWidget(
            self.frame_slider,
            stretch=1,
        )
        controls_layout.addWidget(self.slider_frame_label)
        controls_layout.addWidget(self.next_button)
        controls_layout.addWidget(self.last_button)

        main_layout.addLayout(
            controls_layout
        )

    def connect_controls(self) -> None:
        self.first_button.clicked.connect(
            lambda: self.set_frame(0)
        )
        self.previous_button.clicked.connect(
            lambda: self.set_frame(
                self.frame_number - 1
            )
        )
        self.next_button.clicked.connect(
            lambda: self.set_frame(
                self.frame_number + 1
            )
        )
        self.last_button.clicked.connect(
            lambda: self.set_frame(
                self.capture_data.frame_count - 1
            )
        )
        self.frame_slider.valueChanged.connect(
            self.on_slider_changed
        )

    def apply_candidate_settings(
        self,
        config: CandidateConfig,
    ) -> None:
        """Replay the archived Pi metrics using experimental thresholds."""

        self.candidate_config = config
        self.candidate_result = replay_candidate_finder(
            self.capture_data.sidecar,
            config,
        )

        self.graph_panel.update_candidate_result(
            self.candidate_result,
            self.candidate_config,
        )

        self.update_trigger_replay_information()

    def frame_to_pixmap(
        self,
        frame: np.ndarray,
    ) -> QPixmap:
        rgb_frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB,
        )

        height, width, channels = rgb_frame.shape
        bytes_per_line = width * channels

        image = QImage(
            rgb_frame.data,
            width,
            height,
            bytes_per_line,
            QImage.Format.Format_RGB888,
        ).copy()

        return QPixmap.fromImage(image)

    def display_frame(
        self,
        frame: np.ndarray,
    ) -> None:
        pixmap = self.frame_to_pixmap(frame)

        scaled_pixmap = pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.image_label.setPixmap(
            scaled_pixmap
        )

    def update_capture_information(self) -> None:
        capture_labels = self.capture_value_labels
        sidecar = self.capture_data.sidecar

        capture_labels["video"].setText(
            self.capture_data.video_path.name
        )
        capture_labels["sidecar"].setText(
            self.capture_data.sidecar_path.name
            if sidecar is not None
            else "Not found"
        )

        if sidecar is None:
            self.update_trigger_replay_information()
            return

        capture_labels["capture_start"].setText(
            format_value(
                sidecar.get("capture_start_utc")
            )
        )
        capture_labels["capture_duration"].setText(
            format_number(
                sidecar.get("capture_duration_ms"),
                3,
                " ms",
            )
        )

        trigger_display = (
            sidecar.get("trigger_display")
            or sidecar.get("trigger_type")
            or sidecar.get("trigger_reason")
        )

        capture_labels["trigger"].setText(
            format_value(trigger_display)
        )

        trigger_frame_index = (
            self.capture_data.original_trigger_frame_index
        )
        trigger_frame_number = (
            trigger_frame_index + 1
            if trigger_frame_index is not None
            else None
        )

        capture_labels["trigger_frame"].setText(
            format_value(trigger_frame_number)
        )

        capture_labels["trigger_offset"].setText(
            format_number(
                sidecar.get("trigger_offset_ms"),
                3,
                " ms",
            )
        )
        capture_labels["frame_count"].setText(
            format_value(
                sidecar.get("frame_count")
            )
        )

        self.update_trigger_replay_information()

    def update_trigger_replay_information(self) -> None:
        capture_labels = self.capture_value_labels
        trigger_frame_index = (
            self.capture_data.original_trigger_frame_index
        )
        replay_frame_index = self.candidate_result.frame_index

        replay_frame_number = (
            replay_frame_index + 1
            if replay_frame_index is not None
            else None
        )

        capture_labels["replay_trigger_frame"].setText(
            format_value(replay_frame_number)
        )

        if trigger_frame_index is None:
            replay_result = "Pi trigger unavailable"
        elif replay_frame_index is None:
            replay_result = "NO REPLAY TRIGGER"
        elif replay_frame_index == trigger_frame_index:
            replay_result = "MATCH"
        else:
            difference = (
                replay_frame_index - trigger_frame_index
            )
            replay_result = f"DIFF {difference:+d} frames"

        capture_labels["replay_result"].setText(
            replay_result
        )

    def update_frame_information(self) -> None:
        labels = self.frame_value_labels
        frame_count = self.capture_data.frame_count

        labels["frame_number"].setText(
            f"{self.frame_number + 1} / {frame_count}"
        )

        encoded_info: dict[str, Any] = {}

        if self.frame_number < len(
            self.capture_data.frame_info
        ):
            encoded_info = self.capture_data.frame_info[
                self.frame_number
            ]

        picture_type = encoded_info.get(
            "pict_type",
            "—",
        )
        key_frame = encoded_info.get(
            "key_frame",
            "—",
        )
        ffprobe_time = encoded_info.get(
            "best_effort_timestamp_time"
        )

        record = self.capture_data.frame_records.get(
            self.frame_number,
            {},
        )

        timestamp_utc = record.get("timestamp_utc")
        offset_ms = record.get("offset_ms")
        sequence_number = record.get("sequence_number")

        if offset_ms is None and ffprobe_time is not None:
            try:
                offset_ms = float(ffprobe_time) * 1000.0
            except (TypeError, ValueError):
                offset_ms = None

        labels["timestamp_utc"].setText(
            format_value(timestamp_utc)
        )
        labels["offset"].setText(
            format_number(
                offset_ms,
                3,
                " ms",
            )
        )
        labels["sequence"].setText(
            format_value(sequence_number)
        )
        labels["picture_type"].setText(
            format_value(picture_type)
        )
        labels["key_frame"].setText(
            format_value(key_frame)
        )

        pi_brightness = (
            self.capture_data.pi_brightness[
                self.frame_number
            ]
        )
        pi_delta = (
            self.capture_data.pi_brightness_delta[
                self.frame_number
            ]
        )

        labels["pi_brightness"].setText(
            format_number(pi_brightness, 3)
            if np.isfinite(pi_brightness)
            else "—"
        )
        labels["pi_brightness_delta"].setText(
            f"{pi_delta:+.3f}"
            if np.isfinite(pi_delta)
            else "—"
        )

    def set_frame(
        self,
        frame_number: int,
        force: bool = False,
    ) -> None:
        frame_number = max(
            0,
            min(
                int(frame_number),
                self.capture_data.frame_count - 1,
            ),
        )

        if (
            not force
            and frame_number == self.frame_number
        ):
            return

        frame = self.video_reader.read_frame(
            frame_number
        )

        if frame is None:
            return

        self.frame_number = frame_number

        self.display_frame(frame)
        self.update_frame_information()
        self.graph_panel.set_current_frame(
            self.frame_number
        )
        self.update_slider()

    def update_slider(self) -> None:
        self.slider_frame_label.setText(
            f"{self.frame_number + 1} / "
            f"{self.capture_data.frame_count}"
        )

        if self.frame_slider.value() == self.frame_number:
            return

        self.updating_slider = True

        try:
            self.frame_slider.setValue(
                self.frame_number
            )
        finally:
            self.updating_slider = False

    def on_slider_changed(
        self,
        value: int,
    ) -> None:
        if self.updating_slider:
            return

        self.set_frame(value)

    def keyPressEvent(self, event) -> None:
        key = event.key()

        if key == Qt.Key.Key_Right:
            self.set_frame(self.frame_number + 1)
            return

        if key == Qt.Key.Key_Left:
            self.set_frame(self.frame_number - 1)
            return

        if key in {
            Qt.Key.Key_Up,
            Qt.Key.Key_PageUp,
        }:
            self.set_frame(self.frame_number + 10)
            return

        if key in {
            Qt.Key.Key_Down,
            Qt.Key.Key_PageDown,
        }:
            self.set_frame(self.frame_number - 10)
            return

        if key == Qt.Key.Key_Home:
            self.set_frame(0)
            return

        if key == Qt.Key.Key_End:
            self.set_frame(
                self.capture_data.frame_count - 1
            )
            return

        if key in {
            Qt.Key.Key_X,
            Qt.Key.Key_Escape,
        }:
            self.close()
            return

        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

        frame = self.video_reader.read_frame(
            self.frame_number
        )

        if frame is not None:
            self.display_frame(frame)

    def closeEvent(self, event) -> None:
        self.video_reader.close()
        event.accept()
