"""Canonical S3 key construction for Pi Camera capture pairs."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import PurePosixPath
from typing import Any

from common.capture_sidecar import normalize_sidecar


def _brightness_bucket(prefix: str, value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid brightness summary value: {value!r}") from error

    number = max(0.0, number)
    bucket = min(999, int(math.floor(number + 0.5)))
    return f"{prefix}{bucket:03d}"



def canonical_capture_base_key(
    sidecar: dict[str, Any],
    fallback_stem: str | None = None,
) -> str:
    """Derive the canonical S3 base key from current V7 sidecar metadata.

    Unverified:
        unverified/<H-M-L classification>/dXXX/bXXX/<site>/<filename-base>

    Verified:
        verified/<classification>/<type>/dXXX/bXXX/<site>/<filename-base>

    The returned key has no extension.
    """
    normalized, _changed = normalize_sidecar(
        sidecar
    )

    camera = normalized.get(
        "camera",
        {},
    )

    site = ""

    if isinstance(
        camera,
        dict,
    ):
        site = str(
            camera.get(
                "site_name",
                "",
            ) or ""
        ).strip()

    site = _safe_segment(
        site or "Unknown"
    )

    capture = normalized[
        "capture"
    ]

    stem = _capture_filename_stem(
        normalized,
        fallback_stem,
    )

    delta_bucket = _brightness_bucket(
        "d",
        capture.get("max_brightness_delta"),
    )
    brightness_bucket = _brightness_bucket(
        "b",
        capture.get("mean_brightness"),
    )

    if not capture[
        "verified"
    ]:
        classification = _safe_segment(
            str(
                capture[
                    "classification"
                ]
            )
        )

        return (
            f"unverified/{classification}/"
            f"{delta_bucket}/{brightness_bucket}/{site}/{stem}"
        )

    classification = _safe_segment(
        str(
            capture[
                "classification"
            ]
        )
    )

    lightning_type = _safe_segment(
        str(
            capture[
                "type"
            ]
        )
    )

    return (
        f"verified/{classification}/"
        f"{lightning_type}/{delta_bucket}/{brightness_bucket}/"
        f"{site}/{stem}"
    )


def pair_keys(
    base_key: str,
) -> tuple[str, str]:
    """Return (mp4_key, json_key) for a canonical base key."""
    return (
        f"{base_key}.mp4",
        f"{base_key}.json",
    )


def base_key_from_object_key(
    key: str,
) -> str:
    path = PurePosixPath(
        key
    )

    suffix = path.suffix.lower()

    if suffix not in {
        ".mp4",
        ".json",
    }:
        return key

    return str(
        path.with_suffix("")
    )


def _capture_filename_stem(
    sidecar: dict[str, Any],
    fallback_stem: str | None,
) -> str:
    capture = sidecar.get(
        "capture",
        {},
    )

    if not isinstance(
        capture,
        dict,
    ):
        raise ValueError(
            "Sidecar does not contain capture metadata"
        )

    prefix = (
        "flash"
        if (
            capture.get(
                "verified"
            ) is True
            and str(
                capture.get(
                    "classification",
                    "",
                ) or ""
            ).strip().upper() == "TF"
        )
        else "capture"
    )

    timestamps: list[Any] = [
        capture.get(
            "saved_utc"
        ),
        capture.get(
            "start_utc"
        ),
    ]

    for value in timestamps:
        dt = _parse_utc(
            value
        )

        if dt is not None:
            return (
                f"{prefix}_"
                f"{dt.strftime('%Y%m%dT%H%M%SZ')}"
            )

    if fallback_stem:
        stem = PurePosixPath(
            str(
                fallback_stem
            )
        ).stem

        if stem:
            for old_prefix in (
                "trigger_",
                "capture_",
                "flash_",
            ):
                if stem.startswith(
                    old_prefix
                ):
                    stem = stem[
                        len(old_prefix):
                    ]
                    break

            return _safe_segment(
                f"{prefix}_{stem}"
            )

    raise ValueError(
        "Sidecar does not contain capture.saved_utc/start_utc and no "
        "fallback filename stem was supplied"
    )


def _parse_utc(
    value: Any,
) -> datetime | None:
    if (
        not isinstance(
            value,
            str,
        )
        or not value.strip()
    ):
        return None

    text = value.strip()

    try:
        if text.endswith(
            "Z"
        ):
            dt = datetime.fromisoformat(
                text[:-1] + "+00:00"
            )
        else:
            dt = datetime.fromisoformat(
                text
            )
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )
    else:
        dt = dt.astimezone(
            timezone.utc
        )

    return dt


def _safe_segment(
    value: str,
) -> str:
    # S3 allows almost anything, but path separators must not leak into one
    # logical key segment. Keep spaces and human-readable site names intact.
    return (
        value.strip()
        .replace("/", "_")
        .replace("\\", "_")
        or "Unknown"
    )
