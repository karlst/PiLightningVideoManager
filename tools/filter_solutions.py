"""
@file filter_solutions.py

@brief Command-line entry point for batch SolutionFilter classification.

The reusable classification engine lives in common.solution_batch so the same
logic can be called by this tool and by the Pi SolutionFilter service.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from common.candidate_config import CANDIDATE_CONFIG
from common.candidate_config import CandidateConfig
from common.candidate_config import candidate_config_from_settings
from common.candidate_config import load_candidate_settings
from common.solution_batch import run_batch_solution_filter


# ## Build an optional one-run sensitivity override without changing the JSON file.
def build_candidate_config(
    sensitivity: str | None,
) -> CandidateConfig:
    if sensitivity is None:
        return CANDIDATE_CONFIG

    settings = (
        load_candidate_settings()
    )

    settings[
        "sensitivity"
    ] = sensitivity

    return candidate_config_from_settings(
        settings
    )


# ## Always report the effective CandidateFinder settings for this batch run.
def print_candidate_config(
    config: CandidateConfig,
    find_candidates: bool,
) -> None:
    mode_text = (
        "used for CandidateFinder replay"
        if find_candidates
        else "reported only; normal batch trusts sidecar trigger"
    )

    print(
        "CandidateFinder settings "
        f"({mode_text}):"
    )

    print(
        f"  Sensitivity: "
        f"{config.sensitivity}"
    )

    print(
        f"  Brightness delta threshold: "
        f"{config.candidate_brightness_delta_threshold:.3f}"
    )

    print(
        f"  Bright pixel delta threshold: "
        f"{config.candidate_bright_pixel_delta_threshold:.1f}"
    )

    print(
        f"  Bright pixel fraction threshold: "
        f"{config.candidate_bright_pixel_fraction_threshold:.6f}"
    )

    print()


# ## Parse command-line arguments and run SolutionFilter classification.
def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Classify saved Candidate captures using "
            "sidecar brightness data and SolutionFilter."
        )
    )

    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing MP4 captures and JSON sidecars",
    )

    parser.add_argument(
        "-v",
        "--verbosity",
        type=int,
        default=0,
        choices=[0, 1, 2],
        help=(
            "Verbosity: 0=quiet (default), "
            "1=one line per capture, "
            "2=reserved for detailed diagnostics"
        ),
    )

    parser.add_argument(
        "--copy",
        action="store_true",
        help=(
            "Copy classified MP4/JSON pairs instead of moving or renaming "
            "them. Useful for repeated experimental runs."
        ),
    )

    parser.add_argument(
        "--delete-rejects",
        action="store_true",
        help=(
            "Pi production mode: rename TRUE_FLASH pairs in place from "
            "trigger_* to flash_* and delete all rejected pairs."
        ),
    )

    parser.add_argument(
        "--findCandidates",
        action="store_true",
        help=(
            "Rerun CandidateFinder using CandidateConfig before "
            "SolutionFilter. This decodes MP4 files and is much slower than "
            "the normal sidecar-only path."
        ),
    )

    parser.add_argument(
        "--sensitivity",
        choices=[
            "high",
            "medium",
            "low",
        ],
        default=None,
        help=(
            "Override CandidateFinder sensitivity for this batch run only. "
            "Does not modify candidate_config.json. "
            "If omitted, use the current shared CandidateConfig."
        ),
    )

    arguments = parser.parse_args()

    try:
        candidate_config = (
            build_candidate_config(
                arguments.sensitivity
            )
        )

        print_candidate_config(
            candidate_config,
            arguments.findCandidates,
        )

        return run_batch_solution_filter(
            arguments.folder,
            verbosity=arguments.verbosity,
            copy_only=arguments.copy,
            delete_rejects=arguments.delete_rejects,
            find_candidates=arguments.findCandidates,
            candidate_config=candidate_config,
        )

    except (
        OSError,
        RuntimeError,
    ) as error:
        print(
            f"Batch classification failed: {error}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
