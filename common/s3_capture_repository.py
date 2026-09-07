"""Capture-aware repository layered above the generic S3Store."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any

from common.capture_key import (
    base_key_from_object_key,
    canonical_capture_base_key,
    pair_keys,
)
from common.capture_sidecar import metadata_for_filter, normalize_sidecar
from common.s3_store import S3Store, S3StoreError


@dataclass
class S3CaptureRecord:
    base_key: str
    mp4_key: str
    json_key: str
    sidecar: dict[str, Any]
    metadata_hint: dict[str, Any] | None = None

    @property
    def filename(self) -> str:
        return PurePosixPath(self.mp4_key).name

    @property
    def stem(self) -> str:
        return PurePosixPath(self.mp4_key).stem

    @property
    def metadata(self) -> dict[str, Any]:
        if self.metadata_hint is not None:
            return self.metadata_hint
        return metadata_for_filter(self.sidecar)


class S3CaptureRepository:
    """Browse/open/save Pi Camera MP4+JSON pairs in one S3 bucket."""

    def __init__(self, store: S3Store) -> None:
        self.store = store
        self._tempdir = tempfile.TemporaryDirectory(prefix="picam-vce-s3-")
        self.cache_root = Path(self._tempdir.name)

    def close(self) -> None:
        self._tempdir.cleanup()

    def list_captures(self) -> list[S3CaptureRecord]:
        """Read sidecars under the two Capture Editor namespaces."""
        json_keys: set[str] = set()
        for prefix in ("unverified/", "verified/"):
            for obj in self.store.list_objects(prefix):
                if obj.key.lower().endswith(".json"):
                    json_keys.add(obj.key)

        records: list[S3CaptureRecord] = []
        for json_key in sorted(json_keys):
            try:
                raw = self.store.download_bytes(json_key)
                sidecar = json.loads(raw.decode("utf-8-sig"))
                sidecar, _changed = normalize_sidecar(sidecar)
            except (UnicodeError, json.JSONDecodeError, TypeError, S3StoreError):
                # A malformed/orphan sidecar should not make the entire S3
                # browser unusable. It simply does not appear in the clip list.
                continue

            base_key = base_key_from_object_key(json_key)
            mp4_key, _canonical_json = pair_keys(base_key)
            records.append(
                S3CaptureRecord(
                    base_key=base_key,
                    mp4_key=mp4_key,
                    json_key=json_key,
                    sidecar=sidecar,
                )
            )

        return records

    def list_capture_index(self) -> list[S3CaptureRecord]:
        """List editable captures without downloading every JSON sidecar.

        Canonical S3 keys contain the metadata needed by the Vce browser.
        Full JSON is downloaded only when a capture is opened.
        """
        object_keys: set[str] = set()

        for prefix in (
            "unverified/",
            "verified/",
        ):
            for obj in self.store.list_objects(prefix):
                object_keys.add(obj.key)

        records: list[S3CaptureRecord] = []

        for json_key in sorted(
            key
            for key in object_keys
            if key.lower().endswith(".json")
        ):
            base_key = base_key_from_object_key(json_key)
            mp4_key, _canonical_json = pair_keys(base_key)

            if mp4_key not in object_keys:
                continue

            metadata = self._metadata_from_base_key(base_key)
            if metadata is None:
                continue

            records.append(
                S3CaptureRecord(
                    base_key=base_key,
                    mp4_key=mp4_key,
                    json_key=json_key,
                    sidecar={},
                    metadata_hint=metadata,
                )
            )

        return records

    @staticmethod
    def _metadata_from_base_key(
        base_key: str,
    ) -> dict[str, Any] | None:
        parts = PurePosixPath(base_key).parts

        if not parts:
            return None

        def parse_bucket(text: str, prefix: str) -> int | None:
            if (
                len(text) != 4
                or not text.startswith(prefix)
                or not text[1:].isdigit()
            ):
                return None
            return int(text[1:])

        if parts[0] == "verified":
            # V7:
            # verified/<classification>/<type>/dXXX/bXXX/<site>/<stem>
            if len(parts) == 7:
                delta = parse_bucket(parts[3], "d")
                brightness = parse_bucket(parts[4], "b")
                if delta is None or brightness is None:
                    return None
                return {
                    "verified": True,
                    "classification": parts[1],
                    "type": parts[2],
                    "max_brightness_delta": delta,
                    "mean_brightness": brightness,
                    "site": parts[5],
                }

            # V6 compatibility.
            if len(parts) == 5:
                return {
                    "verified": True,
                    "classification": parts[1],
                    "type": parts[2],
                    "max_brightness_delta": None,
                    "mean_brightness": None,
                    "site": parts[3],
                }

        if parts[0] == "unverified":
            # V7:
            # unverified/<H-M-L>/dXXX/bXXX/<site>/<stem>
            if len(parts) == 6:
                signature = parts[1].split("-")
                delta = parse_bucket(parts[2], "d")
                brightness = parse_bucket(parts[3], "b")
                if (
                    len(signature) != 3
                    or not all(signature)
                    or delta is None
                    or brightness is None
                ):
                    return None
                return {
                    "verified": False,
                    "classification": parts[1],
                    "type": "UK",
                    "max_brightness_delta": delta,
                    "mean_brightness": brightness,
                    "site": parts[4],
                }

            # V6 compatibility.
            if len(parts) == 4:
                signature = parts[1].split("-")
                if len(signature) != 3 or not all(signature):
                    return None
                return {
                    "verified": False,
                    "classification": parts[1],
                    "type": "UK",
                    "max_brightness_delta": None,
                    "mean_brightness": None,
                    "site": parts[2],
                }

            if len(parts) == 3:
                return {
                    "verified": False,
                    "classification": "",
                    "type": "UK",
                    "max_brightness_delta": None,
                    "mean_brightness": None,
                    "site": parts[1],
                }

        return None


    def open_capture(
        self,
        record: S3CaptureRecord,
    ) -> tuple[Path, S3CaptureRecord]:
        """Lazy-upgrade and download one capture pair.

        If the selected S3 sidecar is pre-current-version, opening it performs the
        lazy migration immediately.  That can also re-key the pair into the
        canonical current-version location.  Only the selected capture is migrated;
        listing S3 never mass-updates the bucket.
        """
        raw = self.store.download_bytes(record.json_key)
        sidecar = json.loads(raw.decode("utf-8-sig"))
        sidecar, changed = normalize_sidecar(sidecar)

        if changed:
            record = self.save_capture(record, sidecar)
        else:
            record.sidecar = sidecar
            record.metadata_hint = None

        digest = hashlib.sha1(record.base_key.encode("utf-8")).hexdigest()[:12]
        folder = self.cache_root / digest
        folder.mkdir(parents=True, exist_ok=True)

        local_mp4 = folder / PurePosixPath(record.mp4_key).name
        local_json = local_mp4.with_suffix(".json")

        self.store.download_file(record.mp4_key, local_mp4)
        local_json.write_text(
            json.dumps(record.sidecar, indent=4) + "\n",
            encoding="utf-8",
        )

        return local_mp4, record

    def save_capture(
        self,
        record: S3CaptureRecord,
        sidecar: dict[str, Any],
    ) -> S3CaptureRecord:
        """Write updated JSON and safely re-key the pair when necessary.

        If the canonical key changes:
          1. copy MP4 to the new key
          2. write the new JSON
          3. verify both new objects exist
          4. delete the old pair

        Old objects are never deleted before the new pair has been verified.
        """
        normalized, _changed = normalize_sidecar(sidecar)
        new_base = canonical_capture_base_key(
            normalized,
            fallback_stem=record.stem,
        )
        new_mp4, new_json = pair_keys(new_base)

        json_bytes = (json.dumps(normalized, indent=4) + "\n").encode("utf-8")

        if new_base == record.base_key:
            self.store.upload_bytes(
                json_bytes,
                record.json_key,
                content_type="application/json",
            )
            return S3CaptureRecord(
                base_key=record.base_key,
                mp4_key=record.mp4_key,
                json_key=record.json_key,
                sidecar=normalized,
            )

        created_new_mp4 = False
        created_new_json = False

        try:
            self.store.copy_object(record.mp4_key, new_mp4)
            created_new_mp4 = True

            self.store.upload_bytes(
                json_bytes,
                new_json,
                content_type="application/json",
            )
            created_new_json = True

            if not self.store.object_exists(new_mp4):
                raise S3StoreError(
                    f"S3 re-key verification failed for {new_mp4}"
                )
            if not self.store.object_exists(new_json):
                raise S3StoreError(
                    f"S3 re-key verification failed for {new_json}"
                )

        except Exception:
            # Best-effort cleanup of the incomplete destination. Never touch
            # the old pair on failure.
            if created_new_json:
                try:
                    self.store.delete_object(new_json)
                except Exception:
                    pass
            if created_new_mp4:
                try:
                    self.store.delete_object(new_mp4)
                except Exception:
                    pass
            raise

        self.store.delete_object(record.json_key)
        self.store.delete_object(record.mp4_key)

        return S3CaptureRecord(
            base_key=new_base,
            mp4_key=new_mp4,
            json_key=new_json,
            sidecar=normalized,
        )
