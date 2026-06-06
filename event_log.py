from collections import deque
from datetime import datetime
from datetime import timezone
from threading import Lock


class EventLog:
    """
    Thread-safe in-memory event log.
    """

    def __init__(self, max_entries: int = 200) -> None:
        self._max_entries = max_entries
        self._entries = deque(
            maxlen=max_entries
        )
        self._lock = Lock()
        self._next_id = 1

    def add(
        self,
        message: str,
        level: str = "info"
    ) -> None:
        timestamp = datetime.now(
            timezone.utc
        ).strftime(
            "%H:%M:%S"
        )

        with self._lock:
            entry = {
                "id": self._next_id,
                "timestamp": timestamp,
                "level": level,
                "message": message
            }

            self._entries.append(
                entry
            )

            self._next_id += 1

    def snapshot(self) -> list[dict]:
        entries = []

        with self._lock:
            entries = list(
                self._entries
            )

        return entries

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()