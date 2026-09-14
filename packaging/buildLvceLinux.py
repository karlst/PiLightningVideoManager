"""
@file buildLvceLinux.py

@brief Build the Linux Lightning Video Clip Editor/Reader executable.

Commands:

    python packaging/buildLvceLinux.py build
    python packaging/buildLvceLinux.py clean

Output:

    <repository>/dist/linux/Lvce/Lvce

The build embeds ffmpeg and ffprobe inside the PyInstaller one-file bundle.
At runtime PyInstaller extracts them to its temporary directory and a runtime
hook prepends that internal tools directory to PATH.
"""

from __future__ import annotations

from pathlib import Path
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
    / "linux"
    / "Lvce"
)

SPEC_DIRECTORY = (
    BUILD_DIRECTORY
    / "spec"
)

DIST_DIRECTORY = (
    REPOSITORY_ROOT
    / "dist"
    / "linux"
    / "Lvce"
)

RUNTIME_HOOK = (
    BUILD_DIRECTORY
    / "lvce_runtime.py"
)

SPLASH_IMAGE = PACKAGING_DIRECTORY / "LvceSplash.png"

EXECUTABLE_NAME = "Lvce"
EXECUTABLE_PATH = DIST_DIRECTORY / EXECUTABLE_NAME


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

    return Path(result).resolve()


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
    if not sys.platform.startswith("linux"):
        raise RuntimeError(
            "This build script must be run on Linux."
        )

    for module_name in (
        "PyInstaller",
        "PySide6",
        "cv2",
        "numpy",
        "boto3",
        "tkinter",
    ):
        require_python_module(module_name)

    require_file(SOURCE_FILE)
    require_file(SPLASH_IMAGE)

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
        "--onefile",
        "--windowed",
        "--splash",
        str(SPLASH_IMAGE),
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

    if not EXECUTABLE_PATH.is_file():
        raise RuntimeError(
            f"{EXECUTABLE_NAME} was not found after build: "
            f"{EXECUTABLE_PATH}"
        )

    EXECUTABLE_PATH.chmod(
        EXECUTABLE_PATH.stat().st_mode | 0o111
    )

    size_mb = EXECUTABLE_PATH.stat().st_size / (1024 * 1024)

    print()
    print("Linux build complete.")
    print(f"Executable: {EXECUTABLE_PATH}")
    print(f"Size: {size_mb:.1f} MB")
    print(f"Embedded ffmpeg:  {ffmpeg_path}")
    print(f"Embedded ffprobe: {ffprobe_path}")
    print(f"Splash image:     {SPLASH_IMAGE}")


def print_usage() -> None:
    print("Usage:")
    print("  python packaging/buildLvceLinux.py build")
    print("  python packaging/buildLvceLinux.py clean")


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
        print(f"Lvce Linux build failed: {error}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
