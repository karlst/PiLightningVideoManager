# VERIFIED UNIFIED LINUX BUILD 2026-08-27
"""
@file buildLinuxTools.py

@brief Build and install the Linux Video Manager executable suite.

Builds exactly:

    Vfa
    Vce
    Ccm
    filterSolutions
    runSmokeTests
    buildCaptureIndex

Vfa uses the maintained packaging/VfaLinux.spec. Vce and the three console
utilities are built directly from their current Python entry points.

Commands:

    python packaging/buildLinuxTools.py build
    python packaging/buildLinuxTools.py install
    python packaging/buildLinuxTools.py clean
    python packaging/buildLinuxTools.py clean-install

Finished build:

    <repository>/dist/linux/VideoManager/

Installed suite:

    ~/bin/VideoManager/

PyInstaller intermediate output:

    <repository>/build/linux/

Smoke-test data is copied to:

    VideoManager/testData/

FFmpeg and ffprobe are copied to:

    VideoManager/tools/

so frozen applications can resolve them without requiring PATH on the target
machine.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys


PACKAGING_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGING_DIRECTORY.parent

VFA_SPEC = PACKAGING_DIRECTORY / "VfaLinux.spec"

BUILD_ROOT = REPOSITORY_ROOT / "build" / "linux"
DIST_ROOT = REPOSITORY_ROOT / "dist" / "linux"
DIST_DIRECTORY = DIST_ROOT / "VideoManager"

INSTALL_DIRECTORY = (
    Path.home()
    / "bin"
    / "VideoManager"
)

VCE_SOURCE = (
    REPOSITORY_ROOT
    / "video_analyzer"
    / "clip_editor.py"
)

CCM_SOURCE = (
    REPOSITORY_ROOT
    / "camera_capture_manager"
    / "ccm.py"
)

FILTER_SOLUTIONS_SOURCE = (
    REPOSITORY_ROOT
    / "tools"
    / "filter_solutions.py"
)

SMOKE_TEST_SOURCE = (
    REPOSITORY_ROOT
    / "tools"
    / "run_smoke_tests.py"
)

BUILD_CAPTURE_INDEX_SOURCE = (
    REPOSITORY_ROOT
    / "tools"
    / "buildCaptureIndex.py"
)

TEST_DATA_SOURCE = (
    REPOSITORY_ROOT
    / "testData"
)

EXPECTED_EXECUTABLES = (
    "Vfa",
    "Vce",
    "Ccm",
    "filterSolutions",
    "runSmokeTests",
    "buildCaptureIndex",
)


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
            f"Required Python build dependency is missing: {module_name}. "
            f"Install it in the build environment before building."
        ) from error


def require_path_tool(executable_name: str) -> Path:
    result = shutil.which(
        executable_name
    )

    if result is None:
        raise RuntimeError(
            f"{executable_name} was not found on PATH. "
            "Install FFmpeg on the Linux build machine before building."
        )

    return Path(
        result
    ).resolve()


def run_command(command: list[str]) -> None:
    print()
    print(
        " ".join(
            str(part)
            for part in command
        )
    )

    subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=True,
    )


def build_vfa() -> None:
    """
    Build Vfa with the maintained Linux spec, then merge its complete onedir
    runtime tree into dist/linux/VideoManager.
    """
    print()
    print(
        "Building Vfa using packaging/VfaLinux.spec..."
    )

    staging_dist = (
        BUILD_ROOT
        / "vfa_dist"
    )

    work_directory = (
        BUILD_ROOT
        / "Vfa"
    )

    if staging_dist.exists():
        shutil.rmtree(
            staging_dist
        )

    staging_dist.mkdir(
        parents=True,
        exist_ok=True,
    )

    run_command(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--workpath",
            str(work_directory),
            "--distpath",
            str(staging_dist),
            str(VFA_SPEC),
        ]
    )

    built_directory = (
        staging_dist
        / "Vfa"
    )

    built_executable = (
        built_directory
        / "Vfa"
    )

    if not built_executable.is_file():
        raise RuntimeError(
            f"Vfa was not found after build: {built_executable}"
        )

    shutil.copytree(
        built_directory,
        DIST_DIRECTORY,
        dirs_exist_ok=True,
    )


def build_direct_executable(
    source_file: Path,
    executable_name: str,
    windowed: bool,
) -> None:
    print()
    print(
        f"Building {executable_name}..."
    )

    work_directory = (
        BUILD_ROOT
        / executable_name
    )

    spec_directory = (
        BUILD_ROOT
        / "generated_specs"
    )

    spec_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        executable_name,
        "--paths",
        str(REPOSITORY_ROOT),
        "--workpath",
        str(work_directory),
        "--specpath",
        str(spec_directory),
        "--distpath",
        str(DIST_DIRECTORY),
    ]

    command.append(
        "--windowed"
        if windowed
        else "--console"
    )

    command.append(
        str(source_file)
    )

    run_command(
        command
    )

    executable = (
        DIST_DIRECTORY
        / executable_name
    )

    if not executable.is_file():
        raise RuntimeError(
            f"{executable_name} was not found after build: {executable}"
        )


def copy_external_tools() -> None:
    ffmpeg_path = require_path_tool(
        "ffmpeg"
    )

    ffprobe_path = require_path_tool(
        "ffprobe"
    )

    tools_directory = (
        DIST_DIRECTORY
        / "tools"
    )

    tools_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        ffmpeg_path,
        tools_directory / "ffmpeg",
    )

    shutil.copy2(
        ffprobe_path,
        tools_directory / "ffprobe",
    )



def copy_test_data() -> None:
    if not TEST_DATA_SOURCE.is_dir():
        raise RuntimeError(
            f"Required test-data folder not found: {TEST_DATA_SOURCE}"
        )

    destination = (
        DIST_DIRECTORY
        / "testData"
    )

    shutil.copytree(
        TEST_DATA_SOURCE,
        destination,
        dirs_exist_ok=True,
    )


def verify_suite(directory: Path) -> None:
    missing = [
        executable_name
        for executable_name in EXPECTED_EXECUTABLES
        if not (
            directory
            / executable_name
        ).is_file()
    ]

    if missing:
        raise RuntimeError(
            "Expected executable(s) missing: "
            + ", ".join(missing)
        )


def clean() -> None:
    if BUILD_ROOT.exists():
        print(
            f"Removing {BUILD_ROOT}"
        )

        shutil.rmtree(
            BUILD_ROOT
        )

    if DIST_DIRECTORY.exists():
        print(
            f"Removing {DIST_DIRECTORY}"
        )

        shutil.rmtree(
            DIST_DIRECTORY
        )

    print("Clean complete.")


def build() -> None:
    if not sys.platform.startswith("linux"):
        raise RuntimeError(
            "This build script must be run on Linux."
        )

    require_python_module("paramiko")

    for path in (
        VFA_SPEC,
        VCE_SOURCE,
        CCM_SOURCE,
        FILTER_SOLUTIONS_SOURCE,
        SMOKE_TEST_SOURCE,
        BUILD_CAPTURE_INDEX_SOURCE,
    ):
        require_file(
            path
        )

    if BUILD_ROOT.exists():
        shutil.rmtree(
            BUILD_ROOT
        )

    if DIST_DIRECTORY.exists():
        shutil.rmtree(
            DIST_DIRECTORY
        )

    BUILD_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    DIST_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    build_vfa()

    build_direct_executable(
        VCE_SOURCE,
        "Vce",
        windowed=True,
    )

    build_direct_executable(
        CCM_SOURCE,
        "Ccm",
        windowed=True,
    )

    build_direct_executable(
        FILTER_SOLUTIONS_SOURCE,
        "filterSolutions",
        windowed=False,
    )

    build_direct_executable(
        SMOKE_TEST_SOURCE,
        "runSmokeTests",
        windowed=False,
    )

    build_direct_executable(
        BUILD_CAPTURE_INDEX_SOURCE,
        "buildCaptureIndex",
        windowed=False,
    )

    copy_external_tools()
    copy_test_data()

    verify_suite(
        DIST_DIRECTORY
    )

    print()
    print("Linux build complete.")
    print(
        f"Output: {DIST_DIRECTORY}"
    )


def install() -> None:
    # Always rebuild first; never install stale binaries accidentally.
    build()

    if INSTALL_DIRECTORY.exists():
        print(
            f"Removing existing install: {INSTALL_DIRECTORY}"
        )

        shutil.rmtree(
            INSTALL_DIRECTORY
        )

    INSTALL_DIRECTORY.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"Installing to: {INSTALL_DIRECTORY}"
    )

    shutil.copytree(
        DIST_DIRECTORY,
        INSTALL_DIRECTORY,
    )

    verify_suite(
        INSTALL_DIRECTORY
    )

    print()
    print(
        f"Install complete: {INSTALL_DIRECTORY}"
    )


def print_usage() -> None:
    print("Usage:")
    print(
        "  python packaging/buildLinuxTools.py build"
    )
    print(
        "  python packaging/buildLinuxTools.py install"
    )
    print(
        "  python packaging/buildLinuxTools.py clean"
    )
    print(
        "  python packaging/buildLinuxTools.py clean-install"
    )


def main() -> int:
    command = (
        sys.argv[1].lower()
        if len(sys.argv) > 1
        else "build"
    )

    try:
        if command == "build":
            build()

        elif command == "install":
            install()

        elif command == "clean":
            clean()

        elif command == "clean-install":
            clean()
            install()

        else:
            print_usage()
            return 1

    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        print()
        print(
            f"Linux tools build failed: {error}"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
