"""Vce Capture Editor for local and S3 Pi Camera captures.

The editor displays the production classifier's original FLASH/ANOMALY result
and initial confidence from the V8 sidecar, supports human verification/editing, and
displays the recorded geographic search bounding box. Legacy SolutionFilter
results are intentionally not computed or displayed.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from common.aws_auth import AwsAuthConfig, AwsAuthenticator, AwsAuthError
from common.capture_sidecar import (
    CLASSIFICATION_CODE_TO_NAME,
    CLASSIFICATION_NAME_TO_CODE,
    metadata_for_filter,
    normalize_sidecar,
)
from common.s3_capture_repository import S3CaptureRecord, S3CaptureRepository
from common.s3_store import S3Store, S3StoreError
from video_analyzer.capture_data import load_capture
from video_analyzer.candidate_replay import replay_candidate_finder
from video_analyzer.clip_editor_window import ClipEditorWindow, nested
from video_analyzer.graph_panel import GraphPanel
from video_analyzer.video_reader import VideoReader


VERIFIED_VALUES = ("No", "Yes")

CLASSIFICATION_VALUES = tuple(
    name
    for code, name in CLASSIFICATION_CODE_TO_NAME.items()
    if code != "PENDING"
)

TYPE_VALUES = ("UK", "CG", "IC", "LCC")

FILTER_VERIFIED = ("Any", "Yes", "No")
FILTER_CLASSIFICATION = ("Any",) + CLASSIFICATION_VALUES
FILTER_TYPE = ("Any",) + TYPE_VALUES
SORT_VALUES = ("Filename ascending", "Filename descending")

S3_BUCKET_NAME = "soloran-picam"
S3_AUTH_PROFILE = "picam-manager"


class CaptureEditorWindow(ClipEditorWindow):
    """UI-first Capture Editor.

    Local-storage editing remains functional through the existing ClipEditorWindow
    mechanisms. S3 is represented in the UI but deliberately left unwired in this pass.
    """

    def create_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main = QVBoxLayout(central)
        main.setContentsMargins(6, 6, 6, 6)
        main.setSpacing(4)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 7)
        grid.setColumnStretch(2, 3)
        grid.setRowStretch(0, 3)
        grid.setRowStretch(1, 2)

        # ------------------------------------------------------------------
        # LEFT COLUMN - Navigation / Filters / Clip list / full-width Open
        # ------------------------------------------------------------------
        browser = QGroupBox("Captures")
        browser.setMinimumWidth(255)
        browser.setMaximumWidth(330)
        bl = QVBoxLayout(browser)
        bl.setSpacing(5)

        nav = QGridLayout()
        nav.setHorizontalSpacing(4)
        nav.setVerticalSpacing(4)

        self.source_combo = QComboBox()
        self.source_combo.addItems(("Local Storage", "S3"))
        self.source_combo.setCurrentText(
            getattr(self, "source_mode", "Local Storage")
        )

        self.location_edit = QLineEdit(str(self.open_directory))
        self.location_edit.setReadOnly(True)

        self.parent_folder_button = QPushButton("Up")
        self.browse_location_button = QPushButton("Browse")

        self.source_label = QLabel("Source:")
        self.location_label = QLabel("Location:")

        nav.addWidget(self.source_label, 0, 0)
        nav.addWidget(self.source_combo, 0, 1, 1, 2)
        nav.addWidget(self.location_label, 1, 0)
        nav.addWidget(self.location_edit, 1, 1, 1, 2)
        nav.addWidget(self.parent_folder_button, 2, 1)
        nav.addWidget(self.browse_location_button, 2, 2)
        nav.setColumnStretch(1, 1)
        nav.setColumnStretch(2, 1)
        bl.addLayout(nav)

        filters = QGridLayout()
        filters.setHorizontalSpacing(4)
        filters.setVerticalSpacing(4)

        self.verified_filter_combo = QComboBox()
        self.verified_filter_combo.addItems(FILTER_VERIFIED)

        self.classification_filter_combo = QComboBox()
        self.classification_filter_combo.addItems(FILTER_CLASSIFICATION)

        self.type_filter_combo = QComboBox()
        self.type_filter_combo.addItems(FILTER_TYPE)

        self.site_filter_combo = QComboBox()
        self.site_filter_combo.addItem("Any")

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(SORT_VALUES)

        saved_filters = getattr(
            self,
            "_browser_filter_settings",
            {
                "verified": "No",
                "classification": "Any",
                "type": "Any",
                "site": "Any",
                "sort": "Filename ascending",
            },
        )

        self.verified_filter_combo.setCurrentText(
            saved_filters.get("verified", "No")
        )
        self.classification_filter_combo.setCurrentText(
            saved_filters.get("classification", "Any")
        )
        self.type_filter_combo.setCurrentText(
            saved_filters.get("type", "Any")
        )
        self.sort_combo.setCurrentText(
            saved_filters.get("sort", "Filename ascending")
        )

        filter_rows = (
            ("Verified:", self.verified_filter_combo),
            ("Classification:", self.classification_filter_combo),
            ("Type:", self.type_filter_combo),
            ("Site:", self.site_filter_combo),
            ("Sort:", self.sort_combo),
        )
        for row, (name, widget) in enumerate(filter_rows):
            filters.addWidget(QLabel(name), row, 0)
            filters.addWidget(widget, row, 1)
        filters.setColumnStretch(1, 1)
        bl.addLayout(filters)

        self.apply_filters_button = QPushButton("Apply Filters")
        self.apply_filters_button.setEnabled(False)
        bl.addWidget(self.apply_filters_button)

        self.directory_label = QLabel()
        self.directory_label.setWordWrap(True)
        self.directory_label.setStyleSheet("QLabel { color: #555; font-size: 10px; }")
        bl.addWidget(self.directory_label)

        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        bl.addWidget(self.file_list, 1)

        self.open_browser_button = QPushButton("Open")
        bl.addWidget(self.open_browser_button)

        grid.addWidget(browser, 0, 0, 2, 1)

        # ------------------------------------------------------------------
        # MIDDLE COLUMN - intentionally unchanged from current Vce editor
        # ------------------------------------------------------------------
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumHeight(240)
        self.image_label.setStyleSheet("QLabel { background-color: black; }")
        grid.addWidget(self.image_label, 0, 1)

        if self.capture_data is not None:
            self.graph_panel = GraphPanel(
                self.capture_data,
                self.candidate_result,
                self.candidate_config,
            )
            grid.addWidget(self.graph_panel, 1, 1)
        else:
            self.graph_panel = None
            empty = QLabel("Select a clip to load")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(empty, 1, 1)

        # ------------------------------------------------------------------
        # RIGHT COLUMN
        # ------------------------------------------------------------------
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(3)

        # Keep Analyzer-compatible hidden/source value labels so the existing
        # capture-information population code still works.
        capture_fields = [
            ("video", "Video"),
            ("site_name", "Site"),
            ("capture_start", "Capture start UTC"),
            ("capture_duration", "Duration"),
            ("capture_sensitivity", "Capture Sensitivity"),
            ("trigger", "Trigger"),
            ("trigger_reason", "Trigger reason"),
            ("trigger_frame", "Pi trigger frame"),
            ("replay_trigger_frame", "Replay trigger frame"),
            ("trigger_offset", "Trigger offset"),
            ("mean_frame_gap", "Mean frame gap"),
            ("max_frame_gap", "Max frame gap"),
        ]
        self.capture_value_labels = {
            key: QLabel("—") for key, _label in capture_fields
        }

        capture_group = QGroupBox("Capture information")
        cgl = QGridLayout(capture_group)
        cgl.setHorizontalSpacing(5)
        cgl.setVerticalSpacing(2)

        # Direct fields use the Analyzer-populated labels.
        direct_rows = [
            ("Video", self.capture_value_labels["video"]),
            ("Capture start UTC", self.capture_value_labels["capture_start"]),
            ("Duration", self.capture_value_labels["capture_duration"]),
            ("Capture Sensitivity", self.capture_value_labels["capture_sensitivity"]),
            ("Trigger", self.capture_value_labels["trigger"]),
            ("Trigger reason", self.capture_value_labels["trigger_reason"]),
        ]
        row = 0
        for name, value_label in direct_rows:
            cgl.addWidget(QLabel(name + ":"), row, 0)
            cgl.addWidget(value_label, row, 1)
            row += 1

        self.trigger_frames_label = QLabel("—")
        self.frame_gaps_label = QLabel("—")

        cgl.addWidget(QLabel("Pi / Replay trigger frame:"), row, 0)
        cgl.addWidget(self.trigger_frames_label, row, 1)
        row += 1

        cgl.addWidget(QLabel("Trigger offset:"), row, 0)
        cgl.addWidget(self.capture_value_labels["trigger_offset"], row, 1)
        row += 1

        cgl.addWidget(QLabel("Frame gaps ms mean / max:"), row, 0)
        cgl.addWidget(self.frame_gaps_label, row, 1)
        row += 1

        self.initial_classification_label = QLabel("—")
        self.classification_confidence_label = QLabel("—")

        cgl.addWidget(QLabel("Initial classification:"), row, 0)
        cgl.addWidget(self.initial_classification_label, row, 1)
        row += 1

        cgl.addWidget(QLabel("Initial confidence:"), row, 0)
        cgl.addWidget(self.classification_confidence_label, row, 1)
        cgl.setColumnStretch(1, 1)

        frame_fields = [
            ("frame_number", "Frame"),
            ("timestamp_utc", "Timestamp UTC"),
            ("offset", "Offset"),
            ("brightness_change", "Brightness, change"),
        ]
        frame_group, self.frame_value_labels = self.create_information_group(
            "Current frame",
            frame_fields,
        )

        rl.addWidget(capture_group)
        rl.addWidget(frame_group)

        # Spatial search bounds recorded by the capture pipeline.  Capture
        # Editor displays these values directly from the sidecar; it does not
        # recompute them.
        search_group = QGroupBox("Search bounding box")
        sgl = QGridLayout(search_group)
        sgl.setHorizontalSpacing(5)
        sgl.setVerticalSpacing(2)

        self.search_range_label = QLabel("—")
        self.search_latitude_label = QLabel("—")
        self.search_longitude_label = QLabel("—")

        sgl.addWidget(QLabel("Range miles:"), 0, 0)
        sgl.addWidget(self.search_range_label, 0, 1)
        sgl.addWidget(QLabel("Latitude:"), 1, 0)
        sgl.addWidget(self.search_latitude_label, 1, 1)
        sgl.addWidget(QLabel("Longitude:"), 2, 0)
        sgl.addWidget(self.search_longitude_label, 2, 1)
        sgl.setColumnStretch(1, 1)

        rl.addWidget(search_group)

        # Editable Clip Metadata
        edit = QGroupBox("Clip metadata")
        el = QGridLayout(edit)
        el.setHorizontalSpacing(5)
        el.setVerticalSpacing(2)

        self.site_edit = QLineEdit()
        self.latitude_spin = self.spin(-90, 90, 7)
        self.longitude_spin = self.spin(-180, 180, 7)
        self.bearing_spin = self.spin(0, 359.999, 3)
        self.hfov_spin = self.spin(1, 120, 3)

        # Keep VFOV in memory for compatibility with current sidecars/save code,
        # but it is deliberately not presented in the UI.
        self.vfov_spin = self.spin(1, 120, 3)
        self.vfov_spin.hide()

        self.verified_combo = QComboBox()
        self.verified_combo.addItems(VERIFIED_VALUES)

        self.classification_combo = QComboBox()
        self.classification_combo.addItems(CLASSIFICATION_VALUES)

        self.type_combo = QComboBox()
        self.type_combo.addItems(TYPE_VALUES)

        self.description_edit = QTextEdit()
        self.description_edit.setAcceptRichText(False)
        self.description_edit.setMinimumHeight(150)
        self.description_edit.setMaximumHeight(240)

        # Site
        el.addWidget(QLabel("Site name:"), 0, 0)
        el.addWidget(self.site_edit, 0, 1, 1, 3)

        # Latitude / Longitude on separate rows to use vertical space cleanly.
        el.addWidget(QLabel("Latitude:"), 1, 0)
        el.addWidget(self.latitude_spin, 1, 1, 1, 3)

        el.addWidget(QLabel("Longitude:"), 2, 0)
        el.addWidget(self.longitude_spin, 2, 1, 1, 3)

        # Bearing / HFOV still share one row.
        el.addWidget(QLabel("Bearing:"), 3, 0)
        el.addWidget(self.bearing_spin, 3, 1)
        el.addWidget(QLabel("HFOV:"), 3, 2)
        el.addWidget(self.hfov_spin, 3, 3)

        el.addWidget(QLabel("Verified:"), 4, 0)
        el.addWidget(self.verified_combo, 4, 1, 1, 3)

        el.addWidget(QLabel("Classification:"), 5, 0)
        el.addWidget(self.classification_combo, 5, 1, 1, 3)

        el.addWidget(QLabel("Type:"), 6, 0)
        el.addWidget(self.type_combo, 6, 1, 1, 3)

        el.addWidget(
            QLabel("Description:"),
            7,
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        el.addWidget(self.description_edit, 7, 1, 1, 3)

        buttons = QHBoxLayout()
        self.restore_button = QPushButton("Restore")
        self.save_button = QPushButton("Save Changes")
        self.save_button.setDefault(True)
        self.save_button.setAutoDefault(True)
        buttons.addWidget(self.restore_button)
        buttons.addWidget(self.save_button)
        el.addLayout(buttons, 8, 0, 1, 4)

        el.setColumnStretch(1, 1)
        el.setColumnStretch(3, 1)

        rl.addWidget(edit, 1)

        # Keep the three columns on the same bottom baseline.  Spare vertical
        # space is consumed by the Clip Metadata group (primarily Description),
        # rather than by empty gaps between groups.
        grid.addWidget(right, 0, 2, 2, 1)

        self._applied_filters = self._current_filter_settings()
        self.refresh_file_browser()
        main.addLayout(grid, 1)

        # Keep existing keyboard workflow hint.
        shortcut_label = QLabel(
            "Ctrl+Left/Right: Previous/Next clip    "
            "Ctrl+Enter: Save + Next clip    "
            "Ctrl+I: IC    Ctrl+G: CG    Ctrl+J: View JSON    "
            "Left/Right: Previous/Next frame    "
            "Enter: Save    Esc: Restore"
        )
        shortcut_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shortcut_label.setStyleSheet("QLabel { color: #555; font-size: 10px; }")
        main.addWidget(shortcut_label)

        controls = QHBoxLayout()
        self.first_button = QPushButton("|<")
        self.previous_button = QPushButton("<")
        self.next_button = QPushButton(">")
        self.last_button = QPushButton(">|")

        frame_count = self.capture_data.frame_count if self.capture_data is not None else 0
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(0, max(0, frame_count - 1))
        self.frame_slider.setSingleStep(1)
        self.frame_slider.setPageStep(10)

        self.slider_frame_label = QLabel(f"0 / {max(0, frame_count - 1)}")
        self.slider_frame_label.setMinimumWidth(100)

        controls.addWidget(self.first_button)
        controls.addWidget(self.previous_button)
        controls.addWidget(self.frame_slider, 1)
        controls.addWidget(self.slider_frame_label)
        controls.addWidget(self.next_button)
        controls.addWidget(self.last_button)
        main.addLayout(controls)

        self._set_source_ui()

    def connect_controls(self):
        # Navigation
        self.source_combo.currentTextChanged.connect(self.on_source_changed)
        self.parent_folder_button.clicked.connect(self.browse_parent_directory)
        self.browse_location_button.clicked.connect(self.browse_local_directory)
        self.open_browser_button.clicked.connect(self.open_selected_browser_item)
        self.file_list.itemDoubleClicked.connect(
            lambda _item: self.open_selected_browser_item()
        )

        # Filter changes are staged. The file list changes only when Apply
        # Filters is pressed.
        self.verified_filter_combo.currentTextChanged.connect(self.on_filter_changed)
        self.classification_filter_combo.currentTextChanged.connect(self.on_filter_changed)
        self.type_filter_combo.currentTextChanged.connect(self.on_filter_changed)
        self.site_filter_combo.currentTextChanged.connect(self.on_filter_changed)
        self.sort_combo.currentTextChanged.connect(self.on_filter_changed)
        self.apply_filters_button.clicked.connect(self.apply_filters)

        # Existing frame controls
        self.first_button.clicked.connect(lambda: self.set_frame(0))
        self.previous_button.clicked.connect(
            lambda: self.set_frame(self.frame_number - 1)
        )
        self.next_button.clicked.connect(
            lambda: self.set_frame(self.frame_number + 1)
        )
        self.last_button.clicked.connect(
            lambda: self.set_frame(
                self.capture_data.frame_count - 1
                if self.capture_data is not None
                else 0
            )
        )
        self.frame_slider.valueChanged.connect(self.on_slider_changed)

        # Existing metadata workflow
        self.restore_button.clicked.connect(self.restore_loaded_values)
        self.save_button.clicked.connect(self.save_changes)

        # Classification -> Type validation rule
        self.classification_combo.currentTextChanged.connect(
            self.on_classification_changed
        )
        self.type_combo.currentTextChanged.connect(
            self.on_type_changed
        )

        # Metadata keyboard navigation
        self._editor_fields = (
            self.site_edit,
            self.latitude_spin,
            self.longitude_spin,
            self.bearing_spin,
            self.hfov_spin,
            self.verified_combo,
            self.classification_combo,
            self.type_combo,
            self.description_edit,
        )
        for field in self._editor_fields:
            field.installEventFilter(self)
            for child in field.findChildren(QWidget):
                child.installEventFilter(self)

        self.setTabOrder(self.site_edit, self.latitude_spin)
        self.setTabOrder(self.latitude_spin, self.longitude_spin)
        self.setTabOrder(self.longitude_spin, self.bearing_spin)
        self.setTabOrder(self.bearing_spin, self.hfov_spin)
        self.setTabOrder(self.hfov_spin, self.verified_combo)
        self.setTabOrder(self.verified_combo, self.classification_combo)
        self.setTabOrder(self.classification_combo, self.type_combo)
        self.setTabOrder(self.type_combo, self.description_edit)

    # ------------------------------------------------------------------
    # Source UI
    # ------------------------------------------------------------------
    def _set_source_ui(self):
        # source_mode is authoritative.  An S3 clip is downloaded to a local
        # temporary cache for decoding, but that cache must never make the UI
        # look like Local Storage.
        if self.source_combo.currentText() != self.source_mode:
            self.source_combo.blockSignals(True)
            try:
                self.source_combo.setCurrentText(self.source_mode)
            finally:
                self.source_combo.blockSignals(False)

        local = self.source_mode == "Local Storage"

        # Location/Up/Browse are local-storage navigation controls. S3 does not
        # show a meaningless path field in this UI pass.
        self.location_label.setVisible(local)
        self.location_edit.setVisible(local)
        self.parent_folder_button.setVisible(local)
        self.browse_location_button.setVisible(local)

        if local:
            self.location_edit.setText(str(self.open_directory))

    def _current_filter_settings(self):
        return {
            "verified": self.verified_filter_combo.currentText(),
            "classification": self.classification_filter_combo.currentText(),
            "type": self.type_filter_combo.currentText(),
            "site": self.site_filter_combo.currentText(),
            "sort": self.sort_combo.currentText(),
        }

    def on_filter_changed(self, _value=None):
        if not hasattr(self, "_applied_filters"):
            return
        self.apply_filters_button.setEnabled(
            self._current_filter_settings() != self._applied_filters
        )

    def apply_filters(self):
        self._applied_filters = self._current_filter_settings()
        self._browser_filter_settings = dict(self._applied_filters)
        self.refresh_file_browser()
        self.apply_filters_button.setEnabled(False)

    def browse_parent_directory(self):
        if self.source_mode != "Local Storage":
            return

        parent = self.open_directory.parent

        if parent == self.open_directory:
            return

        if not self.confirm_abandon_changes():
            return

        self.open_directory = parent
        self._local_open_directory = parent
        self._invalidate_local_browser_cache()
        self.refresh_file_browser()

    def browse_local_directory(self):
        if self.source_combo.currentText() != "Local Storage":
            return

        selected = QFileDialog.getExistingDirectory(
            self,
            "Select capture folder",
            str(self.open_directory),
        )
        if not selected:
            return
        if not self.confirm_abandon_changes():
            return

        self.open_directory = Path(selected)
        self._local_open_directory = self.open_directory
        self._invalidate_local_browser_cache()
        self.refresh_file_browser()

    # ------------------------------------------------------------------
    # Compact Capture Information
    # ------------------------------------------------------------------
    def update_capture_information(self):
        if self.capture_data is None or not hasattr(self, "capture_value_labels"):
            return

        # ClipEditorWindow fills the Analyzer-compatible source labels and
        # Capture Sensitivity.
        super().update_capture_information()

        pi_frame = self.capture_value_labels["trigger_frame"].text()
        replay_frame = self.capture_value_labels["replay_trigger_frame"].text()
        self.trigger_frames_label.setText(f"{pi_frame} / {replay_frame}")

        mean_gap = self.capture_value_labels["mean_frame_gap"].text()
        max_gap = self.capture_value_labels["max_frame_gap"].text()

        # Existing implementation does not expose the frame-pair text separately,
        # so the UI pass combines the two existing values now. The exact
        # "(259-260)" suffix can be wired when the underlying value is available.
        self.frame_gaps_label.setText(f"{mean_gap} / {max_gap}")

        sidecar = (
            self.capture_data.sidecar
            if isinstance(self.capture_data.sidecar, dict)
            else {}
        )
        capture = sidecar.get("capture")
        if not isinstance(capture, dict):
            capture = {}

        classification_code = str(
            capture.get("initial_classification", "") or ""
        ).strip().upper()
        # V8 model provenance. For transitional historical V8 files without
        # initial_classification, show the current classification rather than a
        # misleading blank value. New PSF output always stores the initial value.
        if not classification_code:
            classification_code = str(
                capture.get("classification", "") or ""
            ).strip().upper()
        self.initial_classification_label.setText(
            CLASSIFICATION_CODE_TO_NAME.get(
                classification_code,
                classification_code or "—",
            )
        )

        initial_confidence = capture.get("initial_confidence")
        if initial_confidence is None:
            self.classification_confidence_label.setText("—")
        else:
            try:
                self.classification_confidence_label.setText(
                    f"{float(initial_confidence) * 100.0:.1f}%"
                )
            except (TypeError, ValueError):
                self.classification_confidence_label.setText("—")

        self._update_search_bounding_box()

    def _update_search_bounding_box(self):
        if self.capture_data is None:
            return

        sidecar = (
            self.capture_data.sidecar
            if isinstance(self.capture_data.sidecar, dict)
            else {}
        )
        camera = sidecar.get("camera")
        if not isinstance(camera, dict):
            camera = {}

        box = camera.get("search_bounding_box")
        if not isinstance(box, dict):
            box = sidecar.get("search_bounding_box")
        if not isinstance(box, dict):
            box = {}

        def pair_text(name, digits):
            values = box.get(name)
            if not isinstance(values, (list, tuple)) or len(values) != 2:
                return "—"
            try:
                low = float(values[0])
                high = float(values[1])
            except (TypeError, ValueError):
                return "—"
            return f"{low:.{digits}f} – {high:.{digits}f}"

        self.search_range_label.setText(pair_text("range", 1))
        self.search_latitude_label.setText(pair_text("lat", 6))
        self.search_longitude_label.setText(pair_text("lon", 6))

    # ------------------------------------------------------------------
    # New metadata model
    # ------------------------------------------------------------------
    def metadata(self):
        sidecar = (
            self.capture_data.sidecar
            if self.capture_data is not None
            and isinstance(self.capture_data.sidecar, dict)
            else {}
        )

        camera = sidecar.get("camera")
        if not isinstance(camera, dict):
            camera = {}

        capture = sidecar.get("capture")
        if not isinstance(capture, dict):
            capture = {}

        verified = capture.get("verified", False)
        if not isinstance(verified, bool):
            verified = bool(verified)

        raw_classification = str(
            capture.get("classification", "") or ""
        ).strip().upper()

        # PENDING exists only between capture creation and the PSF pass. If a
        # PENDING sidecar is opened manually, present FLASH as the adjudication
        # default without changing the stored sidecar until Save.
        if raw_classification == "PENDING":
            classification_code = "FLASH"
        elif raw_classification in CLASSIFICATION_CODE_TO_NAME:
            classification_code = raw_classification
        else:
            classification_code = "ANOMALY"

        lightning_type = str(
            capture.get("type", "UK") or "UK"
        ).strip().upper()

        if lightning_type not in TYPE_VALUES:
            lightning_type = "UK"

        if classification_code != "FLASH":
            lightning_type = "UK"

        return dict(
            site_name=str(camera.get("site_name", "") or ""),
            latitude=float(camera.get("latitude_degrees", 0) or 0),
            longitude=float(camera.get("longitude_degrees", 0) or 0),
            bearing=float(camera.get("bearing_degrees", 0) or 0),
            hfov=float(camera.get("hfov_degrees", 1) or 1),
            vfov=float(camera.get("vfov_degrees", 1) or 1),
            verified=verified,
            classification=CLASSIFICATION_CODE_TO_NAME[classification_code],
            type=lightning_type,
            description=str(capture.get("description", "") or ""),
        )

    def current_values(self):
        return dict(
            site_name=self.site_edit.text().strip(),
            latitude=self.latitude_spin.value(),
            longitude=self.longitude_spin.value(),
            bearing=self.bearing_spin.value(),
            hfov=self.hfov_spin.value(),
            vfov=self.vfov_spin.value(),
            verified=self.verified_combo.currentText() == "Yes",
            classification=self.classification_combo.currentText(),
            type=self.type_combo.currentText(),
            description=self.description_edit.toPlainText(),
        )

    def restore_loaded_values(self):
        if not self.loaded_metadata:
            return

        v = self.loaded_metadata
        self.site_edit.setText(v["site_name"])
        self.latitude_spin.setValue(v["latitude"])
        self.longitude_spin.setValue(v["longitude"])
        self.bearing_spin.setValue(v["bearing"])
        self.hfov_spin.setValue(v["hfov"])
        self.vfov_spin.setValue(v["vfov"])
        self.verified_combo.setCurrentText("Yes" if v["verified"] else "No")
        self.classification_combo.setCurrentText(v["classification"])
        self.type_combo.setCurrentText(v["type"])
        self.description_edit.setPlainText(v["description"])
        self.on_classification_changed(self.classification_combo.currentText())

    def on_classification_changed(self, classification):
        is_true_flash = (
            CLASSIFICATION_NAME_TO_CODE.get(classification) == "FLASH"
        )
        self.type_combo.setEnabled(is_true_flash)
        if not is_true_flash:
            self.type_combo.setCurrentText("UK")

    def on_type_changed(self, lightning_type):
        if lightning_type in ("CG", "IC", "LCC"):
            self.verified_combo.setCurrentText("Yes")

    def _handle_type_shortcut(self, key, modifiers):
        if not (
            modifiers
            & Qt.KeyboardModifier.ControlModifier
        ):
            return False

        if key == Qt.Key.Key_I:
            self.type_combo.setCurrentText("IC")
            return True

        if key == Qt.Key.Key_G:
            self.type_combo.setCurrentText("CG")
            return True

        if key == Qt.Key.Key_J:
            self.show_json_sidecar()
            return True

        return False

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.Type.KeyPress
            and self._handle_type_shortcut(
                event.key(),
                event.modifiers(),
            )
        ):
            return True

        return super().eventFilter(
            obj,
            event,
        )

    def keyPressEvent(self, event):
        if self._handle_type_shortcut(
            event.key(),
            event.modifiers(),
        ):
            return

        super().keyPressEvent(
            event
        )

    def show_json_sidecar(self):
        if (
            self.capture_data is None
            or not isinstance(
                self.capture_data.sidecar,
                dict,
            )
        ):
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(
            f"JSON Sidecar — {self.capture_data.sidecar_path.name}"
        )
        dialog.resize(
            900,
            700,
        )

        layout = QVBoxLayout(dialog)

        json_view = QPlainTextEdit()
        json_view.setReadOnly(True)
        json_view.setPlainText(
            json.dumps(
                self.capture_data.sidecar,
                indent=4,
            )
        )
        json_view.moveCursor(
            json_view.textCursor().MoveOperation.Start
        )

        close_button = QPushButton("Close")
        close_button.clicked.connect(
            dialog.close
        )

        layout.addWidget(
            json_view,
            1,
        )
        layout.addWidget(
            close_button,
        )

        dialog.exec()

    def set_editor_enabled(self, enabled):
        widgets = (
            self.site_edit,
            self.latitude_spin,
            self.longitude_spin,
            self.bearing_spin,
            self.hfov_spin,
            self.verified_combo,
            self.classification_combo,
            self.type_combo,
            self.description_edit,
            self.restore_button,
            self.save_button,
        )
        for w in widgets:
            w.setEnabled(enabled)

        if enabled:
            self.on_classification_changed(self.classification_combo.currentText())

    # ------------------------------------------------------------------
    # Local browser + UI filters
    # ------------------------------------------------------------------
    def _invalidate_local_browser_cache(self):
        self._local_browser_directory = None
        self._local_browser_entries = []
        self._local_browser_sites = set()

    def _build_local_browser_cache(self):
        directory = Path(self.open_directory)

        if self._local_browser_directory == directory:
            return

        try:
            entries = list(directory.iterdir())
        except OSError as exc:
            raise RuntimeError(str(exc)) from exc

        browser_entries = []
        sites = set()

        for path in entries:
            if path.is_dir():
                browser_entries.append((path, None))
                continue

            if path.suffix.lower() != ".mp4":
                continue

            meta = self._read_sidecar_metadata_for_filter(path)

            if meta and meta["site"]:
                sites.add(meta["site"])

            browser_entries.append((path, meta))

        self._local_browser_directory = directory
        self._local_browser_entries = browser_entries
        self._local_browser_sites = sites

    def _update_cached_local_metadata(
        self,
        video_path: Path,
        sidecar: dict,
    ):
        if self._local_browser_directory != Path(self.open_directory):
            return

        meta = metadata_for_filter(sidecar)
        browser_meta = {
            "verified": meta["verified"],
            "classification": CLASSIFICATION_CODE_TO_NAME.get(
                meta["classification"],
                "",
            ),
            "type": meta["type"],
            "site": meta["site"],
        }

        for index, (path, _old_meta) in enumerate(self._local_browser_entries):
            if path == video_path:
                self._local_browser_entries[index] = (
                    path,
                    browser_meta,
                )
                break

        self._local_browser_sites = {
            item_meta["site"]
            for path, item_meta in self._local_browser_entries
            if (
                not path.is_dir()
                and item_meta is not None
                and item_meta["site"]
            )
        }

    def refresh_file_browser(self):
        if not hasattr(self, "file_list"):
            return

        if self.source_combo.currentText() == "S3":
            self._refresh_s3_browser()
            return

        self.location_edit.setText(str(self.open_directory))
        self.directory_label.setText(str(self.open_directory))
        self.file_list.clear()

        try:
            self._build_local_browser_cache()
        except RuntimeError as exc:
            QMessageBox.warning(
                self,
                "Unable to read folder",
                str(exc),
            )
            return

        clips = self._local_browser_entries
        self._refresh_site_filter(
            self._local_browser_sites
        )

        applied = getattr(
            self,
            "_applied_filters",
            self._current_filter_settings(),
        )
        verified_filter = applied["verified"]
        classification_filter = applied["classification"]
        type_filter = applied["type"]
        site_filter = applied["site"]

        filtered = []
        for p, meta in clips:
            if p.is_dir():
                filtered.append((p, meta))
                continue

            if meta is None:
                # Keep clips with missing/unreadable sidecars visible when all
                # filters are Any; otherwise they cannot satisfy metadata filters.
                if any(
                    value != "Any"
                    for value in (
                        verified_filter,
                        classification_filter,
                        type_filter,
                        site_filter,
                    )
                ):
                    continue
                filtered.append((p, meta))
                continue

            if verified_filter != "Any":
                expected = verified_filter == "Yes"
                if meta["verified"] != expected:
                    continue

            if (
                classification_filter != "Any"
                and meta["classification"] != classification_filter
            ):
                continue

            if type_filter != "Any" and meta["type"] != type_filter:
                continue

            if site_filter != "Any" and meta["site"] != site_filter:
                continue

            filtered.append((p, meta))

        reverse = applied["sort"] == "Filename descending"
        filtered.sort(
            key=lambda item: (not item[0].is_dir(), item[0].name.lower()),
            reverse=reverse,
        )

        current = None
        if self.capture_data is not None:
            try:
                current = self.capture_data.video_path.resolve()
            except OSError:
                pass

        selected = None
        for p, _meta in filtered:
            item = QListWidgetItem(
                f"[Folder] {p.name}" if p.is_dir() else p.name
            )
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.file_list.addItem(item)

            if current is not None:
                try:
                    if p.resolve() == current:
                        selected = item
                except OSError:
                    pass

        if selected is not None:
            self.file_list.setCurrentItem(selected)
            self.file_list.scrollToItem(selected)

    def _refresh_site_filter(self, sites):
        previous = self.site_filter_combo.currentText()
        values = ["Any"] + sorted(sites, key=str.lower)

        current_values = [
            self.site_filter_combo.itemText(i)
            for i in range(self.site_filter_combo.count())
        ]
        if current_values == values:
            return

        self.site_filter_combo.blockSignals(True)
        try:
            self.site_filter_combo.clear()
            self.site_filter_combo.addItems(values)
            desired = getattr(
                self,
                "_browser_filter_settings",
                {},
            ).get("site", previous)

            if desired in values:
                self.site_filter_combo.setCurrentText(desired)
            elif previous in values:
                self.site_filter_combo.setCurrentText(previous)
        finally:
            self.site_filter_combo.blockSignals(False)

        if hasattr(self, "_applied_filters"):
            self.on_filter_changed()

    def _read_sidecar_metadata_for_filter(self, video_path: Path):
        sidecar_path = video_path.with_suffix(".json")
        if not sidecar_path.exists():
            return None

        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8-sig"))
            meta = metadata_for_filter(sidecar)
        except (OSError, json.JSONDecodeError, TypeError):
            return None

        return {
            "verified": meta["verified"],
            "classification": CLASSIFICATION_CODE_TO_NAME.get(
                meta["classification"], ""
            ),
            "type": meta["type"],
            "site": meta["site"],
        }

    # ------------------------------------------------------------------
    # Backend implementation
    # ------------------------------------------------------------------
    def __init__(
        self,
        capture_data,
        candidate_result,
        solution_result,
        open_directory=None,
    ):
        self.source_mode = "Local Storage"
        self._source_change_in_progress = False

        self._browser_filter_settings = {
            "verified": "No",
            "classification": "Any",
            "type": "Any",
            "site": "Any",
            "sort": "Filename ascending",
        }

        self._s3_store = None
        self._s3_repository = None
        self._s3_records = []
        self._current_s3_record = None

        # Local filtering currently requires reading each JSON sidecar. Cache
        # that metadata once per folder so opening/rebuilding one capture does
        # not reread thousands of sidecars.
        self._local_browser_directory = None
        self._local_browser_entries = []
        self._local_browser_sites = set()

        # S3 clips are downloaded into a temporary directory for decoding.
        # Keep that cache path from replacing the user's actual local folder.
        self._local_open_directory = (
            Path(open_directory)
            if open_directory is not None
            else None
        )

        super().__init__(
            capture_data,
            candidate_result,
            None,
            open_directory=open_directory,
        )

        # A capture supplied at startup is local.
        if self._local_open_directory is None:
            self._local_open_directory = Path(self.open_directory)

        if capture_data is not None:
            self._upgrade_loaded_sidecar(persist_local=True)

    def _ensure_s3_repository(self):
        if self._s3_repository is not None:
            return self._s3_repository

        auth = AwsAuthenticator(
            AwsAuthConfig(profile_name=S3_AUTH_PROFILE)
        )
        self._s3_store = S3Store(
            S3_BUCKET_NAME,
            authenticator=auth,
        )
        self._s3_repository = S3CaptureRepository(self._s3_store)
        return self._s3_repository

    def on_source_changed(self, source):
        if self._source_change_in_progress:
            return

        old_source = self.source_mode
        if source == old_source:
            self._set_source_ui()
            return

        if not self.confirm_abandon_changes():
            self._source_change_in_progress = True
            try:
                self.source_combo.setCurrentText(old_source)
            finally:
                self._source_change_in_progress = False
            return

        self.source_mode = source
        self._current_s3_record = None

        if source == "Local Storage":
            if self._local_open_directory is not None:
                self.open_directory = Path(
                    self._local_open_directory
                )

        if source == "S3":
            try:
                self._ensure_s3_repository()
                self._s3_records = self._s3_repository.list_capture_index()
            except (AwsAuthError, S3StoreError, OSError, ValueError) as exc:
                QMessageBox.critical(self, "Unable to open S3", str(exc))
                self._s3_records = []

        self._set_source_ui()
        self._applied_filters = self._current_filter_settings()
        self.refresh_file_browser()
        self.apply_filters_button.setEnabled(False)

    def apply_filters(self):
        self._applied_filters = self._current_filter_settings()
        self._browser_filter_settings = dict(self._applied_filters)
        self.refresh_file_browser()
        self.apply_filters_button.setEnabled(False)

    def _refresh_s3_browser(self):
        self.directory_label.setText(f"S3 bucket: {S3_BUCKET_NAME}")
        self.file_list.clear()

        sites = {
            record.metadata["site"]
            for record in self._s3_records
            if record.metadata["site"]
        }
        self._refresh_site_filter(sites)

        applied = getattr(
            self,
            "_applied_filters",
            self._current_filter_settings(),
        )

        verified_filter = applied["verified"]
        classification_filter = applied["classification"]
        type_filter = applied["type"]
        site_filter = applied["site"]

        classification_code_filter = (
            "Any"
            if classification_filter == "Any"
            else CLASSIFICATION_NAME_TO_CODE[classification_filter]
        )

        records = []
        for record in self._s3_records:
            meta = record.metadata

            if verified_filter != "Any":
                expected = verified_filter == "Yes"
                if meta["verified"] != expected:
                    continue

            if (
                classification_code_filter != "Any"
                and meta["classification"] != classification_code_filter
            ):
                continue

            if type_filter != "Any" and meta["type"] != type_filter:
                continue

            if site_filter != "Any" and meta["site"] != site_filter:
                continue

            records.append(record)

        reverse = applied["sort"] == "Filename descending"
        records.sort(key=lambda r: r.filename.lower(), reverse=reverse)

        selected = None
        current_key = (
            self._current_s3_record.json_key
            if self._current_s3_record is not None
            else None
        )

        for record in records:
            item = QListWidgetItem(record.filename)
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setToolTip(record.json_key)
            self.file_list.addItem(item)

            if current_key and record.json_key == current_key:
                selected = item

        if selected is not None:
            self.file_list.setCurrentItem(selected)
            self.file_list.scrollToItem(selected)

    def open_selected_browser_item(self):
        item = self.file_list.currentItem()
        if item is None:
            return

        if self.source_mode == "S3":
            record = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(record, S3CaptureRecord):
                return
            if not self.confirm_abandon_changes():
                return

            try:
                repo = self._ensure_s3_repository()
                local_mp4, opened_record = repo.open_capture(record)

                if opened_record.json_key != record.json_key:
                    self._replace_s3_record(record, opened_record)

                self._load_capture_path(
                    local_mp4,
                    source_mode="S3",
                    s3_record=opened_record,
                    confirm=False,
                )
            except (
                AwsAuthError,
                S3StoreError,
                RuntimeError,
                OSError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                QMessageBox.critical(self, "Unable to open S3 capture", str(exc))
            return

        # Local Storage behavior.
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, str):
            return
        p = Path(data)

        if p.is_dir():
            if self.confirm_abandon_changes():
                self.open_directory = p
                self._local_open_directory = p
                self._invalidate_local_browser_cache()
                self.refresh_file_browser()
        elif p.suffix.lower() == ".mp4":
            self.load_new_capture(p)

    def load_new_capture(self, video_path):
        self._load_capture_path(
            Path(video_path),
            source_mode="Local Storage",
            s3_record=None,
            confirm=True,
        )

    def _load_capture_path(
        self,
        video_path: Path,
        *,
        source_mode: str,
        s3_record: S3CaptureRecord | None,
        confirm: bool,
    ):
        if confirm and not self.confirm_abandon_changes():
            return

        try:
            cd = load_capture(video_path)

            if isinstance(cd.sidecar, dict):
                upgraded, changed = normalize_sidecar(cd.sidecar)
                cd.sidecar = upgraded
                if changed and source_mode == "Local Storage":
                    self._write_local_sidecar_atomic(cd.sidecar_path, upgraded)

            cr = replay_candidate_finder(cd, self.candidate_config)
            vr = VideoReader(cd.video_path)

        except (RuntimeError, OSError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "Unable to open capture", str(exc))
            return

        if self.video_reader is not None:
            self.video_reader.close()

        self.capture_data = cd
        self.candidate_result = cr
        self.solution_result = None
        self.video_reader = vr

        if source_mode == "Local Storage":
            self.open_directory = cd.video_path.parent
            self._local_open_directory = self.open_directory

        self.frame_number = 0
        self.updating_slider = False

        self.source_mode = source_mode
        self._current_s3_record = s3_record

        self.create_ui()
        self.connect_controls()
        self.load_editor_fields()
        self.update_capture_information()
        self.set_frame(0, force=True)
        self.focus_description_at_end()

    def _upgrade_loaded_sidecar(self, *, persist_local: bool):
        if self.capture_data is None or not isinstance(
            self.capture_data.sidecar, dict
        ):
            return

        upgraded, changed = normalize_sidecar(self.capture_data.sidecar)
        self.capture_data.sidecar = upgraded

        if changed and persist_local:
            self._write_local_sidecar_atomic(
                self.capture_data.sidecar_path,
                upgraded,
            )
            self.loaded_metadata = copy.deepcopy(self.metadata())
            self.restore_loaded_values()

    @staticmethod
    def _write_local_sidecar_atomic(path: Path, sidecar):
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(sidecar, indent=4) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)

    def _sidecar_from_editor(self):
        values = self.current_values()
        sidecar = copy.deepcopy(self.capture_data.sidecar)

        camera = sidecar.setdefault("camera", {})
        camera.update(
            site_name=values["site_name"],
            latitude_degrees=values["latitude"],
            longitude_degrees=values["longitude"],
            bearing_degrees=values["bearing"],
            hfov_degrees=values["hfov"],
            vfov_degrees=values["vfov"],
        )

        capture = sidecar.setdefault("capture", {})
        classification_code = CLASSIFICATION_NAME_TO_CODE[
            values["classification"]
        ]

        # ANOMALY is a final algorithm/human adjudication and is always
        # verified. FLASH may remain unverified until human review.
        if classification_code == "ANOMALY":
            capture["verified"] = True
            capture["classification"] = "ANOMALY"
            capture["type"] = "UK"
        else:
            capture["verified"] = values["verified"]
            capture["classification"] = "FLASH"
            capture["type"] = (
                values["type"]
                if values["verified"]
                else "UK"
            )

        capture["description"] = values["description"]

        sidecar, _changed = normalize_sidecar(sidecar)
        return sidecar

    def save_changes(self):
        if self.capture_data is None or self.capture_data.sidecar is None:
            return False

        sidecar = self._sidecar_from_editor()

        if self.source_mode == "S3":
            if self._current_s3_record is None:
                QMessageBox.critical(
                    self,
                    "Unable to save",
                    "No S3 capture is associated with the current clip.",
                )
                return False

            try:
                repo = self._ensure_s3_repository()
                old_record = self._current_s3_record
                new_record = repo.save_capture(old_record, sidecar)

                # Keep the downloaded working copy synchronized with S3.
                self._write_local_sidecar_atomic(
                    self.capture_data.sidecar_path,
                    new_record.sidecar,
                )

            except (
                AwsAuthError,
                S3StoreError,
                OSError,
                ValueError,
                TypeError,
            ) as exc:
                QMessageBox.critical(self, "Unable to save S3 capture", str(exc))
                return False

            self.capture_data.sidecar = new_record.sidecar
            self._replace_s3_record(old_record, new_record)
            self._current_s3_record = new_record

            if hasattr(self, "capture_value_labels"):
                self.capture_value_labels["video"].setText(
                    new_record.filename
                )

            current_item = self.file_list.currentItem()
            if current_item is not None:
                current_item.setData(
                    Qt.ItemDataRole.UserRole,
                    new_record,
                )
                current_item.setText(new_record.filename)
                current_item.setToolTip(new_record.json_key)

        else:
            try:
                self._write_local_sidecar_atomic(
                    self.capture_data.sidecar_path,
                    sidecar,
                )
            except OSError as exc:
                QMessageBox.critical(
                    self,
                    "Unable to save sidecar",
                    str(exc),
                )
                return False

            self.capture_data.sidecar = sidecar
            self._update_cached_local_metadata(
                self.capture_data.video_path,
                sidecar,
            )

        self.loaded_metadata = copy.deepcopy(self.metadata())

        # Refresh only the QListWidget from the already-built local/S3 index.
        self.refresh_file_browser()
        return True

    def _replace_s3_record(
        self,
        old_record: S3CaptureRecord,
        new_record: S3CaptureRecord,
    ):
        for index, record in enumerate(self._s3_records):
            if record.json_key == old_record.json_key:
                self._s3_records[index] = new_record
                return
        self._s3_records.append(new_record)

    def load_adjacent_clip(self, direction):
        item = self.file_list.currentItem()
        if item is None:
            return

        row = self.file_list.row(item)
        target = row + direction
        if target < 0 or target >= self.file_list.count():
            return

        self.file_list.setCurrentRow(target)
        self.open_selected_browser_item()

    def save_and_next_clip(self):
        item = self.file_list.currentItem()
        if item is None:
            return

        original_row = self.file_list.row(item)

        if self.has_unsaved_changes():
            if not self.save_changes():
                return

            # save_changes() refreshes the list. A newly verified capture may
            # disappear from the default Verified=No view, so the next capture
            # shifts into the same row.
            if self.file_list.count() == 0:
                return

            target = min(
                original_row,
                self.file_list.count() - 1,
            )
            self.file_list.setCurrentRow(target)
            self.open_selected_browser_item()
            return

        target = original_row + 1
        if target < self.file_list.count():
            self.file_list.setCurrentRow(target)
            self.open_selected_browser_item()

    def closeEvent(self, event):
        if not self.confirm_abandon_changes():
            event.ignore()
            return

        if self.video_reader is not None:
            self.video_reader.close()

        if self._s3_repository is not None:
            self._s3_repository.close()

        event.accept()
