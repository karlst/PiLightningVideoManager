# PI PACKAGE BUILDER V1 2026-08-29
"""
@file buildPiPackage.py

@brief Build the Raspberry Pi Camera Capture source/install release.

Run from the repository root:

    python packaging/piSide/buildPiPackage.py

Output:

    dist/pi/piCameraCapture/
    dist/pi/piCameraCapture.tar.gz

The Pi release intentionally contains only Pi runtime source and installation
support. It does NOT copy .venv, desktop GUI files, testData, build output,
web publication captures, or machine-specific NetworkManager profiles.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import tarfile


PACKAGING_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGING_DIRECTORY.parents[1]

DIST_ROOT = REPOSITORY_ROOT / "dist" / "pi"
DIST_DIRECTORY = DIST_ROOT / "piCameraCapture"
APP_DIRECTORY = DIST_DIRECTORY / "app"

VIDEO_ANALYZER_FILES = (
    "__init__.py",
    "brightness_noise_filter.py",
    "bright_pixel_no_return_filter.py",
    "candidate_replay.py",
    "capture_data.py",
    "frame_dropout_filter.py",
    "solution_config.py",
    "solution_filter.py",
    "solution_types.py",
    "stair_step_decay_filter.py",
    "steady_state_change_filter.py",
    "strong_transient_filter.py",
    "tool_paths.py",
)

VIDEO_CAPTURE_EXCLUDE = {
    "openCvTimingTest.py",
}

SUPPORT_FILES = (
    "install.sh",
    "upgrade.sh",
    "uninstall.sh",
)

BIN_FILES = (
    "addWifi",
    "delWifi",
    "vmStart",
    "vmStop",
    "vmRestart",
    "vmStatus",
    "vmEnable",
    "vmDisable",
    "vmLog",
    "psfStart",
    "psfStop",
    "psfRestart",
)


def require_file(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"Required file not found: {path}")


def copy_python_directory(
    source: Path,
    destination: Path,
    exclude: set[str] | None = None,
) -> None:
    exclude = exclude or set()
    destination.mkdir(parents=True, exist_ok=True)

    for path in sorted(source.glob("*.py")):
        if path.name in exclude:
            continue
        shutil.copy2(path, destination / path.name)


def build() -> None:
    if DIST_DIRECTORY.exists():
        shutil.rmtree(DIST_DIRECTORY)

    APP_DIRECTORY.mkdir(parents=True, exist_ok=True)

    # Repository-level runtime.
    require_file(REPOSITORY_ROOT / "version.py")
    shutil.copy2(
        REPOSITORY_ROOT / "version.py",
        APP_DIRECTORY / "version.py",
    )

    # Shared non-GUI runtime.
    copy_python_directory(
        REPOSITORY_ROOT / "common",
        APP_DIRECTORY / "common",
    )

    # Pi capture/web runtime. Exclude the explicit timing-development tool.
    copy_python_directory(
        REPOSITORY_ROOT / "video_capture",
        APP_DIRECTORY / "video_capture",
        exclude=VIDEO_CAPTURE_EXCLUDE,
    )

    # Flask templates/static files are runtime assets.
    shutil.copytree(
        REPOSITORY_ROOT / "video_capture" / "templates",
        APP_DIRECTORY / "video_capture" / "templates",
    )
    shutil.copytree(
        REPOSITORY_ROOT / "video_capture" / "static",
        APP_DIRECTORY / "video_capture" / "static",
    )

    # Only analyzer modules imported by Pi replay/SolutionFilter.
    analyzer_destination = APP_DIRECTORY / "video_analyzer"
    analyzer_destination.mkdir(parents=True, exist_ok=True)

    for filename in VIDEO_ANALYZER_FILES:
        source = REPOSITORY_ROOT / "video_analyzer" / filename
        require_file(source)
        shutil.copy2(source, analyzer_destination / filename)

    # Shared playback component used by the Pi-hosted web UI.
    capture_viewer = (
        REPOSITORY_ROOT
        / "web_viewer"
        / "static"
        / "js"
        / "captureViewer.js"
    )
    require_file(capture_viewer)

    viewer_destination = (
        APP_DIRECTORY
        / "web_viewer"
        / "static"
        / "js"
    )
    viewer_destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        capture_viewer,
        viewer_destination / "captureViewer.js",
    )

    # Clean generic defaults. Never ship Karl/site-specific geometry/paths.
    defaults = DIST_DIRECTORY / "defaults"
    defaults.mkdir(parents=True, exist_ok=True)

    (defaults / "camera_config.json").write_text(
        """{
    "video_device": "/dev/video0",
    "input_format": "mjpeg",
    "frame_rate_fps": 260,
    "frame_width_pixels": 640,
    "frame_height_pixels": 360,
    "camera_name": "ELP USB Camera",
    "camera_type": "ELP USB High Speed",
    "camera_site_name": "UNCONFIGURED",
    "camera_latitude_degrees": 0.0,
    "camera_longitude_degrees": 0.0,
    "camera_bearing_degrees": 0.0,
    "camera_hfov_degrees": 0.0,
    "camera_vfov_degrees": 0.0
}
""",
        encoding="utf-8",
    )

    # Candidate defaults are shared product defaults, not machine-specific.
    candidate_source = REPOSITORY_ROOT / "config" / "candidate_config.json"
    require_file(candidate_source)
    shutil.copy2(
        candidate_source,
        defaults / "candidate_config.json",
    )

    # system_config.json is generated by install.sh because paths depend
    # on the target user.
    (defaults / "system_config.json").write_text(
        """{
    "home_directory": "",
    "program_root": "",
    "data_root": "",
    "psf_interval_seconds": 60,
    "save_filtered_false_positives": false
}
""",
        encoding="utf-8",
    )

    # Network runtime.
    network_destination = DIST_DIRECTORY / "network"
    network_destination.mkdir(parents=True, exist_ok=True)

    wifi_startup = REPOSITORY_ROOT / "network" / "wifiStartup.py"
    require_file(wifi_startup)

    shutil.copy2(
        wifi_startup,
        network_destination / "wifiStartup.py",
    )

    for filename in SUPPORT_FILES:
        source = PACKAGING_DIRECTORY / filename
        require_file(source)
        shutil.copy2(source, DIST_DIRECTORY / filename)

    bin_destination = DIST_DIRECTORY / "bin"
    bin_destination.mkdir(parents=True, exist_ok=True)

    for filename in BIN_FILES:
        source = PACKAGING_DIRECTORY / "bin" / filename
        require_file(source)
        shutil.copy2(source, bin_destination / filename)

    # Normalize shell scripts to Unix LF line endings.  The package is built
    # on Windows, so do not rely on the source checkout's line-ending mode.
    executable_paths = [
        DIST_DIRECTORY / "install.sh",
        DIST_DIRECTORY / "upgrade.sh",
        DIST_DIRECTORY / "uninstall.sh",
        *[bin_destination / name for name in BIN_FILES],
    ]

    for path in executable_paths:
        data = path.read_bytes().replace(b"\r\n", b"\n")
        path.write_bytes(data)

    archive_path = DIST_ROOT / "piCameraCapture.tar.gz"

    if archive_path.exists():
        archive_path.unlink()

    # Windows does not preserve Unix executable bits.  Set them explicitly
    # in the tar metadata so extraction on a Pi produces runnable scripts.
    executable_archive_names = {
        "piCameraCapture/install.sh",
        "piCameraCapture/upgrade.sh",
        "piCameraCapture/uninstall.sh",
        *{f"piCameraCapture/bin/{name}" for name in BIN_FILES},
    }

    def tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
        if info.name in executable_archive_names:
            info.mode = 0o755
        return info

    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(
            DIST_DIRECTORY,
            arcname="piCameraCapture",
            filter=tar_filter,
        )

    print()
    print(f"Built: {DIST_DIRECTORY}")
    print(f"Archive: {archive_path}")


if __name__ == "__main__":
    build()
