"""Launch Vce and Vfa from the same installed VideoManager directory as CCM."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def application_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(sys.argv[0]).resolve().parent


def sibling_executable(tool_name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return application_directory() / f"{tool_name}{suffix}"


def launch_tool(tool_name: str, capture_path: Path) -> None:
    executable = sibling_executable(tool_name)
    if not executable.is_file():
        raise RuntimeError(
            f"{tool_name} was not found beside CCM:\n{executable}\n\n"
            "Install the complete VideoManager suite or launch from the installed folder."
        )

    subprocess.Popen([str(executable), str(capture_path)])
