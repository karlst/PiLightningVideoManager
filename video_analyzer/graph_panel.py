"""Brightness graph panel for the desktop video analyzer."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from common.candidate_config import CandidateConfig
from video_analyzer.candidate_replay import CandidateReplayResult
from video_analyzer.capture_data import CaptureData


class GraphPanel(QWidget):
    def __init__(
        self,
        capture_data: CaptureData,
        candidate_result: CandidateReplayResult,
        candidate_config: CandidateConfig,
    ) -> None:
        super().__init__()

        self._capture_data = capture_data
        self._candidate_result = candidate_result
        self._candidate_config = candidate_config

        self._replay_trigger_lines: list[pg.InfiniteLine] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        self._create_graphs(layout)

    def set_current_frame(
        self,
        frame_index: int,
    ) -> None:
        for line in self._current_frame_lines:
            line.setValue(frame_index)

    def update_candidate_result(
        self,
        candidate_result: CandidateReplayResult,
        candidate_config: CandidateConfig,
    ) -> None:
        """Update threshold and replay trigger markers after Apply."""

        self._candidate_result = candidate_result
        self._candidate_config = candidate_config

        self._threshold_line.setValue(
            candidate_config.candidate_brightness_delta_threshold
        )

        for line in self._replay_trigger_lines:
            self._brightness_graph.removeItem(line)
            self._delta_graph.removeItem(line)

        self._replay_trigger_lines = []
        self._add_replay_trigger_lines()

    def _create_graphs(
        self,
        layout: QVBoxLayout,
    ) -> None:
        pg.setConfigOptions(
            antialias=True,
        )

        frame_numbers = np.arange(
            self._capture_data.frame_count
        )

        brightness_values = (
            self._capture_data.pi_brightness
            if np.isfinite(
                self._capture_data.pi_brightness
            ).any()
            else self._capture_data.replay_brightness
        )

        delta_values = (
            self._capture_data.pi_brightness_delta
            if np.isfinite(
                self._capture_data.pi_brightness_delta
            ).any()
            else self._capture_data.replay_brightness_delta
        )

        self._brightness_graph = pg.PlotWidget()
        self._brightness_graph.setLabel(
            "left",
            "Absolute brightness",
        )
        self._brightness_graph.showGrid(
            x=True,
            y=True,
            alpha=0.3,
        )
        self._brightness_graph.plot(
            frame_numbers,
            brightness_values,
        )

        self._delta_graph = pg.PlotWidget()
        self._delta_graph.setLabel(
            "left",
            "Brightness change",
        )
        self._delta_graph.setLabel(
            "bottom",
            "Frame number",
        )
        self._delta_graph.showGrid(
            x=True,
            y=True,
            alpha=0.3,
        )
        self._delta_graph.plot(
            frame_numbers,
            delta_values,
        )

        self._threshold_line = pg.InfiniteLine(
            pos=(
                self._candidate_config.
                candidate_brightness_delta_threshold
            ),
            angle=0,
            movable=False,
            pen=pg.mkPen(
                width=1,
                style=Qt.PenStyle.DashLine,
            ),
        )
        self._delta_graph.addItem(
            self._threshold_line
        )

        self._delta_graph.setXLink(
            self._brightness_graph
        )

        self._current_frame_lines = [
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

        self._brightness_graph.addItem(
            self._current_frame_lines[0]
        )
        self._delta_graph.addItem(
            self._current_frame_lines[1]
        )

        self._add_original_trigger_lines()
        self._add_replay_trigger_lines()

        layout.addWidget(
            self._brightness_graph
        )
        layout.addWidget(
            self._delta_graph
        )

    def _add_original_trigger_lines(self) -> None:
        frame_index = (
            self._capture_data.original_trigger_frame_index
        )

        if frame_index is None:
            return

        for graph in [
            self._brightness_graph,
            self._delta_graph,
        ]:
            graph.addItem(
                pg.InfiniteLine(
                    pos=frame_index,
                    angle=90,
                    movable=False,
                    pen=pg.mkPen(
                        width=2,
                        style=Qt.PenStyle.DotLine,
                    ),
                )
            )

    def _add_replay_trigger_lines(self) -> None:
        frame_index = self._candidate_result.frame_index

        if frame_index is None:
            return

        brightness_line = pg.InfiniteLine(
            pos=frame_index,
            angle=90,
            movable=False,
            pen=pg.mkPen(
                width=2,
                style=Qt.PenStyle.DashDotLine,
            ),
        )
        delta_line = pg.InfiniteLine(
            pos=frame_index,
            angle=90,
            movable=False,
            pen=pg.mkPen(
                width=2,
                style=Qt.PenStyle.DashDotLine,
            ),
        )

        self._brightness_graph.addItem(
            brightness_line
        )
        self._delta_graph.addItem(
            delta_line
        )

        self._replay_trigger_lines = [
            brightness_line,
            delta_line,
        ]
