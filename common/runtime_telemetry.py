"""Lightweight volatile runtime telemetry for Pi Camera Capture services.

Telemetry is intentionally session-only.  Each service owns its own status file
under /run and publishes atomic JSON snapshots.  No log parsing, directory scans,
or persistent reconstruction is performed.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from typing import Iterable


DEFAULT_BUCKET_SECONDS = 5 * 60
DEFAULT_WINDOW_HOURS = 24


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RollingEventCounts:
    """Thread-safe rolling event counters keyed by fixed UTC time buckets."""

    def __init__(
        self,
        fields: Iterable[str],
        *,
        bucket_seconds: int = DEFAULT_BUCKET_SECONDS,
        window_hours: int = DEFAULT_WINDOW_HOURS,
    ) -> None:
        fields = tuple(str(field) for field in fields)
        if not fields:
            raise ValueError("At least one telemetry field is required")
        if bucket_seconds <= 0:
            raise ValueError("bucket_seconds must be positive")
        if window_hours <= 0:
            raise ValueError("window_hours must be positive")

        self._fields = fields
        self._bucket_seconds = int(bucket_seconds)
        self._max_buckets = max(
            1,
            int(window_hours * 3600 / self._bucket_seconds),
        )
        self._window_hours = int(window_hours)
        self._lock = Lock()
        self._buckets: deque[dict] = deque()
        started_now = datetime.now(timezone.utc)
        self._started_utc = started_now.isoformat(timespec="seconds")
        self._started_bucket_epoch = (
            int(started_now.timestamp()) // self._bucket_seconds
        ) * self._bucket_seconds

    @property
    def started_utc(self) -> str:
        return self._started_utc

    def increment(self, field: str, amount: int = 1) -> None:
        if field not in self._fields:
            raise KeyError(field)
        if amount == 0:
            return

        now_epoch = int(datetime.now(timezone.utc).timestamp())
        bucket_start_epoch = (
            now_epoch // self._bucket_seconds
        ) * self._bucket_seconds

        with self._lock:
            if (
                not self._buckets
                or self._buckets[-1]["start_epoch"] != bucket_start_epoch
            ):
                self._buckets.append(
                    {
                        "start_epoch": bucket_start_epoch,
                        **{name: 0 for name in self._fields},
                    }
                )
                cutoff_epoch = (
                    bucket_start_epoch
                    - (self._max_buckets - 1) * self._bucket_seconds
                )
                while (
                    self._buckets
                    and self._buckets[0]["start_epoch"] < cutoff_epoch
                ):
                    self._buckets.popleft()

            self._buckets[-1][field] += int(amount)

    def snapshot(self) -> dict:
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        current_bucket_epoch = (
            now_epoch // self._bucket_seconds
        ) * self._bucket_seconds
        first_bucket_epoch = max(
            self._started_bucket_epoch,
            current_bucket_epoch
            - (self._max_buckets - 1) * self._bucket_seconds,
        )

        with self._lock:
            values_by_start = {
                int(bucket["start_epoch"]): dict(bucket)
                for bucket in self._buckets
                if int(bucket["start_epoch"]) >= first_bucket_epoch
            }

        totals = {field: 0 for field in self._fields}
        serialized = []
        start_epoch = first_bucket_epoch
        while start_epoch <= current_bucket_epoch:
            bucket = values_by_start.get(
                start_epoch,
                {
                    "start_epoch": start_epoch,
                    **{field: 0 for field in self._fields},
                },
            )
            bucket.pop("start_epoch", None)
            for field in self._fields:
                totals[field] += int(bucket.get(field, 0))
            serialized.append(
                {
                    "start_utc": datetime.fromtimestamp(
                        start_epoch,
                        tz=timezone.utc,
                    ).isoformat(timespec="seconds"),
                    **bucket,
                }
            )
            start_epoch += self._bucket_seconds

        return {
            "started_utc": self._started_utc,
            "bucket_seconds": self._bucket_seconds,
            "window_hours": self._window_hours,
            "totals": totals,
            "buckets": serialized,
        }


def atomic_write_json(path: str | Path, payload: dict) -> None:
    """Atomically replace one JSON status file.

    The temp file is unique to the process and write call.  The caller owns the
    destination file; no inter-process lock is required for readers.
    """
    destination = Path(path)
    temp_path = destination.with_name(
        f".{destination.name}.tmp.{os.getpid()}.{id(payload)}"
    )

    encoded = json.dumps(payload, separators=(",", ":")) + "\n"
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def read_json_status(path: str | Path) -> tuple[dict | None, str | None]:
    """Read an optional runtime status file without raising to callers."""
    status_path = Path(path)
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None, "status JSON is not an object"
        return data, None
    except FileNotFoundError:
        return None, "status file unavailable"
    except (OSError, json.JSONDecodeError) as error:
        return None, str(error)
