"""
@file metric_history.py

@brief Thread-safe metric history buffer.
"""

from ring_buffer import RingBuffer


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