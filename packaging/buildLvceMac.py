"""
@file buildLvceMac.py

@brief Build the macOS Lightning Video Clip Editor/Reader application.

Commands:

    python3 packaging/buildLvceMac.py build
    python3 packaging/buildLvceMac.py clean

Output:

    <repository>/dist/macos/Lvce/Lvce.app

The macOS build deliberately uses PyInstaller's one-folder/windowed mode rather
than one-file mode.  On macOS this creates a normal .app bundle, starts faster,
and avoids the repeated one-file extraction cost on every launch.

The build embeds ffmpeg and ffprobe inside the application bundle.  A runtime
hook prepends the bundled tools directory to PATH so existing subprocess calls
can continue to invoke "ffmpeg" and "ffprobe" by name.

PyInstaller's splash-screen feature is intentionally NOT used here because it
is incompatible with macOS.
"""

from __future__ import annotations

from pathlib import Path
import platform
import shutil
import subprocess
import sys


PACKAGING_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGING_DIRECTORY.parent

SOURCE_FILE = (
    REPOSITORY_ROOT
    / "video_analyzer"
    / "capture_editor.py"
)

BUILD_DIRECTORY = (
    REPOSITORY_ROOT
    / "build"
    / "macos"
    / "Lvce"
)

SPEC_DIRECTORY = (
    BUILD_DIRECTORY
    / "spec"
)

DIST_DIRECTORY = (
    REPOSITORY_ROOT
    / "dist"
    / "macos"
    / "Lvce"
)

RUNTIME_HOOK = (
    BUILD_DIRECTORY
    / "lvce_runtime.py"
)

EXECUTABLE_NAME = "Lvce"
APP_PATH = DIST_DIRECTORY / f"{EXECUTABLE_NAME}.app"


def require_file(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(
            f"Required file not found: {path}"
        )


def require_python_module(module_name: str) -> None:
    try:
        __import__(module_name)
    except ImportError as error:
        raise RuntimeError(
            f"Required Python build dependency is missing: {module_name}"
        ) from error


def require_path_tool(executable_name: str) -> Path:
    result = shutil.which(executable_name)

    if result is None:
        raise RuntimeError(
            f"{executable_name} was not found on PATH on the build machine"
        )

    path = Path(result).resolve()
    require_file(path)
    return path


def run_command(command: list[str]) -> None:
    print()
    print(
        subprocess.list2cmdline(
            [str(part) for part in command]
        )
    )

    subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=True,
    )


def write_runtime_hook() -> None:
    RUNTIME_HOOK.write_text(
        (
            "import os\n"
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            "base = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))\n"
            "tools = base / 'tools'\n"
            "os.environ['PATH'] = str(tools) + os.pathsep + os.environ.get('PATH', '')\n"
        ),
        encoding="utf-8",
    )


def clean() -> None:
    if BUILD_DIRECTORY.exists():
        print(f"Removing {BUILD_DIRECTORY}")
        shutil.rmtree(BUILD_DIRECTORY)

    if DIST_DIRECTORY.exists():
        print(f"Removing {DIST_DIRECTORY}")
        shutil.rmtree(DIST_DIRECTORY)

    print("Clean complete.")


def build() -> None:
    if sys.platform != "darwin":
        raise RuntimeError(
            "This build script must be run on macOS."
        )

    for module_name in (
        "PyInstaller",
        "PySide6",
        "cv2",
        "numpy",
        "boto3",
    ):
        require_python_module(module_name)

    require_file(SOURCE_FILE)

    ffmpeg_path = require_path_tool("ffmpeg")
    ffprobe_path = require_path_tool("ffprobe")

    if BUILD_DIRECTORY.exists():
        shutil.rmtree(BUILD_DIRECTORY)

    if DIST_DIRECTORY.exists():
        shutil.rmtree(DIST_DIRECTORY)

    BUILD_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )
    SPEC_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )
    DIST_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_runtime_hook()

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        EXECUTABLE_NAME,
        "--paths",
        str(REPOSITORY_ROOT),
        "--workpath",
        str(BUILD_DIRECTORY),
        "--specpath",
        str(SPEC_DIRECTORY),
        "--distpath",
        str(DIST_DIRECTORY),
        "--runtime-hook",
        str(RUNTIME_HOOK),
        "--add-binary",
        f"{ffmpeg_path}:tools",
        "--add-binary",
        f"{ffprobe_path}:tools",
        str(SOURCE_FILE),
    ]

    run_command(command)

    if not APP_PATH.is_dir():
        raise RuntimeError(
            f"{EXECUTABLE_NAME}.app was not found after build: {APP_PATH}"
        )

    app_size_bytes = sum(
        p.stat().st_size
        for p in APP_PATH.rglob("*")
        if p.is_file()
    )
    size_mb = app_size_bytes / (1024 * 1024)

    print()
    print("macOS build complete.")
    print(f"Application:       {APP_PATH}")
    print(f"Size:              {size_mb:.1f} MB")
    print(f"Architecture:      {platform.machine()}")
    print(f"Embedded ffmpeg:   {ffmpeg_path}")
    print(f"Embedded ffprobe:  {ffprobe_path}")
    print("Splash image:      not used (PyInstaller splash is incompatible with macOS)")
    print()
    print("Unsigned build: macOS Gatekeeper may require a one-time manual override")
    print("when this app is downloaded onto another Mac.")


def print_usage() -> None:
    print("Usage:")
    print("  python3 packaging/buildLvceMac.py build")
    print("  python3 packaging/buildLvceMac.py clean")


def main() -> int:
    command = (
        sys.argv[1].lower()
        if len(sys.argv) > 1
        else "build"
    )

    try:
        if command == "build":
            build()
        elif command == "clean":
            clean()
        else:
            print_usage()
            return 1

    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        print()
        print(f"Lvce macOS build failed: {error}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
