"""Developer smoke test for common.runtime_telemetry.

Run from the Pi Camera Capture program root:

    python3 -m common.telemetry_test

This test does NOT require the camera, lightning, PSF, S3, or /run permissions.
It creates temporary status files, exercises rolling counters, atomic JSON
replacement, read failure handling, and a fast bucket rollover.

Optional:
    python3 -m common.telemetry_test --show-json

Exit status is 0 on success, 1 on failure.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from common.runtime_telemetry import (
    RollingEventCounts,
    atomic_write_json,
    read_json_status,
    utc_now_text,
)


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _pretty(payload: dict) -> str:
    return json.dumps(payload, indent=2)


def test_capture_counts(show_json: bool) -> None:
    counts = RollingEventCounts(
        (
            "candidates",
            "captures",
            "automatic_captures",
            "manual_captures",
        ),
        bucket_seconds=300,
        window_hours=24,
    )

    counts.increment("candidates", 12)
    counts.increment("captures", 4)
    counts.increment("automatic_captures", 3)
    counts.increment("manual_captures", 1)

    snap = counts.snapshot()
    totals = snap["totals"]

    _check(totals["candidates"] == 12, "candidate count mismatch")
    _check(totals["captures"] == 4, "capture count mismatch")
    _check(totals["automatic_captures"] == 3, "automatic count mismatch")
    _check(totals["manual_captures"] == 1, "manual count mismatch")
    _check(snap["bucket_seconds"] == 300, "wrong bucket size")
    _check(snap["window_hours"] == 24, "wrong window")

    print("PASS  capture counters")
    if show_json:
        print(_pretty(snap))


def test_psf_counts(show_json: bool) -> None:
    counts = RollingEventCounts(
        ("flash", "anomaly", "s3_success", "s3_failure"),
        bucket_seconds=300,
        window_hours=24,
    )

    counts.increment("flash", 2)
    counts.increment("anomaly", 7)
    counts.increment("s3_success", 8)
    counts.increment("s3_failure", 1)

    snap = counts.snapshot()
    totals = snap["totals"]

    _check(totals["flash"] == 2, "FLASH count mismatch")
    _check(totals["anomaly"] == 7, "ANOMALY count mismatch")
    _check(totals["s3_success"] == 8, "S3 success count mismatch")
    _check(totals["s3_failure"] == 1, "S3 failure count mismatch")

    print("PASS  PSF counters")
    if show_json:
        print(_pretty(snap))


def test_atomic_status_files(show_json: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="picam-telemetry-test-") as temp:
        root = Path(temp)
        capture_path = root / "capture_status.json"
        psf_path = root / "psf_status.json"

        capture_counts = RollingEventCounts(
            (
                "candidates",
                "captures",
                "automatic_captures",
                "manual_captures",
            ),
            bucket_seconds=300,
            window_hours=24,
        )
        capture_counts.increment("candidates", 20)
        capture_counts.increment("captures", 5)
        capture_counts.increment("automatic_captures", 4)
        capture_counts.increment("manual_captures", 1)

        capture_payload = {
            "schema_version": 1,
            "component": "picam",
            "heartbeat_utc": utc_now_text(),
            **capture_counts.snapshot(),
        }
        atomic_write_json(capture_path, capture_payload)

        psf_counts = RollingEventCounts(
            ("flash", "anomaly", "s3_success", "s3_failure"),
            bucket_seconds=300,
            window_hours=24,
        )
        psf_counts.increment("flash", 2)
        psf_counts.increment("anomaly", 3)
        psf_counts.increment("s3_success", 5)

        psf_payload = {
            "schema_version": 1,
            "component": "psf",
            "heartbeat_utc": utc_now_text(),
            "ap_active": False,
            "configured_upload_to_s3": True,
            "effective_upload_to_s3": True,
            "last_classification_utc": utc_now_text(),
            "last_upload_utc": utc_now_text(),
            "last_pass_utc": utc_now_text(),
            "last_error": "",
            **psf_counts.snapshot(),
        }
        atomic_write_json(psf_path, psf_payload)

        capture_read, capture_error = read_json_status(capture_path)
        psf_read, psf_error = read_json_status(psf_path)

        _check(capture_error is None, f"capture read failed: {capture_error}")
        _check(psf_error is None, f"PSF read failed: {psf_error}")
        _check(capture_read == capture_payload, "capture payload changed on read")
        _check(psf_read == psf_payload, "PSF payload changed on read")

        # Replace the same destination again to exercise atomic replacement.
        capture_counts.increment("candidates", 3)
        second_payload = {
            "schema_version": 1,
            "component": "picam",
            "heartbeat_utc": utc_now_text(),
            **capture_counts.snapshot(),
        }
        atomic_write_json(capture_path, second_payload)

        second_read, second_error = read_json_status(capture_path)
        _check(second_error is None, f"second read failed: {second_error}")
        _check(
            second_read["totals"]["candidates"] == 23,
            "atomic replacement did not publish updated value",
        )

        print("PASS  atomic status write/read/replace")
        if show_json:
            print("Synthetic capture_status.json:")
            print(_pretty(second_read))
            print("Synthetic psf_status.json:")
            print(_pretty(psf_read))


def test_read_failures() -> None:
    with tempfile.TemporaryDirectory(prefix="picam-telemetry-test-") as temp:
        root = Path(temp)

        missing_payload, missing_error = read_json_status(root / "missing.json")
        _check(missing_payload is None, "missing file unexpectedly returned data")
        _check(bool(missing_error), "missing file did not return an error reason")

        bad_path = root / "bad.json"
        bad_path.write_text("{this is not json", encoding="utf-8")
        bad_payload, bad_error = read_json_status(bad_path)
        _check(bad_payload is None, "malformed JSON unexpectedly returned data")
        _check(bool(bad_error), "malformed JSON did not return an error reason")

        array_path = root / "array.json"
        array_path.write_text("[1, 2, 3]\n", encoding="utf-8")
        array_payload, array_error = read_json_status(array_path)
        _check(array_payload is None, "non-object JSON unexpectedly returned data")
        _check(bool(array_error), "non-object JSON did not return an error reason")

    print("PASS  missing/malformed status handling")


def test_fast_bucket_rollover(show_json: bool) -> None:
    # Two-second buckets let us prove rollover without waiting five minutes.
    counts = RollingEventCounts(
        ("events",),
        bucket_seconds=2,
        window_hours=1,
    )

    counts.increment("events", 1)
    first = counts.snapshot()
    first_bucket = first["buckets"][-1]["start_utc"]

    deadline = time.monotonic() + 3.2
    while time.monotonic() < deadline:
        time.sleep(0.1)
        current = counts.snapshot()
        if current["buckets"][-1]["start_utc"] != first_bucket:
            break
    else:
        raise AssertionError("bucket did not roll over within expected time")

    counts.increment("events", 2)
    snap = counts.snapshot()

    _check(snap["totals"]["events"] == 3, "rollover lost event counts")
    _check(len(snap["buckets"]) >= 2, "rollover did not create another bucket")
    _check(snap["buckets"][-1]["events"] == 2, "new bucket count mismatch")

    print("PASS  fast bucket rollover")
    if show_json:
        print(_pretty(snap))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test Pi Camera Capture runtime telemetry."
    )
    parser.add_argument(
        "--show-json",
        action="store_true",
        help="Print the synthetic telemetry snapshots.",
    )
    args = parser.parse_args()

    print("Pi Camera Capture telemetry smoke test")
    print("--------------------------------------")

    try:
        test_capture_counts(args.show_json)
        test_psf_counts(args.show_json)
        test_atomic_status_files(args.show_json)
        test_read_failures()
        test_fast_bucket_rollover(args.show_json)
    except Exception as exc:
        print(f"FAIL  {exc}")
        return 1

    print("--------------------------------------")
    print("ALL TELEMETRY TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
