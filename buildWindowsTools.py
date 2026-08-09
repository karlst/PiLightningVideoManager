"""
@file buildWindowsTools.py

@brief Build the self-contained Windows Video Camera Manager desktop release.

Run this script from Windows with the repository checked out and the project's
Python environment active.

The script builds three PyInstaller executables:

    Analyzer.exe
    BatchClassifier.exe
    RebuildSidecars.exe

Python and Python package dependencies are bundled by PyInstaller. FFmpeg and
ffprobe are copied into a "tools" directory inside the release package so the
end user does not need to install FFmpeg or modify PATH.

The developer machine DOES need ffmpeg.exe and ffprobe.exe available on PATH
while building. They are copied from that development installation into the
release package.

The resulting package is:

    dist/
        VideoManager-v<version>-Windows/
            Analyzer.exe
            BatchClassifier.exe
            RebuildSidecars.exe
            README.md
            tools/
                ffmpeg.exe
                ffprobe.exe

        VideoManager-v<version>-Windows.zip

The three programs share the same application version from
video_analyzer/version.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


# ## Load the shared release version without requiring video_analyzer to be installed.
def read_version(
    repository_root: Path,
) -> str:
    version_file = (
        repository_root
        /
        "video_analyzer"
        /
        "version.py"
    )

    if not version_file.is_file():
        raise RuntimeError(
            f"Version file not found: "
            f"{version_file}"
        )

    specification = (
        importlib.util.spec_from_file_location(
            "video_manager_version",
            version_file,
        )
    )

    if (
        specification is None
        or specification.loader is None
    ):
        raise RuntimeError(
            "Unable to load version.py"
        )

    module = (
        importlib.util.module_from_spec(
            specification
        )
    )

    specification.loader.exec_module(
        module
    )

    version = getattr(
        module,
        "VERSION",
        None,
    )

    if not isinstance(
        version,
        str,
    ) or not version.strip():
        raise RuntimeError(
            "video_analyzer/version.py "
            "does not define a valid VERSION string"
        )

    return version.strip()


# ## Find one required build-time executable on the developer's PATH.
def require_path_tool(
    executable_name: str,
) -> Path:
    path = shutil.which(
        executable_name
    )

    if path is None:
        raise RuntimeError(
            f"{executable_name} was not found on PATH. "
            "Install FFmpeg on the build machine before "
            "creating the Windows release."
        )

    return Path(
        path
    ).resolve()


# ## Run one PyInstaller build with a consistent repository search path.
def build_executable(
    repository_root: Path,
    work_directory: Path,
    specification_directory: Path,
    release_directory: Path,
    source_file: Path,
    executable_name: str,
    windowed: bool,
) -> None:
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
        str(repository_root),
        "--workpath",
        str(
            work_directory
            /
            executable_name
        ),
        "--specpath",
        str(
            specification_directory
        ),
        "--distpath",
        str(
            release_directory
        ),
    ]

    if windowed:
        command.append(
            "--windowed"
        )
    else:
        command.append(
            "--console"
        )

    command.append(
        str(source_file)
    )

    print()
    print(
        f"Building {executable_name}.exe"
    )

    subprocess.run(
        command,
        cwd=repository_root,
        check=True,
    )


# ## Zip the finished release directory without adding an extra temporary tree.
def create_release_zip(
    release_directory: Path,
    zip_path: Path,
) -> None:
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for file_path in sorted(
            release_directory.rglob("*")
        ):
            if not file_path.is_file():
                continue

            archive_name = (
                release_directory.name
                /
                file_path.relative_to(
                    release_directory
                )
            )

            archive.write(
                file_path,
                archive_name,
            )


# ## Build all Windows executables, bundle external tools, and create the release ZIP.
def main() -> int:
    repository_root = (
        Path(__file__).resolve().parent
    )

    if sys.platform != "win32":
        print(
            "This build script must be run on Windows."
        )
        return 1

    try:
        version = read_version(
            repository_root
        )

        ffmpeg_path = require_path_tool(
            "ffmpeg.exe"
        )
        ffprobe_path = require_path_tool(
            "ffprobe.exe"
        )

        build_root = (
            repository_root
            /
            "build"
            /
            "windows"
        )

        specification_directory = (
            build_root
            /
            "spec"
        )

        release_root = (
            repository_root
            /
            "dist"
        )

        package_name = (
            f"VideoManager-v{version}-Windows"
        )

        release_directory = (
            release_root
            /
            package_name
        )

        zip_path = (
            release_root
            /
            f"{package_name}.zip"
        )

        # Always build into a clean package tree so stale executables or tools
        # from a previous version cannot accidentally enter the release.
        if build_root.exists():
            shutil.rmtree(
                build_root
            )

        if release_directory.exists():
            shutil.rmtree(
                release_directory
            )

        specification_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        release_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        build_executable(
            repository_root=repository_root,
            work_directory=build_root,
            specification_directory=specification_directory,
            release_directory=release_directory,
            source_file=(
                repository_root
                /
                "video_analyzer"
                /
                "analyzer.py"
            ),
            executable_name="Analyzer",
            windowed=True,
        )

        build_executable(
            repository_root=repository_root,
            work_directory=build_root,
            specification_directory=specification_directory,
            release_directory=release_directory,
            source_file=(
                repository_root
                /
                "video_analyzer"
                /
                "batch_classifier.py"
            ),
            executable_name="BatchClassifier",
            windowed=False,
        )

        build_executable(
            repository_root=repository_root,
            work_directory=build_root,
            specification_directory=specification_directory,
            release_directory=release_directory,
            source_file=(
                repository_root
                /
                "video_analyzer"
                /
                "rebuild_sidecars.py"
            ),
            executable_name="RebuildSidecars",
            windowed=False,
        )

        tools_directory = (
            release_directory
            /
            "tools"
        )

        tools_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(
            ffmpeg_path,
            tools_directory
            /
            "ffmpeg.exe",
        )

        shutil.copy2(
            ffprobe_path,
            tools_directory
            /
            "ffprobe.exe",
        )

        readme_path = (
            repository_root
            /
            "README.md"
        )

        if readme_path.is_file():
            shutil.copy2(
                readme_path,
                release_directory
                /
                "README.md",
            )

        create_release_zip(
            release_directory,
            zip_path,
        )

        print()
        print("Windows release build complete.")
        print(
            f"Package: {release_directory}"
        )
        print(
            f"ZIP:     {zip_path}"
        )
        print()
        print(
            "Smoke-test Analyzer.exe, "
            "BatchClassifier.exe --help, and "
            "RebuildSidecars.exe --help before publishing."
        )

        return 0

    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        print()
        print(
            f"Windows build failed: {error}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
