"""Main Qt window for Camera Capture Manager (CCM)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTableWidgetSelectionRange,
    QVBoxLayout,
    QWidget,
)

from camera_capture_manager.app_launcher import launch_tool
from camera_capture_manager.camera_dialog import CameraDialog
from camera_capture_manager.camera_registry import CameraDefinition, CameraRegistry
from camera_capture_manager.pi_connection import PiConnection, RemoteCapture, RemoteInventory
from camera_capture_manager.settings import CcmSettings
from camera_capture_manager.transfer_manager import perform_batch
from version import VERSION


def human_size(value: int | None) -> str:
    if value is None:
        return "—"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


class TransferWorker(QObject):
    progress = Signal(str, int, int)
    finished = Signal(int, object)

    def __init__(
        self,
        camera: CameraDefinition,
        captures: list[RemoteCapture],
        destination: Path | None,
        operation: str,
    ) -> None:
        super().__init__()
        self.camera = camera
        self.captures = captures
        self.destination = destination
        self.operation = operation

    def run(self) -> None:
        try:
            completed, errors = perform_batch(
                self.camera,
                self.captures,
                self.destination,
                self.operation,
                lambda name, done, total: self.progress.emit(name, done, total),
            )
        except Exception as error:
            completed = 0
            errors = [str(error)]
        self.finished.emit(completed, errors)


class RemoteWorker(QObject):
    """Run SSH connection tests and Pi inventory reads off the Qt UI thread."""

    finished = Signal(object, object, object, object, object)

    def __init__(
        self,
        camera: CameraDefinition,
        load_inventory: bool,
        operation: str,
    ) -> None:
        super().__init__()
        self.camera = camera
        self.load_inventory = load_inventory
        self.operation = operation

    def run(self) -> None:
        hostname = None
        inventory = None
        error_text = None

        try:
            with PiConnection(self.camera) as connection:
                hostname = connection.test_connection()
                if self.load_inventory:
                    inventory = connection.inventory()
        except Exception as error:
            error_text = str(error)

        self.finished.emit(
            self.camera,
            self.operation,
            hostname,
            inventory,
            error_text,
        )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Camera Capture Manager — v{VERSION}")
        self.resize(1180, 760)

        self.registry = CameraRegistry()
        self.settings = CcmSettings()
        self.current_camera: CameraDefinition | None = None
        self.inventory: RemoteInventory | None = None
        self.destination = self.settings.host_destination
        self.transfer_thread: QThread | None = None
        self.transfer_worker: TransferWorker | None = None
        self.host_capture_stems: set[str] = set()
        self.remote_thread: QThread | None = None
        self.remote_worker: RemoteWorker | None = None
        self.remote_operation: str | None = None

        self._create_ui()
        self.refresh_camera_table()
        self.update_action_state()

    def _create_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(7)

        camera_group = QGroupBox("Registered Cameras")
        camera_layout = QVBoxLayout(camera_group)

        self.camera_table = QTableWidget(0, 3)
        self.camera_table.setHorizontalHeaderLabels(["Camera", "IP Address", "Status"])
        self.camera_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.camera_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.camera_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.camera_table.verticalHeader().setVisible(False)
        header = self.camera_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.camera_table.setMinimumHeight(72)
        self.camera_table.setMaximumHeight(120)
        camera_layout.addWidget(self.camera_table)

        camera_buttons = QHBoxLayout()
        self.add_button = QPushButton("Add Camera")
        self.edit_button = QPushButton("Edit")
        self.remove_button = QPushButton("Remove")
        self.test_button = QPushButton("Test Connection")
        self.connect_button = QPushButton("Refresh Pi")
        for button in (
            self.add_button,
            self.edit_button,
            self.remove_button,
            self.test_button,
        ):
            camera_buttons.addWidget(button)
        camera_buttons.addStretch(1)
        camera_layout.addLayout(camera_buttons)
        main.addWidget(camera_group, stretch=0)

        remote_group = QGroupBox("Remote Captures")
        remote_layout = QVBoxLayout(remote_group)
        self.remote_summary = QLabel("Select a registered camera.")
        remote_layout.addWidget(self.remote_summary)

        self.capture_table = QTableWidget(0, 4)
        self.capture_table.setHorizontalHeaderLabels(
            ["Capture", "Date/Time", "Size", "In Host Folder"]
        )
        self.capture_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.capture_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.capture_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.capture_table.verticalHeader().setVisible(False)
        capture_header = self.capture_table.horizontalHeader()
        capture_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        capture_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        capture_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        capture_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.capture_table.setColumnWidth(1, 150)
        self.capture_table.setColumnWidth(2, 90)
        self.capture_table.setColumnWidth(3, 115)
        remote_layout.addWidget(self.capture_table, stretch=1)

        remote_action_buttons = QHBoxLayout()
        self.select_all_button = QPushButton("Select All")
        self.select_new_button = QPushButton("Select New")
        self.copy_button = QPushButton("Copy Selected to Host")
        self.move_button = QPushButton("Move Selected to Host")
        self.delete_button = QPushButton("Delete Selected from Pi")
        for button in (
            self.select_all_button,
            self.select_new_button,
            self.connect_button,
            self.copy_button,
            self.move_button,
            self.delete_button,
        ):
            remote_action_buttons.addWidget(button)
        remote_action_buttons.addStretch(1)
        remote_layout.addLayout(remote_action_buttons)
        main.addWidget(remote_group, stretch=5)

        transfer_group = QGroupBox("Host Captures")
        transfer_layout = QGridLayout(transfer_group)
        self.destination_label = QLabel(str(self.destination))
        self.destination_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.browse_button = QPushButton("Browse...")
        transfer_layout.addWidget(QLabel("Destination:"), 0, 0)
        transfer_layout.addWidget(self.destination_label, 0, 1)
        transfer_layout.addWidget(self.browse_button, 0, 2)

        self.host_table = QTableWidget(0, 1)
        self.host_table.setHorizontalHeaderLabels(["MP4 Capture"])
        self.host_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.host_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.host_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.host_table.verticalHeader().setVisible(False)
        host_header = self.host_table.horizontalHeader()
        host_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.host_table.setMinimumHeight(90)
        self.host_table.setMaximumHeight(150)
        transfer_layout.addWidget(self.host_table, 1, 0, 1, 3)

        self.host_status_label = QLabel("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        transfer_layout.addWidget(self.host_status_label, 2, 0)
        transfer_layout.addWidget(self.progress_bar, 2, 1, 1, 2)

        self.vce_button = QPushButton("Open Selected in Vce")
        self.vfa_button = QPushButton("Open Selected in Vfa")
        transfer_layout.addWidget(self.vce_button, 3, 1)
        transfer_layout.addWidget(self.vfa_button, 3, 2)
        main.addWidget(transfer_group)

        self.camera_table.itemSelectionChanged.connect(self.on_camera_selected)
        self.capture_table.itemSelectionChanged.connect(self.update_action_state)
        self.host_table.itemSelectionChanged.connect(self.update_action_state)
        self.add_button.clicked.connect(self.add_camera)
        self.edit_button.clicked.connect(self.edit_camera)
        self.remove_button.clicked.connect(self.remove_camera)
        self.test_button.clicked.connect(self.test_camera)
        self.connect_button.clicked.connect(self.refresh_remote)
        self.select_all_button.clicked.connect(self.capture_table.selectAll)
        self.select_new_button.clicked.connect(self.select_new)
        self.browse_button.clicked.connect(self.choose_destination)
        self.copy_button.clicked.connect(lambda: self.start_transfer("copy"))
        self.move_button.clicked.connect(lambda: self.start_transfer("move"))
        self.delete_button.clicked.connect(lambda: self.start_transfer("delete"))
        self.vce_button.clicked.connect(lambda: self.open_selected_tool("Vce"))
        self.vfa_button.clicked.connect(lambda: self.open_selected_tool("Vfa"))

        # Keep table selection visually clear without Windows focus bars or
        # accidental bold-looking/current-cell emphasis. Headers stay normal
        # weight at all times; selected rows use a light-blue fill.
        table_style = """
            QTableWidget {
                outline: 0;
                selection-background-color: #cfe8ff;
                selection-color: black;
            }
            QTableWidget::item {
                border: 0px;
            }
            QTableWidget::item:selected {
                background-color: #cfe8ff;
                color: black;
                font-weight: normal;
                border: 0px;
            }
            QHeaderView::section {
                font-weight: normal;
            }
        """
        for table in (self.camera_table, self.capture_table, self.host_table):
            table.setStyleSheet(table_style)

        # Consistent clickable affordance across CCM.
        for button in central.findChildren(QAbstractButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.refresh_host_table()

    def refresh_camera_table(self, select_name: str | None = None) -> None:
        cameras = self.registry.cameras
        self.camera_table.setRowCount(len(cameras))
        selected_row = None

        for row, camera in enumerate(cameras):
            name_item = QTableWidgetItem(camera.name)
            name_item.setData(Qt.ItemDataRole.UserRole, camera)
            self.camera_table.setItem(row, 0, name_item)
            self.camera_table.setItem(row, 1, QTableWidgetItem(camera.ip_address))
            status = (
                "Connected"
                if self.current_camera is not None
                and self.inventory is not None
                and self.current_camera.name.casefold() == camera.name.casefold()
                else "Not connected"
            )
            self.camera_table.setItem(row, 2, QTableWidgetItem(status))
            if select_name and camera.name.casefold() == select_name.casefold():
                selected_row = row

        if selected_row is not None:
            self.camera_table.selectRow(selected_row)
        elif cameras and self.camera_table.currentRow() < 0:
            self.camera_table.selectRow(0)

    def selected_camera(self) -> CameraDefinition | None:
        row = self.camera_table.currentRow()
        if row < 0:
            return None
        item = self.camera_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def on_camera_selected(self) -> None:
        selected = self.selected_camera()

        # CCM has one active remote inventory at a time. Changing cameras
        # invalidates the previous connection state everywhere in the UI.
        if (
            self.current_camera is not None
            and selected is not None
            and self.current_camera.name.casefold() == selected.name.casefold()
        ):
            return

        if self.current_camera is not None:
            self._set_camera_status(self.current_camera, "Not connected")

        self.current_camera = selected
        self.inventory = None
        self.capture_table.setRowCount(0)

        if self.current_camera is None:
            self.remote_summary.setText("Select a registered camera.")
        else:
            self._set_camera_status(self.current_camera, "Not connected")
            self.remote_summary.setText(
                f"{self.current_camera.name} — {self.current_camera.ip_address} — not connected"
            )
        self.update_action_state()

    def add_camera(self) -> None:
        dialog = CameraDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            camera = dialog.camera()
            self.registry.add(camera)
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Unable to Add Camera", str(error))
            return
        self.refresh_camera_table(camera.name)
        self.refresh_remote()

    def edit_camera(self) -> None:
        camera = self.selected_camera()
        if camera is None:
            return
        dialog = CameraDialog(self, camera)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            updated = dialog.camera()
            self.registry.update(camera.name, updated)
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Unable to Edit Camera", str(error))
            return
        self.refresh_camera_table(updated.name)
        self.refresh_remote()

    def remove_camera(self) -> None:
        camera = self.selected_camera()
        if camera is None:
            return
        result = QMessageBox.question(
            self,
            "Remove Camera",
            f"Remove '{camera.name}' from the CCM registry?\n\nNo files on the Pi will be changed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            self.registry.remove(camera.name)
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Unable to Remove Camera", str(error))
            return
        self.current_camera = None
        self.inventory = None
        self.refresh_camera_table()
        self.capture_table.setRowCount(0)
        self.remote_summary.setText("Select a registered camera.")
        self.update_action_state()

    def _set_camera_status(self, camera: CameraDefinition, text: str) -> None:
        for row in range(self.camera_table.rowCount()):
            item = self.camera_table.item(row, 0)
            candidate = item.data(Qt.ItemDataRole.UserRole) if item else None
            if candidate and candidate.name == camera.name:
                self.camera_table.setItem(row, 2, QTableWidgetItem(text))
                return

    def test_camera(self) -> None:
        """Test SSH authentication only; do not scan the remote capture folder."""
        camera = self.selected_camera()
        if camera is None or self.remote_thread is not None:
            return

        self._start_remote_operation(
            camera,
            load_inventory=False,
            operation="test",
        )

    def refresh_remote(self, *_args, show_success: bool = False) -> None:
        """Asynchronously connect to the selected Pi and load its capture inventory."""
        camera = self.selected_camera()
        if camera is None or self.remote_thread is not None:
            return

        self.current_camera = camera
        self.inventory = None
        self.capture_table.setRowCount(0)
        self._set_camera_status(camera, "Connecting...")
        self.remote_summary.setText(
            f"{camera.name} — {camera.ip_address} — connecting..."
        )
        self.update_action_state()

        self._start_remote_operation(
            camera,
            load_inventory=True,
            operation="refresh_success" if show_success else "refresh",
        )

    def _start_remote_operation(
        self,
        camera: CameraDefinition,
        load_inventory: bool,
        operation: str,
    ) -> None:
        thread = QThread(self)
        worker = RemoteWorker(
            camera,
            load_inventory,
            operation,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        # Connect directly to a QObject-bound MainWindow method. Qt then uses
        # a queued cross-thread signal and executes the UI update on the main
        # GUI thread. Do not put a Python lambda between the worker and UI.
        worker.finished.connect(
            self._on_remote_operation_finished
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self.remote_thread = thread
        self.remote_worker = worker
        self.remote_operation = operation
        self.update_action_state()
        thread.start()

    def _on_remote_operation_finished(
        self,
        camera: CameraDefinition,
        operation: str,
        hostname: object,
        inventory: object,
        error_text: object,
    ) -> None:
        self.remote_thread = None
        self.remote_worker = None
        self.remote_operation = None

        # Ignore display updates if the user selected a different camera while
        # the SSH operation was running.
        selected = self.selected_camera()
        still_selected = (
            selected is not None
            and selected.name.casefold() == camera.name.casefold()
        )

        if error_text:
            self._set_camera_status(camera, "Offline")
            if still_selected:
                self.current_camera = camera
                self.inventory = None
                self.capture_table.setRowCount(0)
                self.remote_summary.setText(
                    f"{camera.name} — {camera.ip_address} — not connected"
                )
            self.update_action_state()
            QMessageBox.warning(
                self,
                "Unable to Connect to Pi",
                str(error_text),
            )
            return

        if operation == "test":
            # A connection test proves SSH access, but it deliberately does not
            # imply that the remote inventory has been loaded.
            self._set_camera_status(camera, "SSH OK")
            if still_selected:
                self.remote_summary.setText(
                    f"{camera.name} — {camera.ip_address} — SSH OK; press Refresh Pi to load captures"
                )
            self.update_action_state()
            QMessageBox.information(
                self,
                "Connection Successful",
                f"SSH connection to {camera.name} succeeded.\n"
                f"Pi hostname: {hostname}",
            )
            return

        if not isinstance(inventory, RemoteInventory):
            self._set_camera_status(camera, "Offline")
            if still_selected:
                self.inventory = None
                self.remote_summary.setText(
                    f"{camera.name} — {camera.ip_address} — inventory unavailable"
                )
            self.update_action_state()
            return

        self._set_camera_status(camera, "Connected")

        if still_selected:
            self.current_camera = camera
            self.inventory = inventory
            self.populate_capture_table()

            free_text = (
                f"{human_size(inventory.free_bytes)} free"
                if inventory.free_bytes is not None
                else "Free space unavailable"
            )
            self.remote_summary.setText(
                f"{camera.name} — {camera.ip_address}    "
                f"{len(inventory.captures)} complete captures    "
                f"{free_text}"
            )

        self.update_action_state()

        if operation == "refresh_success":
            QMessageBox.information(
                self,
                "Connection Successful",
                f"Connected to {camera.name}.\nPi hostname: {hostname}",
            )

    def populate_capture_table(self) -> None:
        captures = self.inventory.captures if self.inventory else []
        self.capture_table.setRowCount(len(captures))
        for row, capture in enumerate(captures):
            capture_item = QTableWidgetItem(capture.stem)
            capture_item.setData(Qt.ItemDataRole.UserRole, capture)
            timestamp = datetime.fromtimestamp(capture.modified_time).strftime("%Y-%m-%d %H:%M:%S")
            host_stems = getattr(self, "host_capture_stems", set())
            status = "Yes" if capture.stem in host_stems else "No"
            self.capture_table.setItem(row, 0, capture_item)
            self.capture_table.setItem(row, 1, QTableWidgetItem(timestamp))
            self.capture_table.setItem(row, 2, QTableWidgetItem(human_size(capture.total_size)))
            self.capture_table.setItem(row, 3, QTableWidgetItem(status))

    def selected_captures(self) -> list[RemoteCapture]:
        rows = sorted({index.row() for index in self.capture_table.selectionModel().selectedRows()})
        captures: list[RemoteCapture] = []
        for row in rows:
            item = self.capture_table.item(row, 0)
            capture = item.data(Qt.ItemDataRole.UserRole) if item else None
            if capture is not None:
                captures.append(capture)
        return captures

    def select_new(self) -> None:
        self.capture_table.clearSelection()
        for row in range(self.capture_table.rowCount()):
            status_item = self.capture_table.item(row, 3)
            if status_item and status_item.text() == "No":
                self.capture_table.setRangeSelected(
                    QTableWidgetSelectionRange(row, 0, row, self.capture_table.columnCount() - 1),
                    True,
                )

    def choose_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Host Destination",
            str(self.destination),
        )
        if not folder:
            return

        self.destination = Path(folder)
        self.destination_label.setText(str(self.destination))
        self.destination_label.repaint()

        try:
            self.settings.set_host_destination(self.destination)
        except OSError as error:
            QMessageBox.warning(self, "Unable to Save CCM Settings", str(error))

        self.refresh_host_table()
        self.update_action_state()

    def refresh_host_table(self) -> None:
        """List MP4 files in the host destination using filenames only.

        Intentionally simple and synchronous: one directory enumeration,
        no worker thread, no JSON pairing, no stat/is_file calls, and no
        metadata reads.
        """
        destination = self.destination
        self.host_capture_stems = set()
        self.host_table.setRowCount(0)

        try:
            mp4_paths = sorted(
                (
                    path
                    for path in destination.iterdir()
                    if path.name.casefold().endswith(".mp4")
                ),
                key=lambda path: path.name.casefold(),
            )
        except OSError as error:
            self.host_status_label.setText(
                f"Unable to read host folder: {error}"
            )
            self.update_action_state()
            return

        self.host_capture_stems = {
            path.stem
            for path in mp4_paths
        }

        self.host_table.setRowCount(
            len(mp4_paths)
        )

        for row_index, mp4_path in enumerate(mp4_paths):
            capture_item = QTableWidgetItem(
                mp4_path.stem
            )
            capture_item.setData(
                Qt.ItemDataRole.UserRole,
                mp4_path,
            )
            self.host_table.setItem(
                row_index,
                0,
                capture_item,
            )

        # Refresh the remote/local comparison in one cheap UI batch.
        # "Host" means the computer running CCM, not the Pi.
        self.capture_table.setUpdatesEnabled(False)
        try:
            for row in range(self.capture_table.rowCount()):
                capture_item = self.capture_table.item(row, 0)
                capture = (
                    capture_item.data(Qt.ItemDataRole.UserRole)
                    if capture_item is not None
                    else None
                )
                if capture is None:
                    continue

                status_text = (
                    "Yes"
                    if capture.stem in self.host_capture_stems
                    else "No"
                )

                status_item = self.capture_table.item(row, 3)
                if status_item is None:
                    self.capture_table.setItem(
                        row,
                        3,
                        QTableWidgetItem(status_text),
                    )
                elif status_item.text() != status_text:
                    status_item.setText(status_text)
        finally:
            self.capture_table.setUpdatesEnabled(True)
            self.capture_table.viewport().update()

        self.host_status_label.setText(
            f"{len(mp4_paths)} MP4 file(s) in host folder"
        )
        self.update_action_state()

    def selected_host_capture(self) -> Path | None:
        rows = self.host_table.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        item = self.host_table.item(rows[0].row(), 0)
        path = item.data(Qt.ItemDataRole.UserRole) if item else None
        return Path(path) if path is not None else None

    def update_action_state(self) -> None:
        camera_selected = self.selected_camera() is not None
        captures = self.selected_captures() if hasattr(self, "capture_table") else []
        selected_count = len(captures)
        busy = self.transfer_thread is not None or self.remote_thread is not None
        inventory_ready = self.inventory is not None and camera_selected

        self.edit_button.setEnabled(camera_selected and not busy)
        self.remove_button.setEnabled(camera_selected and not busy)
        self.test_button.setEnabled(camera_selected and not busy)
        self.connect_button.setEnabled(camera_selected and not busy)
        self.select_all_button.setEnabled(inventory_ready and not busy)
        self.select_new_button.setEnabled(inventory_ready and not busy)
        self.browse_button.setEnabled(not busy)
        self.copy_button.setEnabled(inventory_ready and selected_count > 0 and not busy)
        self.move_button.setEnabled(inventory_ready and selected_count > 0 and not busy)
        self.delete_button.setEnabled(inventory_ready and selected_count > 0 and not busy)
        host_capture_selected = self.selected_host_capture() is not None
        self.vce_button.setEnabled(host_capture_selected and not busy)
        self.vfa_button.setEnabled(host_capture_selected and not busy)

    def start_transfer(self, operation: str) -> None:
        camera = self.selected_camera()
        captures = self.selected_captures()
        if camera is None or not captures:
            return

        destination: Path | None = self.destination if operation in {"copy", "move"} else None

        if operation == "delete":
            response = QMessageBox.question(
                self,
                "Delete Captures from Pi",
                f"Delete {len(captures)} capture(s) from {camera.name}?\n\n"
                f"This permanently removes {len(captures) * 2} files from the Pi.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if response != QMessageBox.StandardButton.Yes:
                return

        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        thread = QThread(self)
        worker = TransferWorker(camera, captures, destination, operation)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.on_transfer_progress)
        worker.finished.connect(self.on_transfer_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self.transfer_thread = thread
        self.transfer_worker = worker
        self.update_action_state()
        thread.start()

    def on_transfer_progress(self, filename: str, done: int, total: int) -> None:
        percent = int(done * 100 / total) if total else 0
        self.progress_bar.setValue(max(0, min(100, percent)))

    def on_transfer_finished(self, completed: int, errors: object) -> None:
        error_list = list(errors) if isinstance(errors, list) else []
        self.transfer_thread = None
        self.transfer_worker = None
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)

        if error_list:
            detail = "\n".join(error_list[:12])
            if len(error_list) > 12:
                detail += f"\n...and {len(error_list) - 12} more."
            QMessageBox.warning(self, "CCM Transfer Completed with Errors", detail)

        self.refresh_host_table()
        self.refresh_remote()

    def open_selected_tool(self, tool_name: str) -> None:
        local_mp4 = self.selected_host_capture()
        if local_mp4 is None:
            return

        if not local_mp4.is_file():
            # If the selected MP4 disappears after selection, refresh quietly
            # and disable Open. Sidecar handling belongs to Vce/Vfa.
            self.refresh_host_table()
            self.update_action_state()
            return

        try:
            launch_tool(tool_name, local_mp4)
        except RuntimeError as error:
            QMessageBox.warning(self, f"Unable to Launch {tool_name}", str(error))


    def closeEvent(self, event) -> None:
        # Avoid leaving a local host-scan QThread alive while the Qt window is
        # being destroyed. Host scans are read-only, so waiting is safe.
        event.accept()
