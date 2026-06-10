"""
@file event_log.py

@brief Thread-safe in-memory event log with background file writer.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
from queue import Empty
from queue import Queue
from threading import Lock
from threading import Thread
import json

from cam_config import CamConfig


class EventLog:
    def __init__(
        self,
        config: CamConfig
    ) -> None:
        self._config = config
        self._max_entries = int(
            config.event_log_max_entries
        )

        self._entries: list[dict] = []
        self._lock = Lock()

        self._write_queue: Queue[dict | None] = Queue()

        self._config.ensure_directories()

        self._load_from_file()

        self._writer_thread = Thread(
            target=self._writer_loop,
            name="EventLogWriter",
            daemon=True
        )

        self._writer_thread.start()

    def add(
        self,
        message,
        severity="info"
    ) -> None:
        try:
            entry = {
                "timestamp_utc":
                    datetime.now(
                        timezone.utc
                    ).isoformat(
                        timespec="seconds"
                    ),

                "severity":
                    str(
                        severity
                    ),

                "message":
                    str(
                        message
                    )
            }

            with self._lock:
                self._entries.append(
                    entry
                )

                self._trim_locked()

            self._write_queue.put_nowait(
                entry
            )

        except Exception as error:
            print(
                f"EventLog failure: {error}",
                flush=True
            )

    def snapshot(
        self
    ) -> list[dict]:
        with self._lock:
            return list(
                self._entries
            )

    def clear(
        self
    ) -> None:
        with self._lock:
            self._entries.clear()

        try:
            self._config.event_log_file.write_text(
                "",
                encoding="utf-8"
            )

        except Exception as error:
            print(
                f"EventLog clear file failure: {error}",
                flush=True
            )

    def _load_from_file(
        self
    ) -> None:
        path = self._config.event_log_file

        if not path.exists():
            path.touch(
                exist_ok=True
            )

            return

        entries: list[dict] = []

        try:
            with path.open(
                "r",
                encoding="utf-8"
            ) as file:
                for line in file:
                    line = line.strip()

                    if line:
                        entries.append(
                            json.loads(
                                line
                            )
                        )

            with self._lock:
                self._entries = entries[
                    -self._max_entries:
                ]

            self._rewrite_file_from_memory()

        except Exception as error:
            print(
                f"EventLog load failure: {error}",
                flush=True
            )

    def _writer_loop(
        self
    ) -> None:
        while True:
            try:
                entry = self._write_queue.get()

                if entry is None:
                    return

                self._append_entry_to_file(
                    entry
                )

                self._write_queue.task_done()

            except Exception as error:
                print(
                    f"EventLog writer failure: {error}",
                    flush=True
                )

    def _append_entry_to_file(
        self,
        entry: dict
    ) -> None:
        with self._config.event_log_file.open(
            "a",
            encoding="utf-8"
        ) as file:
            file.write(
                json.dumps(
                    entry
                ) + "\n"
            )

    def _rewrite_file_from_memory(
        self
    ) -> None:
        try:
            with self._lock:
                entries = list(
                    self._entries
                )

            with self._config.event_log_file.open(
                "w",
                encoding="utf-8"
            ) as file:
                for entry in entries:
                    file.write(
                        json.dumps(
                            entry
                        ) + "\n"
                    )

        except Exception as error:
            print(
                f"EventLog rewrite failure: {error}",
                flush=True
            )

    def _trim_locked(
        self
    ) -> None:
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[
                -self._max_entries:
            ]