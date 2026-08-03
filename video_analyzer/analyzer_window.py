"""Qt main window for the desktop video analyzer."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from common.candidate_config import CANDIDATE_CONFIG
from video_analyzer.candidate_replay import CandidateReplayResult
from video_analyzer.capture_data import CaptureData
from video_analyzer.graph_panel import GraphPanel
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
    ) -> None:
        super().__init__()

        self.capture_data = capture_data
        self.candidate_result = candidate_result
        self.frame_number = 0
        self.updating_slider = False

        self.video_reader = VideoReader(
            capture_data.video_path
        )

        self.setWindowTitle("Video Frame Analyzer")
        self.resize(1400, 1000)

        self.create_actions()
        self.create_ui()
        self.connect_controls()

        self.update_capture_information()
        self.set_frame(0, force=True)

    def create_actions(self) -> None:
        self.open_action = QAction("Open Capture...", self)
        self.open_action.setShortcut(
            QKeySequence.StandardKey.Open
        )
        self.open_action.triggered.connect(
            self.open_capture
        )

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut(
            QKeySequence.StandardKey.Quit
        )
        self.exit_action.triggered.connect(
            self.close
        )

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

    def create_information_group(
        self,
        title: str,
        fields: list[tuple[str, str]],
    ) -> tuple[QGroupBox, dict[str, QLabel]]:
        group = QGroupBox(title)
        layout = QGridLayout(group)

        layout.setContentsMargins(8, 6, 8, 6)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(2)

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

        group.setMaximumHeight(300)

        return group, value_labels

    def create_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        vertical_splitter = QSplitter(
            Qt.Orientation.Vertical
        )

        main_layout.addWidget(
            vertical_splitter,
            stretch=1,
        )

        upper_widget = QWidget()
        upper_layout = QVBoxLayout(upper_widget)

        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setSpacing(4)

        self.image_label = QLabel()
        self.image_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.image_label.setMinimumHeight(300)
        self.image_label.setStyleSheet(
            "QLabel { background-color: black; }"
        )

        upper_layout.addWidget(
            self.image_label,
            stretch=1,
        )

        information_layout = QHBoxLayout()
        information_layout.setContentsMargins(0, 0, 0, 0)
        information_layout.setSpacing(6)

        capture_fields = [
            ("video", "Video"),
            ("sidecar", "Sidecar"),
            ("capture_start", "Capture start UTC"),
            ("capture_duration", "Duration"),
            ("trigger", "Trigger"),
            ("trigger_threshold", "Trigger threshold"),
            ("trigger_frame", "Pi trigger frame"),
            ("replay_trigger_frame", "Replay trigger frame"),
            ("replay_result", "Replay result"),
            ("trigger_offset", "Trigger offset"),
            ("frame_count", "Frame count"),
        ]

        component_fields = [
            ("component_count", "Components"),
            ("valid_component_count", "Valid components"),
            ("max_component_area", "Maximum area"),
            ("max_component_height", "Maximum height"),
            ("max_component_width", "Maximum width"),
            ("max_component_aspect", "Maximum aspect"),
            ("longest_event", "Longest event"),
        ]

        frame_fields = [
            ("frame_number", "Frame"),
            ("timestamp_utc", "Timestamp UTC"),
            ("offset", "Offset"),
            ("sequence", "Sequence"),
            ("picture_type", "Encoded type"),
            ("key_frame", "Key frame"),
            ("pi_brightness", "Pi brightness"),
            ("replay_brightness", "Replay brightness"),
            ("brightness_difference", "Brightness difference"),
            ("pi_brightness_delta", "Pi brightness change"),
            ("replay_brightness_delta", "Replay brightness change"),
            ("delta_difference", "Change difference"),
        ]

        (
            capture_group,
            self.capture_value_labels,
        ) = self.create_information_group(
            "Capture information",
            capture_fields,
        )

        (
            component_group,
            self.component_value_labels,
        ) = self.create_information_group(
            "Component information",
            component_fields,
        )

        (
            frame_group,
            self.frame_value_labels,
        ) = self.create_information_group(
            "Current frame",
            frame_fields,
        )

        information_layout.addWidget(
            capture_group,
            stretch=1,
        )
        information_layout.addWidget(
            component_group,
            stretch=1,
        )
        information_layout.addWidget(
            frame_group,
            stretch=1,
        )

        upper_layout.addLayout(
            information_layout
        )

        self.graph_panel = GraphPanel(
            self.capture_data,
            self.candidate_result,
        )

        vertical_splitter.addWidget(
            upper_widget
        )
        vertical_splitter.addWidget(
            self.graph_panel
        )

        vertical_splitter.setStretchFactor(0, 3)
        vertical_splitter.setStretchFactor(1, 2)
        vertical_splitter.setSizes([560, 400])

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
        component_labels = self.component_value_labels
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

        capture_labels["trigger_threshold"].setText(
            format_number(
                CANDIDATE_CONFIG.
                candidate_brightness_delta_threshold,
                3,
            )
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

        component_labels["component_count"].setText(
            format_value(sidecar.get("component_count"))
        )
        component_labels["valid_component_count"].setText(
            format_value(sidecar.get("valid_component_count"))
        )
        component_labels["max_component_area"].setText(
            format_value(sidecar.get("max_component_area"))
        )
        component_labels["max_component_height"].setText(
            format_value(sidecar.get("max_component_height"))
        )
        component_labels["max_component_width"].setText(
            format_value(sidecar.get("max_component_width"))
        )
        component_labels["max_component_aspect"].setText(
            format_value(sidecar.get("max_component_aspect"))
        )
        component_labels["longest_event"].setText(
            format_number(
                sidecar.get("longest_event_ms"),
                1,
                " ms",
            )
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

        replay_brightness = (
            self.capture_data.replay_brightness[
                self.frame_number
            ]
        )
        replay_delta = (
            self.capture_data.replay_brightness_delta[
                self.frame_number
            ]
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
        labels["replay_brightness"].setText(
            f"{replay_brightness:.3f}"
        )
        labels["brightness_difference"].setText(
            f"{replay_brightness - pi_brightness:+.3f}"
            if np.isfinite(pi_brightness)
            else "—"
        )
        labels["pi_brightness_delta"].setText(
            f"{pi_delta:+.3f}"
            if np.isfinite(pi_delta)
            else "—"
        )
        labels["replay_brightness_delta"].setText(
            f"{replay_delta:+.3f}"
        )
        labels["delta_difference"].setText(
            f"{replay_delta - pi_delta:+.3f}"
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

    def open_capture(self) -> None:
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Open Capture",
            str(self.capture_data.video_path.parent),
            "Capture files (*.mp4 *.json);;MP4 files (*.mp4);;"
            "JSON files (*.json)",
        )

        if not filename:
            return

        QMessageBox.information(
            self,
            "Open Capture",
            "For this first version, close the analyzer and "
            "start it with the selected capture:\n\n"
            f"{filename}",
        )

    def closeEvent(self, event) -> None:
        self.video_reader.close()
        event.accept()
