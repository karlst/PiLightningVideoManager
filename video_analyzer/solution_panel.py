"""Solution-filter result panel for the desktop video analyzer."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
)

from video_analyzer.solution_filter import SolutionResult
from video_analyzer.solution_types import CATEGORY_FAILED_CANDIDATE


class SolutionPanel(QGroupBox):
    """Display the current SolutionFilter result."""

    def __init__(
        self,
        result: SolutionResult,
    ) -> None:
        super().__init__("Solution filter")

        self._solution_label = QLabel()
        self._reason_label = QLabel()
        self._reason_label.setWordWrap(True)

        form_layout = QFormLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(6)

        form_layout.addRow(
            "Solution:",
            self._solution_label,
        )
        form_layout.addRow(
            "Reason:",
            self._reason_label,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(form_layout)

        self.set_result(result)

    def set_result(
        self,
        result: SolutionResult,
    ) -> None:
        if result.is_solution:
            self._solution_label.setText("YES")
            background = "#d9f2d9"
            border = "#4f9b4f"
        elif result.category == CATEGORY_FAILED_CANDIDATE:
            self._solution_label.setText("NO — NOT A CANDIDATE")
            background = "#eeeeee"
            border = "#888888"
        else:
            self._solution_label.setText("NO — FALSE POSITIVE")
            background = "#dbeafe"
            border = "#4f79b8"

        self._reason_label.setText(
            result.reason
        )

        self.setStyleSheet(
            f"""
            QGroupBox {{
                background-color: {background};
                border: 1px solid {border};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 3px;
            }}
            """
        )
