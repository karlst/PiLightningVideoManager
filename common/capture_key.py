"""Canonical V8 S3 key construction for Pi Camera capture pairs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from common.capture_sidecar import CLASSIFICATION_ANOMALY
from common.capture_sidecar import CLASSIFICATION_FLASH
from common.capture_sidecar import normalize_sidecar


def canonical_capture_base_key(
    sidecar: dict[str, Any],
    fallback_stem: str | None = None,
) -> str:
    """Derive the canonical S3 base key from V8 sidecar metadata.

    Unverified FLASH candidates:
        unverified/<site>/<filename-base>

    Verified FLASH captures:
        verified/FLASH/<type>/<site>/<filename-base>

    Verified anomalies:
        verified/ANOMALY/<site>/<filename-base>

    Brightness buckets and classifier confidence deliberately do not appear in
    the object key.  Both remain ordinary sidecar metadata.
    """
    normalized, _changed = normalize_sidecar(sidecar)
    camera = normalized.get("camera", {})

    site = ""
    if isinstance(camera, dict):
        site = str(camera.get("site_name", "") or "").strip()
    site = _safe_segment(site or "Unknown")

    capture = normalized["capture"]
    stem = _capture_filename_stem(normalized, fallback_stem)

    if not capture["verified"]:
        if capture["classification"] != CLASSIFICATION_FLASH:
            raise ValueError(
                "Only unverified FLASH captures may be uploaded to S3"
            )
        return f"unverified/{site}/{stem}"

    classification = capture["classification"]
    if classification == CLASSIFICATION_FLASH:
        lightning_type = _safe_segment(str(capture["type"]))
        return f"verified/FLASH/{lightning_type}/{site}/{stem}"

    if classification == CLASSIFICATION_ANOMALY:
        return f"verified/ANOMALY/{site}/{stem}"

    raise ValueError(f"Unsupported verified classification: {classification}")


def pair_keys(base_key: str) -> tuple[str, str]:
    """Return (mp4_key, json_key) for a canonical base key."""
    return f"{base_key}.mp4", f"{base_key}.json"


def base_key_from_object_key(key: str) -> str:
    path = PurePosixPath(key)
    if path.suffix.lower() not in {".mp4", ".json"}:
        return key
    return str(path.with_suffix(""))


def _capture_filename_stem(
    sidecar: dict[str, Any],
    fallback_stem: str | None,
) -> str:
    capture = sidecar.get("capture", {})
    if not isinstance(capture, dict):
        raise ValueError("Sidecar does not contain capture metadata")

    prefix = (
        "flash"
        if (
            capture.get("verified") is True
            and str(capture.get("classification", "") or "").strip().upper()
            == CLASSIFICATION_FLASH
        )
        else "capture"
    )

    for value in (capture.get("saved_utc"), capture.get("start_utc")):
        dt = _parse_utc(value)
        if dt is not None:
            return f"{prefix}_{dt.strftime('%Y%m%dT%H%M%SZ')}"

    if fallback_stem:
        stem = PurePosixPath(str(fallback_stem)).stem
        if stem:
            for old_prefix in ("trigger_", "capture_", "flash_"):
                if stem.startswith(old_prefix):
                    stem = stem[len(old_prefix):]
                    break
            return _safe_segment(f"{prefix}_{stem}")

    raise ValueError(
        "Sidecar does not contain capture.saved_utc/start_utc and no "
        "fallback filename stem was supplied"
    )


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    try:
        if text.endswith("Z"):
            dt = datetime.fromisoformat(text[:-1] + "+00:00")
        else:
            dt = datetime.fromisoformat(text)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _safe_segment(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "Unknown"

    for bad in ("/", "\\", "\x00"):
        text = text.replace(bad, "_")
    return text
