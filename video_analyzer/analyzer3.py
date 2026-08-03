# ## Imports

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QImage, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QApplication,
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


# ## Resolve video and sidecar paths

def resolve_capture_paths(path: Path) -> tuple[Path, Path]:
    suffix = path.suffix.lower()

    if suffix == ".mp4":
        return path, path.with_suffix(".json")

    if suffix == ".json":
        return path.with_suffix(".mp4"), path

    if suffix == "":
        return path.with_suffix(".mp4"), path.with_suffix(".json")

    raise RuntimeError(
        f"Unsupported capture extension: {path.suffix}"
    )


# ## Read ffprobe frame metadata

def read_frame_info(filename: Path) -> list[dict[str, Any]]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_frames",
        "-show_entries",
        "frame=pict_type,key_frame,best_effort_timestamp_time",
        "-of",
        "json",
        str(filename),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        raise RuntimeError("ffprobe was not found in PATH.") from None
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or "ffprobe failed."
        raise RuntimeError(message) from error

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("ffprobe returned invalid JSON.") from error

    frames = data.get("frames", [])

    if not frames:
        raise RuntimeError("ffprobe found no video frames.")

    return frames


# ## Read JSON sidecar

def read_sidecar(filename: Path) -> dict[str, Any] | None:
    if not filename.is_file():
        return None

    try:
        with filename.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except OSError as error:
        raise RuntimeError(
            f"Unable to read sidecar: {error}"
        ) from error
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Invalid sidecar JSON: {error}"
        ) from error

    if not isinstance(data, dict):
        raise RuntimeError("Sidecar JSON must contain an object.")

    return data


# ## Analyze brightness across the clip

def analyze_clip(
    filename: Path,
) -> tuple[np.ndarray, np.ndarray]:
    capture = cv2.VideoCapture(str(filename))

    if not capture.isOpened():
        raise RuntimeError(
            f"OpenCV could not open: {filename}"
        )

    brightness_values: list[float] = []

    while True:
        success, frame = capture.read()

        if not success:
            break

        gray = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2GRAY,
        )

        brightness_values.append(
            float(gray.mean())
        )

    capture.release()

    if not brightness_values:
        raise RuntimeError("OpenCV decoded no frames.")

    brightness = np.asarray(
        brightness_values,
        dtype=np.float64,
    )

    brightness_delta = np.zeros_like(brightness)

    brightness_delta[1:] = (
        brightness[1:] - brightness[:-1]
    )

    return brightness, brightness_delta


# ## Format optional value

def format_value(
    value: Any,
    default: str = "—",
) -> str:
    if value is None:
        return default

    return str(value)


# ## Format optional number

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


# ## Analyzer main window

class AnalyzerWindow(QMainWindow):

    # ## Initialize analyzer window

    def __init__(
        self,
        video_path: Path,
        sidecar_path: Path,
        frame_info: list[dict[str, Any]],
        sidecar: dict[str, Any] | None,
        brightness: np.ndarray,
        brightness_delta: np.ndarray,
    ) -> None:
        super().__init__()

        self.video_path = video_path
        self.sidecar_path = sidecar_path
        self.frame_info = frame_info
        self.sidecar = sidecar
        self.brightness = brightness
        self.brightness_delta = brightness_delta

        self.frame_count = len(brightness)
        self.frame_number = 0
        self.updating_slider = False

        self.capture = cv2.VideoCapture(
            str(self.video_path)
        )

        if not self.capture.isOpened():
            raise RuntimeError(
                f"OpenCV could not open: {self.video_path}"
            )

        self.frame_records = self.build_frame_record_map()
        self.trigger_frame_index = self.get_trigger_frame_index()

        self.setWindowTitle("Standalone Analyzer")
        self.resize(1400, 1000)

        self.create_actions()
        self.create_ui()
        self.create_graphs()
        self.connect_controls()

        self.update_capture_information()
        self.set_frame(0, force=True)

    # ## Create menu and keyboard actions

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

    # ## Create main user interface

        # ## Create one compact information panel

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

        group.setMaximumHeight(225)

        return group, value_labels


    # ## Create main user interface

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
        information_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        information_layout.setSpacing(6)

        capture_fields = [
            ("video", "Video"),
            ("sidecar", "Sidecar"),
            ("capture_start", "Capture start UTC"),
            ("capture_duration", "Duration"),
            ("trigger", "Trigger"),
            ("trigger_frame", "Trigger frame"),
            ("trigger_offset", "Trigger offset"),
            ("frame_count", "Frame count"),
        ]

        component_fields = [
            ("component_count", "Components"),
            (
                "valid_component_count",
                "Valid components",
            ),
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
            ("brightness", "Brightness"),
            (
                "brightness_delta",
                "Brightness change",
            ),
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

        graph_widget = QWidget()
        self.graph_layout = QVBoxLayout(
            graph_widget
        )

        self.graph_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.graph_layout.setSpacing(3)

        vertical_splitter.addWidget(
            upper_widget
        )

        vertical_splitter.addWidget(
            graph_widget
        )

        vertical_splitter.setStretchFactor(
            0,
            3,
        )

        vertical_splitter.setStretchFactor(
            1,
            2,
        )

        vertical_splitter.setSizes(
            [560, 400]
        )

        controls_layout = QHBoxLayout()
        controls_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

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
            max(0, self.frame_count - 1),
        )

        self.frame_slider.setSingleStep(1)
        self.frame_slider.setPageStep(10)

        self.slider_frame_label = QLabel(
            f"0 / {self.frame_count - 1}"
        )

        self.slider_frame_label.setMinimumWidth(
            100
        )

        controls_layout.addWidget(
            self.first_button
        )

        controls_layout.addWidget(
            self.previous_button
        )

        controls_layout.addWidget(
            self.frame_slider,
            stretch=1,
        )

        controls_layout.addWidget(
            self.slider_frame_label
        )

        controls_layout.addWidget(
            self.next_button
        )

        controls_layout.addWidget(
            self.last_button
        )

        main_layout.addLayout(
            controls_layout
        )

    # ## Create brightness graphs

    def create_graphs(self) -> None:
        pg.setConfigOptions(
            antialias=True,
        )

        frame_numbers = np.arange(self.frame_count)

        self.brightness_graph = pg.PlotWidget()
        self.brightness_graph.setLabel(
            "left",
            "Absolute brightness",
        )
        self.brightness_graph.showGrid(
            x=True,
            y=True,
            alpha=0.3,
        )

        self.brightness_graph.plot(
            frame_numbers,
            self.brightness,
        )

        self.delta_graph = pg.PlotWidget()
        self.delta_graph.setLabel(
            "left",
            "Brightness change",
        )
        self.delta_graph.setLabel(
            "bottom",
            "Frame number",
        )
        self.delta_graph.showGrid(
            x=True,
            y=True,
            alpha=0.3,
        )

        self.delta_graph.plot(
            frame_numbers,
            self.brightness_delta,
        )

        self.delta_graph.setXLink(
            self.brightness_graph
        )

        self.current_frame_lines = [
            pg.InfiniteLine(
                pos=0,
                angle=90,
                movable=False,
                pen=pg.mkPen(
                    width=2,
                    style=Qt.PenStyle.DashLine,
                ),
            ),
            pg.InfiniteLine(
                pos=0,
                angle=90,
                movable=False,
                pen=pg.mkPen(
                    width=2,
                    style=Qt.PenStyle.DashLine,
                ),
            ),
        ]

        self.brightness_graph.addItem(
            self.current_frame_lines[0]
        )
        self.delta_graph.addItem(
            self.current_frame_lines[1]
        )

        self.trigger_lines: list[
            pg.InfiniteLine
        ] = []

        if self.trigger_frame_index is not None:
            for graph in [
                self.brightness_graph,
                self.delta_graph,
            ]:
                trigger_line = pg.InfiniteLine(
                    pos=self.trigger_frame_index,
                    angle=90,
                    movable=False,
                    pen=pg.mkPen(
                        width=2,
                        style=Qt.PenStyle.DotLine,
                    ),
                )

                graph.addItem(trigger_line)
                self.trigger_lines.append(
                    trigger_line
                )

        self.graph_layout.addWidget(
            self.brightness_graph
        )
        self.graph_layout.addWidget(
            self.delta_graph
        )

    # ## Connect controls and shortcuts

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
                self.frame_count - 1
            )
        )

        self.frame_slider.valueChanged.connect(
            self.on_slider_changed
        )

    # ## Build sidecar frame record map

    def build_frame_record_map(
        self,
    ) -> dict[int, dict[str, Any]]:
        records: dict[int, dict[str, Any]] = {}

        if self.sidecar is None:
            return records

        raw_records = self.sidecar.get(
            "frame_records",
            [],
        )

        if not isinstance(raw_records, list):
            return records

        for list_index, record in enumerate(raw_records):
            if not isinstance(record, dict):
                continue

            raw_frame_index = record.get(
                "frame_index",
                list_index,
            )

            try:
                frame_index = int(raw_frame_index)
            except (TypeError, ValueError):
                continue

            records[frame_index] = record

        return records

    # ## Get trigger frame index

    def get_trigger_frame_index(self) -> int | None:
        if self.sidecar is None:
            return None

        value = self.sidecar.get(
            "trigger_frame_index"
        )

        if value is None:
            frame_number = self.sidecar.get(
                "trigger_frame_number"
            )

            if frame_number is not None:
                try:
                    value = int(frame_number) - 1
                except (TypeError, ValueError):
                    value = None

        if value is None:
            return None

        try:
            frame_index = int(value)
        except (TypeError, ValueError):
            return None

        if 0 <= frame_index < self.frame_count:
            return frame_index

        return None

    # ## Read one decoded frame

    def read_frame(
        self,
        frame_number: int,
    ) -> np.ndarray | None:
        self.capture.set(
            cv2.CAP_PROP_POS_FRAMES,
            frame_number,
        )

        success, frame = self.capture.read()

        if not success:
            return None

        return frame

    # ## Convert OpenCV frame to Qt pixmap

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

    # ## Display the current frame

    def display_frame(
        self,
        frame: np.ndarray,
    ) -> None:
        pixmap = self.frame_to_pixmap(frame)

        available_size = self.image_label.size()

        scaled_pixmap = pixmap.scaled(
            available_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.image_label.setPixmap(
            scaled_pixmap
        )

    # ## Update capture information panel

        # ## Update capture and component information panels

    def update_capture_information(self) -> None:
        capture_labels = (
            self.capture_value_labels
        )

        component_labels = (
            self.component_value_labels
        )

        capture_labels["video"].setText(
            self.video_path.name
        )

        capture_labels["sidecar"].setText(
            self.sidecar_path.name
            if self.sidecar is not None
            else "Not found"
        )

        if self.sidecar is None:
            return

        capture_labels["capture_start"].setText(
            format_value(
                self.sidecar.get(
                    "capture_start_utc"
                )
            )
        )

        capture_labels[
            "capture_duration"
        ].setText(
            format_number(
                self.sidecar.get(
                    "capture_duration_ms"
                ),
                3,
                " ms",
            )
        )

        trigger_display = (
            self.sidecar.get(
                "trigger_display"
            )
            or self.sidecar.get(
                "trigger_type"
            )
            or self.sidecar.get(
                "trigger_reason"
            )
        )

        capture_labels["trigger"].setText(
            format_value(
                trigger_display
            )
        )

        trigger_frame_number = None

        if self.trigger_frame_index is not None:
            trigger_frame_number = (
                self.trigger_frame_index + 1
            )

        capture_labels[
            "trigger_frame"
        ].setText(
            format_value(
                trigger_frame_number
            )
        )

        capture_labels[
            "trigger_offset"
        ].setText(
            format_number(
                self.sidecar.get(
                    "trigger_offset_ms"
                ),
                3,
                " ms",
            )
        )

        capture_labels[
            "frame_count"
        ].setText(
            format_value(
                self.sidecar.get(
                    "frame_count"
                )
            )
        )

        component_labels[
            "component_count"
        ].setText(
            format_value(
                self.sidecar.get(
                    "component_count"
                )
            )
        )

        component_labels[
            "valid_component_count"
        ].setText(
            format_value(
                self.sidecar.get(
                    "valid_component_count"
                )
            )
        )

        component_labels[
            "max_component_area"
        ].setText(
            format_value(
                self.sidecar.get(
                    "max_component_area"
                )
            )
        )

        component_labels[
            "max_component_height"
        ].setText(
            format_value(
                self.sidecar.get(
                    "max_component_height"
                )
            )
        )

        component_labels[
            "max_component_width"
        ].setText(
            format_value(
                self.sidecar.get(
                    "max_component_width"
                )
            )
        )

        component_labels[
            "max_component_aspect"
        ].setText(
            format_value(
                self.sidecar.get(
                    "max_component_aspect"
                )
            )
        )

        component_labels[
            "longest_event"
        ].setText(
            format_number(
                self.sidecar.get(
                    "longest_event_ms"
                ),
                1,
                " ms",
            )
        )

    # ## Update current-frame information panel

    def update_frame_information(self) -> None:
        labels = self.frame_value_labels

        labels["frame_number"].setText(
            f"{self.frame_number + 1} / {self.frame_count}"
        )

        encoded_info: dict[str, Any] = {}

        if self.frame_number < len(self.frame_info):
            encoded_info = self.frame_info[
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

        record = self.frame_records.get(
            self.frame_number,
            {},
        )

        timestamp_utc = record.get(
            "timestamp_utc"
        )

        offset_ms = record.get(
            "offset_ms"
        )

        sequence_number = record.get(
            "sequence_number"
        )

        if offset_ms is None and ffprobe_time is not None:
            try:
                offset_ms = (
                    float(ffprobe_time) * 1000.0
                )
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

        labels["brightness"].setText(
            f"{self.brightness[self.frame_number]:.3f}"
        )

        labels["brightness_delta"].setText(
            f"{self.brightness_delta[self.frame_number]:+.3f}"
        )

    # ## Set current frame

    def set_frame(
        self,
        frame_number: int,
        force: bool = False,
    ) -> None:
        frame_number = max(
            0,
            min(
                int(frame_number),
                self.frame_count - 1,
            ),
        )

        if (
            not force
            and frame_number == self.frame_number
        ):
            return

        frame = self.read_frame(frame_number)

        if frame is None:
            return

        self.frame_number = frame_number

        self.display_frame(frame)
        self.update_frame_information()
        self.update_graph_cursors()
        self.update_slider()

    # ## Update graph cursor positions

    def update_graph_cursors(self) -> None:
        for line in self.current_frame_lines:
            line.setValue(self.frame_number)

    # ## Update slider position

    def update_slider(self) -> None:
        self.slider_frame_label.setText(
            f"{self.frame_number + 1} / "
            f"{self.frame_count}"
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

    # ## Handle slider movement

    def on_slider_changed(
        self,
        value: int,
    ) -> None:
        if self.updating_slider:
            return

        self.set_frame(value)

    # ## Handle keyboard input

    def keyPressEvent(self, event) -> None:
        key = event.key()

        if key == Qt.Key.Key_Right:
            self.set_frame(
                self.frame_number + 1
            )
            return

        if key == Qt.Key.Key_Left:
            self.set_frame(
                self.frame_number - 1
            )
            return

        if key in {
            Qt.Key.Key_Up,
            Qt.Key.Key_PageUp,
        }:
            self.set_frame(
                self.frame_number + 10
            )
            return

        if key in {
            Qt.Key.Key_Down,
            Qt.Key.Key_PageDown,
        }:
            self.set_frame(
                self.frame_number - 10
            )
            return

        if key == Qt.Key.Key_Home:
            self.set_frame(0)
            return

        if key == Qt.Key.Key_End:
            self.set_frame(
                self.frame_count - 1
            )
            return

        if key in {
            Qt.Key.Key_X,
            Qt.Key.Key_Escape,
        }:
            self.close()
            return

        super().keyPressEvent(event)

    # ## Resize image while preserving aspect ratio

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

        frame = self.read_frame(
            self.frame_number
        )

        if frame is not None:
            self.display_frame(frame)

    # ## Open a different capture

    def open_capture(self) -> None:
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Open Capture",
            str(self.video_path.parent),
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

    # ## Release video resources

        # ## Release video resources and terminate the application

    def closeEvent(self, event) -> None:
        if self.capture is not None:
            self.capture.release()
            self.capture = None

        event.accept()

        application = QApplication.instance()

        if application is not None:
            application.quit()


# ## Main program

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect a capture frame-by-frame with "
            "sidecar data and brightness graphs."
        )
    )

    parser.add_argument(
        "capture",
        type=Path,
        help=(
            "Capture basename, MP4 filename, "
            "or JSON sidecar filename"
        ),
    )

    arguments = parser.parse_args()

    try:
        video_path, sidecar_path = resolve_capture_paths(
            arguments.capture
        )

        if not video_path.is_file():
            raise RuntimeError(
                f"Video not found: {video_path}"
            )

        print(f"Video: {video_path}")

        if sidecar_path.is_file():
            print(f"Sidecar: {sidecar_path}")
        else:
            print(
                f"Sidecar not found: {sidecar_path}"
            )

        print("Reading ffprobe metadata...")
        frame_info = read_frame_info(video_path)

        print("Reading sidecar...")
        sidecar = read_sidecar(sidecar_path)

        print("Analyzing clip brightness...")
        brightness, brightness_delta = analyze_clip(
            video_path
        )

        print(
            f"Decoded frames: {len(brightness)}"
        )
        print(
            f"ffprobe frames: {len(frame_info)}"
        )

        application = QApplication(sys.argv)
        application.setQuitOnLastWindowClosed(
            True
        )

        window = AnalyzerWindow(
            video_path=video_path,
            sidecar_path=sidecar_path,
            frame_info=frame_info,
            sidecar=sidecar,
            brightness=brightness,
            brightness_delta=brightness_delta,
        )

        window.show()

        return application.exec()

    except RuntimeError as error:
        print(f"Error: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())