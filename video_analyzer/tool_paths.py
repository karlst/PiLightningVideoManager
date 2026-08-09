"""
@file tool_paths.py

@brief Locate external command-line tools used by the desktop applications.

The Windows release includes FFmpeg utilities in a "tools" directory beside
the distributed executables:

    VideoManager-vX.Y-Windows/
        Analyzer.exe
        BatchClassifier.exe
        RebuildSidecars.exe
        tools/
            ffmpeg.exe
            ffprobe.exe

Users should not have to install FFmpeg or modify PATH.

During normal source-code development, however, developers may already have
ffmpeg/ffprobe installed on PATH. resolve_external_tool() therefore searches
the packaged release location first and falls back to PATH for development.

This module is shared by Analyzer and RebuildSidecars so both programs use
exactly the same tool-location rules.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import sys


# ## Return the absolute path to a bundled external tool, with PATH as a development fallback.
def resolve_external_tool(
    tool_name: str,
) -> str:
    executable_name = tool_name

    if sys.platform == "win32" and not executable_name.lower().endswith(".exe"):
        executable_name += ".exe"

    # When running from a PyInstaller executable, sys.executable is the EXE
    # itself. The release's tools directory lives beside that executable.
    if getattr(
        sys,
        "frozen",
        False,
    ):
        bundled_candidate = (
            Path(sys.executable).resolve().parent
            /
            "tools"
            /
            executable_name
        )

        if bundled_candidate.is_file():
            return str(
                bundled_candidate
            )

    # During source-code development, also support a tools directory at the
    # repository root. This is optional; PATH remains a convenient fallback.
    source_candidate = (
        Path(__file__).resolve().parents[1]
        /
        "tools"
        /
        executable_name
    )

    if source_candidate.is_file():
        return str(
            source_candidate
        )

    path_candidate = shutil.which(
        executable_name
    )

    if path_candidate is not None:
        return path_candidate

    raise RuntimeError(
        f"{executable_name} was not found. "
        "The distributed application expects it in the "
        "'tools' folder beside the executable."
    )
