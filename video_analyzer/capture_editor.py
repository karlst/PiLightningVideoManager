"""Entry point: python -m video_analyzer.capture_editor [folder|capture.mp4|capture.json]

Vce Capture Editor with Local Storage and S3 backends.
"""
from __future__ import annotations

import argparse
import json
import sys

import boto3
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from common.aws_auth import DEFAULT_CREDENTIAL_FILE
from common.candidate_config import CANDIDATE_CONFIG
from common.capture_sidecar import normalize_sidecar
from video_analyzer.capture_data import load_capture
from video_analyzer.candidate_replay import replay_candidate_finder
from video_analyzer.solution_config import SOLUTION_CONFIG, solution_config_for_sensitivity
from video_analyzer.solution_filter import SolutionFilter, failed_candidate_result
from video_analyzer.capture_editor_window import CaptureEditorWindow
from common.rc import csc


S3_BUCKET_NAME = "soloran-picam"
S3_AUTH_PROFILE = "picam-manager"


def classify_capture(path: Path, *, read_only: bool = False):
    cd = load_capture(path)

    # Normalize the current V7 sidecar when the user opens it.
    if isinstance(cd.sidecar, dict):
        upgraded, changed = normalize_sidecar(cd.sidecar)
        cd.sidecar = upgraded
        if changed and not read_only:
            tmp = cd.sidecar_path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(upgraded, indent=4) + "\n",
                encoding="utf-8",
            )
            tmp.replace(cd.sidecar_path)

    cr = replay_candidate_finder(cd, CANDIDATE_CONFIG)
    sc = solution_config_for_sensitivity(CANDIDATE_CONFIG.sensitivity, SOLUTION_CONFIG)
    sr = (
        failed_candidate_result()
        if cr.frame_index is None
        else SolutionFilter(sc).evaluate(
            cd.pi_brightness,
            cd.pi_brightness_delta,
            cr.frame_index,
            cr.reason,
        )
    )
    return cd, cr, sr



def _load_editor_profile_if_present() -> tuple[dict[str, str], str] | None:
    """Load picam-manager credentials without making startup stricter than legacy Vce.

    The deployed credential file may contain trailing provisioning data after the
    primary JSON object. Reader/editor mode detection only needs the first JSON
    object, so decode exactly that object instead of requiring the entire file
    to contain one JSON document.
    """
    path = Path(DEFAULT_CREDENTIAL_FILE).expanduser()
    if not path.is_file():
        return None

    try:
        text = path.read_text(encoding="utf-8")
        document, _end = json.JSONDecoder().raw_decode(text.lstrip())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to read editor AWS credentials: {exc}") from exc

    if not isinstance(document, dict):
        raise RuntimeError("Editor AWS credential file root is not an object")

    profiles = document.get("profiles")
    if not isinstance(profiles, dict):
        raise RuntimeError("Editor AWS credential file has no profiles object")

    profile = profiles.get(S3_AUTH_PROFILE)
    if profile is None:
        return None
    if not isinstance(profile, dict):
        raise RuntimeError(f"Editor AWS profile {S3_AUTH_PROFILE!r} is invalid")

    access_key_id = profile.get("access_key_id")
    secret_access_key = profile.get("secret_access_key")
    if not isinstance(access_key_id, str) or not access_key_id.strip():
        raise RuntimeError("Editor AWS access key is missing")
    if not isinstance(secret_access_key, str) or not secret_access_key.strip():
        raise RuntimeError("Editor AWS secret access key is missing")

    region = document.get("region", "us-west-2")
    if not isinstance(region, str) or not region.strip():
        region = "us-west-2"

    return ({
        "access_key_id": access_key_id.strip(),
        "secret_access_key": secret_access_key.strip(),
    }, region.strip())


def select_application_mode() -> tuple[str, object]:
    """Return (mode, S3 client), preferring working editor credentials."""
    try:
        loaded = _load_editor_profile_if_present()
    except RuntimeError as exc:
        QMessageBox.warning(
            None,
            "Authentication failed",
            f"Authentication failed.\n\n{exc}",
            QMessageBox.StandardButton.Ok,
        )
        return "reader", csc()

    if loaded is None:
        return "reader", csc()

    profile, region = loaded
    editor_client = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=profile["access_key_id"],
        aws_secret_access_key=profile["secret_access_key"],
    )

    try:
        editor_client.list_objects_v2(
            Bucket=S3_BUCKET_NAME,
            Prefix="unverified/",
            MaxKeys=1,
        )
    except Exception:
        QMessageBox.warning(
            None,
            "Authentication failed",
            "Authentication failed.",
            QMessageBox.StandardButton.Ok,
        )
        return "reader", csc()

    return "editor", editor_client

def main():
    ap = argparse.ArgumentParser(description="Vce Local/S3 Capture Editor")
    ap.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=None,
        help="Optional local folder or capture MP4/JSON",
    )
    args = ap.parse_args()

    app = QApplication(sys.argv)
    p = args.path.expanduser() if args.path is not None else None

    try:
        app_mode, s3_client = select_application_mode()
        initial_source = "S3" if p is None else "Local Storage"

        if p is None:
            w = CaptureEditorWindow(
                None,
                None,
                None,
                open_directory=Path.cwd(),
                app_mode=app_mode,
                s3_client=s3_client,
                initial_source=initial_source,
            )
        elif p.is_dir():
            clips = sorted(
                (x for x in p.iterdir() if x.is_file() and x.suffix.lower() == ".mp4"),
                key=lambda x: x.name.lower(),
            )
            if clips:
                cd, cr, sr = classify_capture(
                    clips[0],
                    read_only=app_mode == "reader",
                )
                w = CaptureEditorWindow(
                    cd,
                    cr,
                    sr,
                    open_directory=p,
                    app_mode=app_mode,
                    s3_client=s3_client,
                    initial_source=initial_source,
                )
            else:
                w = CaptureEditorWindow(
                    None,
                    None,
                    None,
                    open_directory=p,
                    app_mode=app_mode,
                    s3_client=s3_client,
                    initial_source=initial_source,
                )
        else:
            cd, cr, sr = classify_capture(
                p,
                read_only=app_mode == "reader",
            )
            w = CaptureEditorWindow(
                cd,
                cr,
                sr,
                open_directory=cd.video_path.parent,
                app_mode=app_mode,
                s3_client=s3_client,
                initial_source=initial_source,
            )
    except (RuntimeError, OSError) as e:
        print(f"Capture Editor: {e}", file=sys.stderr)
        return 1

    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
