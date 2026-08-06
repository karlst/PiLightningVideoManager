"""
@file moving_average.py

@brief Fixed-window moving average helper.
"""

from collections import deque


class MovingAverage:
    """
    @brief Maintains a fixed-window moving average.
    """

    def __init__(
        self,
        window_size: int
    ) -> None:
        if window_size < 1:
            raise ValueError(
                "MovingAverage window_size must be at least 1"
            )

        self._window_size = window_size
        self._values = deque(
            maxlen=window_size
        )
        self._total = 0.0

    def push(
        self,
        value: float
    ) -> float:
        if len(
            self._values
        ) == self._window_size:
            self._total -= self._values[0]

        self._values.append(
            value
        )

        self._total += value

        return self.average()

    def average(self) -> float:
        result = 0.0

        if len(
            self._values
        ) > 0:
            result = self._total / len(
                self._values
            )

        return result

    def count(self) -> int:
        return len(
            self._values
        )

    def clear(self) -> None:
        self._values.clear()
        self._total = 0.0