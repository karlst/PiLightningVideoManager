"""
@file metric_history.py

@brief Multi-resolution history for PLCC brightness/FPS graphs.

The camera pipeline produces one graph metric sample per second.  Keeping all
86,400 one-second samples for a full day is unnecessary for the longer PLCC
windows, so MetricHistory keeps three in-memory resolutions:

    recent: 1-second samples, 1 hour
    medium: 10-second averages, 6 hours
    long:   60-second averages, 24 hours

This gives the 1-minute / 5-minute / 1-hour views full short-term detail while
keeping the 6-hour and 24-hour histories compact.  All state is volatile and is
reset when the capture application restarts.
"""

from threading import Lock

from video_capture.ring_buffer import RingBuffer


class MetricHistory:
    """Stores recent metric dictionaries at several time resolutions."""

    def __init__(
        self,
        recent_capacity: int,
        medium_capacity: int,
        long_capacity: int,
        medium_bucket_seconds: float = 10.0,
        long_bucket_seconds: float = 60.0,
    ) -> None:
        self._recent = RingBuffer(capacity=recent_capacity)
        self._medium = RingBuffer(capacity=medium_capacity)
        self._long = RingBuffer(capacity=long_capacity)

        self._medium_bucket_seconds = float(medium_bucket_seconds)
        self._long_bucket_seconds = float(long_bucket_seconds)

        self._lock = Lock()
        self._medium_accumulator = None
        self._long_accumulator = None

    def push(self, metric: dict) -> None:
        """Add one one-second metric sample and update coarse histories."""
        sample = dict(metric)

        with self._lock:
            self._recent.push(sample)
            self._medium_accumulator = self._accumulate(
                self._medium,
                self._medium_accumulator,
                sample,
                self._medium_bucket_seconds,
            )
            self._long_accumulator = self._accumulate(
                self._long,
                self._long_accumulator,
                sample,
                self._long_bucket_seconds,
            )

    def snapshot(self, window_seconds: float | None = None) -> list[dict]:
        """Return chronological samples at a resolution suited to the window."""
        with self._lock:
            if window_seconds is None or window_seconds <= 3600.0:
                samples = self._recent.snapshot()
            elif window_seconds <= 21600.0:
                samples = self._medium.snapshot()
                partial = self._partial_sample(self._medium_accumulator)
                if partial is not None:
                    samples.append(partial)
            else:
                samples = self._long.snapshot()
                partial = self._partial_sample(self._long_accumulator)
                if partial is not None:
                    samples.append(partial)

        if not samples or window_seconds is None:
            return samples

        newest = float(samples[-1].get("timestamp_monotonic", 0.0) or 0.0)
        minimum = newest - float(window_seconds)

        return [
            sample for sample in samples
            if float(sample.get("timestamp_monotonic", 0.0) or 0.0) >= minimum
        ]

    def latest(self) -> dict | None:
        """Return the newest one-second sample, if any."""
        with self._lock:
            samples = self._recent.snapshot()

        if not samples:
            return None

        return dict(samples[-1])

    def clear(self) -> None:
        with self._lock:
            self._recent.clear()
            self._medium.clear()
            self._long.clear()
            self._medium_accumulator = None
            self._long_accumulator = None

    def get_status(self) -> dict:
        """Return compact status while preserving legacy count/capacity keys."""
        with self._lock:
            recent = self._recent.get_status()
            medium = self._medium.get_status()
            long = self._long.get_status()

        return {
            "capacity": recent["capacity"],
            "count": recent["count"],
            "overwrite_count": recent["overwrite_count"],
            "recent": recent,
            "medium": medium,
            "long": long,
        }

    def _accumulate(
        self,
        target: RingBuffer,
        accumulator: dict | None,
        sample: dict,
        bucket_seconds: float,
    ) -> dict:
        timestamp = float(sample.get("timestamp_monotonic", 0.0) or 0.0)

        if accumulator is None:
            accumulator = self._new_accumulator(sample)
            return accumulator

        start = float(accumulator["start_timestamp_monotonic"])

        if timestamp - start >= bucket_seconds:
            target.push(self._finalize_accumulator(accumulator))
            accumulator = self._new_accumulator(sample)
        else:
            self._add_to_accumulator(accumulator, sample)

        return accumulator

    @staticmethod
    def _new_accumulator(sample: dict) -> dict:
        accumulator = {
            "start_timestamp_monotonic": float(
                sample.get("timestamp_monotonic", 0.0) or 0.0
            ),
            "count": 0,
            "numeric_sums": {},
            "latest": {},
        }
        MetricHistory._add_to_accumulator(accumulator, sample)
        return accumulator

    @staticmethod
    def _add_to_accumulator(accumulator: dict, sample: dict) -> None:
        accumulator["count"] += 1
        accumulator["latest"] = dict(sample)

        for key, value in sample.items():
            if isinstance(value, bool):
                continue

            if isinstance(value, (int, float)):
                accumulator["numeric_sums"][key] = (
                    accumulator["numeric_sums"].get(key, 0.0) + float(value)
                )

    @staticmethod
    def _finalize_accumulator(accumulator: dict) -> dict:
        count = max(1, int(accumulator["count"]))
        result = dict(accumulator["latest"])

        for key, total in accumulator["numeric_sums"].items():
            result[key] = total / count

        # Keep sequence number meaningful as the newest sample rather than an
        # averaged fractional sequence value.
        latest = accumulator["latest"]
        if "sequence_number" in latest:
            result["sequence_number"] = latest["sequence_number"]

        # Position coarse samples at the newest actual sample time in bucket.
        if "timestamp_monotonic" in latest:
            result["timestamp_monotonic"] = latest["timestamp_monotonic"]
        if "timestamp_utc" in latest:
            result["timestamp_utc"] = latest["timestamp_utc"]

        return result

    @staticmethod
    def _partial_sample(accumulator: dict | None) -> dict | None:
        if accumulator is None or int(accumulator.get("count", 0)) <= 0:
            return None
        return MetricHistory._finalize_accumulator(accumulator)
