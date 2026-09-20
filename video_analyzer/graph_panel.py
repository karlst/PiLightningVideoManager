"""
Qt/pyqtgraph panel that visualizes brightness data for one capture.

GraphPanel draws absolute brightness and adjacent-frame brightness change
against actual elapsed capture time in milliseconds. When Pi sidecar
measurements are available they are preferred; reconstructed MP4 measurements
are used as a fallback.

The x-axis uses each frame's recorded offset_ms, so irregular frame spacing is
visible rather than being hidden by evenly spaced frame numbers.

The graphs also show reference markers: the Candidate brightness-delta
threshold, the currently displayed frame, the original trigger recorded by the
Pi, and the trigger produced by replaying CandidateFinder with the current
experimental settings.
"""


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
        self._elapsed_ms = self._build_elapsed_ms()

        self._replay_trigger_lines: list[pg.InfiniteLine] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        self._create_graphs(layout)

    def set_current_frame(
        self,
        frame_index: int,
    ) -> None:
        elapsed_ms = self._elapsed_ms_for_frame(frame_index)

        for line in self._current_frame_lines:
            line.setValue(elapsed_ms)

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

    def _build_elapsed_ms(self) -> np.ndarray:
        """Return one elapsed-time value in ms for every decoded frame."""
        frame_count = self._capture_data.frame_count
        elapsed_ms = np.full(frame_count, np.nan, dtype=float)

        for frame_index in range(frame_count):
            record = self._capture_data.frame_records.get(
                frame_index,
                {},
            )

            try:
                offset_ms = float(record.get("offset_ms"))
            except (TypeError, ValueError):
                continue

            if np.isfinite(offset_ms):
                elapsed_ms[frame_index] = offset_ms

        valid = np.isfinite(elapsed_ms)
        if valid.any():
            if not valid.all():
                valid_indices = np.flatnonzero(valid)
                elapsed_ms = np.interp(
                    np.arange(frame_count, dtype=float),
                    valid_indices.astype(float),
                    elapsed_ms[valid_indices],
                )

            return elapsed_ms

        # Legacy fallback for captures without Pi offset_ms records. Encoded
        # presentation timestamps keep the graph in millisecond units.
        ffprobe_ms = np.full(frame_count, np.nan, dtype=float)

        for frame_index, info in enumerate(
            self._capture_data.frame_info[:frame_count]
        ):
            try:
                timestamp_ms = (
                    float(info.get("best_effort_timestamp_time")) *
                    1000.0
                )
            except (TypeError, ValueError):
                continue

            if np.isfinite(timestamp_ms):
                ffprobe_ms[frame_index] = timestamp_ms

        valid = np.isfinite(ffprobe_ms)
        if valid.any():
            valid_indices = np.flatnonzero(valid)
            ffprobe_ms[valid] -= ffprobe_ms[valid_indices[0]]

            if not valid.all():
                ffprobe_ms = np.interp(
                    np.arange(frame_count, dtype=float),
                    valid_indices.astype(float),
                    ffprobe_ms[valid_indices],
                )

            return ffprobe_ms

        # Last-resort compatibility for captures with no timing metadata.
        return np.arange(frame_count, dtype=float)

    def _elapsed_ms_for_frame(
        self,
        frame_index: int,
    ) -> float:
        if self._elapsed_ms.size == 0:
            return 0.0

        frame_index = max(
            0,
            min(
                int(frame_index),
                self._elapsed_ms.size - 1,
            ),
        )

        return float(self._elapsed_ms[frame_index])

    def _create_graphs(
        self,
        layout: QVBoxLayout,
    ) -> None:
        pg.setConfigOptions(
            antialias=True,
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
            self._elapsed_ms,
            brightness_values,
        )

        self._delta_graph = pg.PlotWidget()
        self._delta_graph.setLabel(
            "left",
            "Brightness change",
        )
        self._delta_graph.setLabel(
            "bottom",
            "Elapsed time (ms)",
        )

        # Keep elapsed-time ticks in actual milliseconds.  Passing units="ms"
        # lets pyqtgraph apply SI prefixes automatically, which turns a 0-2500
        # ms range into 0-2.5 with the misleading label "kms".
        self._brightness_graph.getAxis(
            "bottom"
        ).enableAutoSIPrefix(False)
        self._delta_graph.getAxis(
            "bottom"
        ).enableAutoSIPrefix(False)
        self._delta_graph.showGrid(
            x=True,
            y=True,
            alpha=0.3,
        )
        self._delta_graph.plot(
            self._elapsed_ms,
            delta_values,
        )

        # Scale the brightness-change Y axis from the actual finite delta
        # values only. Reference lines such as the Candidate threshold must
        # not force the graph to a much larger range and flatten the data.
        finite_delta_values = delta_values[
            np.isfinite(
                delta_values
            )
        ]

        if finite_delta_values.size > 0:
            delta_min = float(
                np.min(
                    finite_delta_values
                )
            )

            delta_max = float(
                np.max(
                    finite_delta_values
                )
            )

            delta_span = (
                delta_max -
                delta_min
            )

            if delta_span > 0.0:
                # Leave enough headroom for pyqtgraph to draw the outer
                # major tick labels cleanly. Five percent was too tight for
                # clips whose extrema landed just inside a round tick such
                # as +50, causing that label to be clipped at the plot edge.
                padding = (
                    delta_span *
                    0.10
                )
            else:
                # Keep a useful visible range for a perfectly flat clip.
                padding = max(
                    abs(
                        delta_min
                    ) *
                    0.10,
                    0.01,
                )

            self._delta_graph.setYRange(
                delta_min - padding,
                delta_max + padding,
                padding=0.0,
            )

            self._delta_graph.enableAutoRange(
                axis="y",
                enable=False,
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

        first_elapsed_ms = self._elapsed_ms_for_frame(0)

        self._current_frame_lines = [
            pg.InfiniteLine(
                pos=first_elapsed_ms,
                angle=90,
                movable=False,
                pen=pg.mkPen(
                    width=2,
                    style=Qt.PenStyle.DashLine,
                ),
            ),
            pg.InfiniteLine(
                pos=first_elapsed_ms,
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
                    pos=self._elapsed_ms_for_frame(frame_index),
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

        elapsed_ms = self._elapsed_ms_for_frame(frame_index)

        brightness_line = pg.InfiniteLine(
            pos=elapsed_ms,
            angle=90,
            movable=False,
            pen=pg.mkPen(
                width=2,
                style=Qt.PenStyle.DashDotLine,
            ),
        )
        delta_line = pg.InfiniteLine(
            pos=elapsed_ms,
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
