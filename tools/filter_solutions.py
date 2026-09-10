"""
@file filter_solutions.py

@brief Command-line entry point for the V8 logistic FLASH/ANOMALY classifier.

The reusable production workflow lives in common.solution_batch.  Current V8
sidecars are required.  Normal classification trusts the Candidate trigger
saved by the Pi and uses only sidecar brightness data.  The legacy
SolutionFilter is not used.  FLASH candidates remain unverified for human
review; ANOMALY captures are algorithmically verified.  Use --findCandidates
only for experimental CandidateFinder replay against the MP4.
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


def build_candidate_config(sensitivity: str | None) -> CandidateConfig:
    if sensitivity is None:
        return CANDIDATE_CONFIG
    settings = load_candidate_settings()
    settings["sensitivity"] = sensitivity
    return candidate_config_from_settings(settings)


def print_candidate_config(config: CandidateConfig, find_candidates: bool) -> None:
    mode_text = (
        "used for CandidateFinder replay"
        if find_candidates
        else "reported only; normal batch trusts sidecar trigger"
    )
    print(f"CandidateFinder settings ({mode_text}):")
    print(f"  Sensitivity: {config.sensitivity}")
    print(
        "  Brightness delta threshold: "
        f"{config.candidate_brightness_delta_threshold:.3f}"
    )
    print(
        "  Bright pixel delta threshold: "
        f"{config.candidate_bright_pixel_delta_threshold:.1f}"
    )
    print(
        "  Bright pixel fraction threshold: "
        f"{config.candidate_bright_pixel_fraction_threshold:.6f}"
    )
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Classify saved Candidate captures as FLASH or ANOMALY using the "
            "frozen logistic-regression model."
        )
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing MP4 captures and V8 JSON sidecars",
    )
    parser.add_argument(
        "-v",
        "--verbosity",
        type=int,
        default=0,
        choices=[0, 1, 2],
        help="Verbosity: 0=quiet, 1=one line per capture, 2=replay diagnostics",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="Copy classified MP4/JSON pairs into FLASH/ANOMALY folders.",
    )
    parser.add_argument(
        "--move-to-subfolders",
        action="store_true",
        help="Move classified anomaly pairs into the anomalies subfolder.",
    )
    parser.add_argument(
        "--delete-rejects",
        action="store_true",
        help="Pi production mode: retain FLASH pairs and delete ANOMALY pairs.",
    )
    parser.add_argument(
        "--findCandidates",
        action="store_true",
        help=(
            "Rerun CandidateFinder before classification. This decodes MP4 "
            "files and is much slower than the normal sidecar-only path."
        ),
    )
    parser.add_argument(
        "--sensitivity",
        choices=["high", "medium", "low"],
        default=None,
        help=(
            "Override CandidateFinder sensitivity for this replay run only. "
            "Does not affect the logistic classifier."
        ),
    )

    arguments = parser.parse_args()

    try:
        candidate_config = build_candidate_config(arguments.sensitivity)
        print_candidate_config(candidate_config, arguments.findCandidates)
        return run_batch_solution_filter(
            arguments.folder,
            verbosity=arguments.verbosity,
            copy_only=arguments.copy,
            delete_rejects=arguments.delete_rejects,
            move_to_subfolders=arguments.move_to_subfolders,
            find_candidates=arguments.findCandidates,
            candidate_config=candidate_config,
        )
    except (OSError, RuntimeError) as error:
        print(f"Batch classification failed: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
