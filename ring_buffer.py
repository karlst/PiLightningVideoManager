"""
@file ring_buffer.py

@brief Thread-safe fixed-capacity ring buffer.
"""

from threading import Lock
from typing import Any


class RingBuffer:
    """
    @brief Thread-safe fixed-capacity ring buffer.

    New items overwrite the oldest items when the buffer is full.
    """

    def __init__(
        self,
        capacity: int
    ) -> None:
        if capacity < 1:
            raise ValueError(
                "RingBuffer capacity must be at least 1"
            )

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
        items: list[Any] = []

        with self._lock:
            ordered_indices = (
                self._get_ordered_indices_locked()
            )

            for iIndex in ordered_indices:
                item = self._items[
                    iIndex
                ]

                if item is not None:
                    items.append(
                        item
                    )

        return items

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
        status = {}

        with self._lock:
            oldest_item = None
            newest_item = None

            ordered_indices = (
                self._get_ordered_indices_locked()
            )

            if len(ordered_indices) > 0:
                oldest_item = self._items[
                    ordered_indices[0]
                ]

                newest_item = self._items[
                    ordered_indices[-1]
                ]

            status = {
                "capacity": self._capacity,
                "count": self._count,
                "total_pushed": self._total_pushed,
                "overwrite_count": self._overwrite_count,
                "next_index": self._next_index,
                "full": self._count == self._capacity,
                "oldest_sequence_number":
                    self._get_sequence_number(
                        oldest_item
                    ),
                "newest_sequence_number":
                    self._get_sequence_number(
                        newest_item
                    )
            }

        return status

    def _get_ordered_indices_locked(self) -> list[int]:
        ordered_indices: list[int] = []

        if self._count < self._capacity:
            ordered_indices = list(
                range(
                    self._count
                )
            )
        else:
            for iOffset in range(
                self._capacity
            ):
                iIndex = (
                    self._next_index + iOffset
                ) % self._capacity

                ordered_indices.append(
                    iIndex
                )

        return ordered_indices

    def _get_sequence_number(
        self,
        item: Any
    ) -> int | None:
        sequence_number = None

        if item is not None and hasattr(
            item,
            "sequence_number"
        ):
            sequence_number = item.sequence_number

        return sequence_number