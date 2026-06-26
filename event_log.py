"""
@file event_log.py

@brief Thread-safe in-memory event log with background file writer.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from queue import Queue
from threading import Lock
from threading import Thread
import json

from cam_config import CamConfig


class EventLog:
    # ## Initialize in-memory event history and background file writer.
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

    # ## Add an event with full text and optional display summary.
    def add(
        self,
        message,
        severity="info",
        event_type="general",
        summary=None
    ) -> None:
        try:
            message_text = str(
                message
            )

            summary_text = str(
                summary
            ) if summary is not None else self._shorten_summary(
                message_text
            )

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

                "event_type":
                    str(
                        event_type
                    ),

                "summary":
                    summary_text,

                "message":
                    message_text
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

    # ## Return a copy of the current in-memory event list.
    def snapshot(
        self
    ) -> list[dict]:
        with self._lock:
            entries = list(
                self._entries
            )

        return entries

    # ## Clear the in-memory event list and persisted event file.
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

    # ## Load persisted event entries from the JSONL event file.
    def _load_from_file(
        self
    ) -> None:
        path = self._config.event_log_file

        if not path.exists():
            path.touch(
                exist_ok=True
            )

        else:
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
                                self._normalize_entry(
                                    json.loads(
                                        line
                                    )
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

    # ## Keep old event records compatible with the new structured format.
    def _normalize_entry(
        self,
        entry: dict
    ) -> dict:
        message = str(
            entry.get(
                "message",
                ""
            )
        )

        normalized = {
            "timestamp_utc": entry.get(
                "timestamp_utc",
                entry.get(
                    "timestamp",
                    ""
                )
            ),
            "severity": str(
                entry.get(
                    "severity",
                    entry.get(
                        "level",
                        "info"
                    )
                )
            ),
            "event_type": str(
                entry.get(
                    "event_type",
                    "general"
                )
            ),
            "summary": str(
                entry.get(
                    "summary",
                    message
                )
            ),
            "message": message
        }

        return normalized

    # ## Shorten fallback summaries without parsing event text.
    def _shorten_summary(
        self,
        message_text: str
    ) -> str:
        summary = message_text

        if len(summary) > 100:
            summary = (
                summary[:97] +
                "..."
            )

        return summary

    # ## Write queued events to disk on the background writer thread.
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

    # ## Append one normalized event entry to the JSONL event file.
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

    # ## Rewrite the persisted file from the current in-memory event list.
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

    # ## Keep only the configured number of recent entries in memory.
    def _trim_locked(
        self
    ) -> None:
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[
                -self._max_entries:
            ]
