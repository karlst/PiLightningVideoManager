from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT_DIRECTORY = Path(__file__).resolve().parent

SPEC_FILE = ROOT_DIRECTORY / "Vfa.spec"

BUILD_DIRECTORY = ROOT_DIRECTORY / "build"
DIST_DIRECTORY = ROOT_DIRECTORY / "dist"

DIST_VFA_DIRECTORY = DIST_DIRECTORY / "Vfa"

INSTALL_DIRECTORY = (
    Path.home()
    / "bin"
    / "Vfa"
)


def run_pyinstaller() -> None:
    print("Building Vfa...")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(SPEC_FILE),
        ],
        cwd=ROOT_DIRECTORY,
        check=True,
    )

    executable = (
        DIST_VFA_DIRECTORY
        / "Vfa.exe"
    )

    if not executable.is_file():
        raise RuntimeError(
            f"Build completed but Vfa.exe was not found: "
            f"{executable}"
        )

    print(
        f"Build complete: {executable}"
    )


def clean() -> None:
    if BUILD_DIRECTORY.exists():
        print(
            f"Removing {BUILD_DIRECTORY}"
        )

        shutil.rmtree(
            BUILD_DIRECTORY
        )

    if DIST_DIRECTORY.exists():
        print(
            f"Removing {DIST_DIRECTORY}"
        )

        shutil.rmtree(
            DIST_DIRECTORY
        )

    print("Clean complete.")


def install() -> None:
    if not DIST_VFA_DIRECTORY.is_dir():
        print(
            "No Vfa build found; building first."
        )

        run_pyinstaller()

    if INSTALL_DIRECTORY.exists():
        print(
            f"Removing existing install: "
            f"{INSTALL_DIRECTORY}"
        )

        shutil.rmtree(
            INSTALL_DIRECTORY
        )

    INSTALL_DIRECTORY.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        f"Installing Vfa to: "
        f"{INSTALL_DIRECTORY}"
    )

    shutil.copytree(
        DIST_VFA_DIRECTORY,
        INSTALL_DIRECTORY,
    )

    executable = (
        INSTALL_DIRECTORY
        / "Vfa.exe"
    )

    if not executable.is_file():
        raise RuntimeError(
            f"Install failed; Vfa.exe was not found: "
            f"{executable}"
        )

    print(
        f"Install complete: {executable}"
    )


def main() -> int:
    command = "build"

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

    try:
        if command == "build":
            run_pyinstaller()

        elif command == "clean":
            clean()
            run_pyinstaller()

        elif command == "install":
            run_pyinstaller()
            install()

        elif command == "clean-install":
            clean()
            run_pyinstaller()
            install()

        else:
            print(
                "Usage:"
            )
            print(
                "  python build.py"
            )
            print(
                "  python build.py build"
            )
            print(
                "  python build.py clean"
            )
            print(
                "  python build.py install"
            )
            print(
                "  python build.py clean-install"
            )

            return 1

    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as error:
        print(
            f"Build failed: {error}"
        )

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )