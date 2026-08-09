"""
@file metric_history.py

@brief Stores the recent sampled frame-analysis metrics used by the web UI.

MetricHistory is a small wrapper around RingBuffer. FrameAnalyzer produces
metric dictionaries such as brightness and motion measurements, and
BufferManager periodically places those dictionaries here. The web application
can then request a chronological snapshot to draw recent metric-history graphs.

Unlike the main camera RingBuffer, this object stores analysis dictionaries
rather than video frames. It delegates the fixed-capacity, overwrite-oldest,
thread-safe behavior to RingBuffer instead of implementing that logic twice.
"""

from video_capture.ring_buffer import RingBuffer


class MetricHistory:
    """
    @brief Stores recent frame-analysis metric dictionaries.
    """

    def __init__(
        self,
        capacity: int
    ) -> None:
        self._buffer = RingBuffer(
            capacity=capacity
        )

    def push(
        self,
        metric: dict
    ) -> None:
        self._buffer.push(
            metric
        )

    def snapshot(self) -> list[dict]:
        return self._buffer.snapshot()

    def clear(self) -> None:
        self._buffer.clear()

    def get_status(self) -> dict:
        return self._buffer.get_status()