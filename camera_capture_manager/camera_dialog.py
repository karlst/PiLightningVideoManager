"""Add/Edit registered-camera dialog for CCM."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from camera_capture_manager.camera_registry import CameraDefinition
from camera_capture_manager.pi_connection import (
    PiConnection,
    ccm_key_exists,
    ccm_private_key_path,
    ensure_ccm_key,
)


class CameraDialog(QDialog):
    def __init__(self, parent=None, camera: CameraDefinition | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Camera" if camera is not None else "Add Camera")
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(camera.name if camera else "")
        self.ip_edit = QLineEdit(camera.ip_address if camera else "")
        self.user_edit = QLineEdit(camera.ssh_user if camera else "")

        form.addRow("Camera name:", self.name_edit)
        form.addRow("IP address:", self.ip_edit)
        form.addRow("SSH user:", self.user_edit)
        layout.addLayout(form)

        action_row = QHBoxLayout()
        self.key_button = QPushButton("Set Up SSH Access...")
        self.test_button = QPushButton("Test Connection")
        action_row.addWidget(self.key_button)
        action_row.addWidget(self.test_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.key_button.clicked.connect(self.setup_key)
        self.test_button.clicked.connect(self.test_connection)

        for button in self.findChildren(QAbstractButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)

    def camera(self) -> CameraDefinition:
        return CameraDefinition(
            name=self.name_edit.text(),
            ip_address=self.ip_edit.text(),
            ssh_user=self.user_edit.text(),
        ).validated()

    def _validate_and_accept(self) -> None:
        try:
            self.camera()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Camera", str(error))
            return
        self.accept()

    def test_connection(self) -> None:
        try:
            camera = self.camera()
            with PiConnection(camera) as connection:
                hostname = connection.test_connection()
            QMessageBox.information(
                self,
                "Connection Successful",
                f"Connected to {camera.name} at {camera.ip_address}.\nPi hostname: {hostname}",
            )
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Camera", str(error))
        except RuntimeError as error:
            message = str(error)
            if "SSH access is not set up" in message or "Authentication failed" in message:
                box = QMessageBox(self)
                box.setWindowTitle("SSH Access Required")
                box.setIcon(QMessageBox.Icon.Warning)
                box.setText(
                    f"CCM cannot authenticate to {self.ip_edit.text().strip()}."
                )
                box.setInformativeText(
                    "Set up CCM's dedicated SSH key for this camera before testing the connection."
                )
                setup_button = box.addButton("Set Up SSH Access...", QMessageBox.ButtonRole.AcceptRole)
                box.addButton(QMessageBox.StandardButton.Cancel)
                box.exec()
                if box.clickedButton() is setup_button:
                    self.setup_key()
                return

            QMessageBox.warning(self, "Connection Failed", message)

    def setup_key(self) -> None:
        try:
            camera = self.camera()
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Camera", str(error))
            return

        if not ccm_key_exists():
            response = QMessageBox.question(
                self,
                "Create CCM SSH Key",
                "Camera Capture Manager does not have its dedicated SSH key yet.\n\n"
                f"Create:\n{ccm_private_key_path()}\n\n"
                "This key will be used only by CCM for registered camera Pis.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if response != QMessageBox.StandardButton.Yes:
                return

            try:
                ensure_ccm_key()
            except (OSError, RuntimeError, ValueError) as error:
                QMessageBox.warning(self, "Unable to Create SSH Key", str(error))
                return

        password, accepted = QInputDialog.getText(
            self,
            "Authorize CCM on Pi",
            f"Enter the SSH password for {camera.ssh_user}@{camera.ip_address}.\n\n"
            "CCM will add its public key to this Pi's ~/.ssh/authorized_keys.\n"
            "The password is used only for this setup operation and is not stored.",
            QLineEdit.EchoMode.Password,
        )
        if not accepted or not password:
            return

        try:
            PiConnection.install_public_key(camera, password)
            with PiConnection(camera) as connection:
                hostname = connection.test_connection()
        except RuntimeError as error:
            QMessageBox.warning(self, "SSH Access Setup Failed", str(error))
            return

        QMessageBox.information(
            self,
            "SSH Access Ready",
            "CCM key authentication is working.\n\n"
            f"Pi hostname: {hostname}\n"
            f"CCM private key: {ccm_private_key_path()}",
        )
