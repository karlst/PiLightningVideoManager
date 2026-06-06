"""
@file ring_buffer.py

@brief Thread-safe circular buffer for camera frames.
"""

from threading import Lock
from typing import Any


class RingBuffer:
    """
    @brief Fixed-capacity thread-safe circular buffer.
    """

    def __init__(
        self,
        capacity: int
    ) -> None:
        self._capacity = capacity
        self._items: list[Any | None] = [
            None
        ] * capacity
        self._next_index = 0
        self._count = 0
        self._total_pushed = 0
        self._overwrite_count = 0
        self._lock = Lock()

    def push(
        self,
        item: Any
    ) -> None:
        with self._lock:
            if self._count == self._capacity:
                self._overwrite_count += 1
            else:
                self._count += 1

            self._items[self._next_index] = item

            self._next_index = (
                self._next_index + 1
            ) % self._capacity

            self._total_pushed += 1

    def snapshot(self) -> list[Any]:
        with self._lock:
            result = []

            if self._count < self._capacity:
                for iIndex in range(
                    self._count
                ):
                    item = self._items[iIndex]

                    if item is not None:
                        result.append(
                            item
                        )
            else:
                for iOffset in range(
                    self._capacity
                ):
                    iIndex = (
                        self._next_index + iOffset
                    ) % self._capacity

                    item = self._items[iIndex]

                    if item is not None:
                        result.append(
                            item
                        )

        return result

    def clear(self) -> None:
        with self._lock:
            self._items = [
                None
            ] * self._capacity
            self._next_index = 0
            self._count = 0
            self._total_pushed = 0
            self._overwrite_count = 0

    def get_status(self) -> dict:
        with self._lock:
            status = {
                "capacity": self._capacity,
                "count": self._count,
                "total_pushed": self._total_pushed,
                "overwrite_count": self._overwrite_count
            }

        return status