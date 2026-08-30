"""Entry point: python -m camera_capture_manager.ccm"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from camera_capture_manager.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    try:
        window = MainWindow()
    except RuntimeError as error:
        QMessageBox.critical(None, "Camera Capture Manager", str(error))
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
