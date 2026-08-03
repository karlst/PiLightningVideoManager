"""Brightness graph panel for the desktop video analyzer."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from common.candidate_config import CANDIDATE_CONFIG
from video_analyzer.candidate_replay import CandidateReplayResult
from video_analyzer.capture_data import CaptureData


class GraphPanel(QWidget):
    def __init__(
        self,
        capture_data: CaptureData,
        candidate_result: CandidateReplayResult,
    ) -> None:
        super().__init__()

        self._capture_data = capture_data
        self._candidate_result = candidate_result

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
        self._brightness_graph.addLegend()

        self._brightness_graph.plot(
            frame_numbers,
            self._capture_data.replay_brightness,
            name="Replay MP4",
        )

        if np.isfinite(
            self._capture_data.pi_brightness
        ).any():
            self._brightness_graph.plot(
                frame_numbers,
                self._capture_data.pi_brightness,
                name="Original Pi",
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
        self._delta_graph.addLegend()

        self._delta_graph.plot(
            frame_numbers,
            self._capture_data.replay_brightness_delta,
            name="Replay MP4",
        )

        if np.isfinite(
            self._capture_data.pi_brightness_delta
        ).any():
            self._delta_graph.plot(
                frame_numbers,
                self._capture_data.pi_brightness_delta,
                name="Original Pi",
            )

        self._delta_graph.addItem(
            pg.InfiniteLine(
                pos=(
                    CANDIDATE_CONFIG.
                    candidate_brightness_delta_threshold
                ),
                angle=0,
                movable=False,
                pen=pg.mkPen(
                    width=1,
                    style=Qt.PenStyle.DashLine,
                ),
            )
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
        self._add_replay_candidate_lines()

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

    def _add_replay_candidate_lines(self) -> None:
        frame_index = self._candidate_result.frame_index

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
                        style=Qt.PenStyle.DashDotLine,
                    ),
                )
            )
