"""Replay archived Pi frame metrics through the shared CandidateFinder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from common.candidate_config import CANDIDATE_CONFIG
from common.candidate_config import CandidateConfig
from common.candidate_finder import CandidateFinder


@dataclass(frozen=True)
class CandidateReplayResult:
    frame_index: int | None
    reason: str

    @property
    def found(self) -> bool:
        return self.frame_index is not None


def replay_candidate_finder(
    sidecar: dict[str, Any] | None,
    config: CandidateConfig = CANDIDATE_CONFIG,
) -> CandidateReplayResult:
    """Return the first trigger frame found using the supplied config."""

    candidate_finder = CandidateFinder(
        config
    )

    if sidecar is None:
        return CandidateReplayResult(
            frame_index=None,
            reason="",
        )

    frame_records = sidecar.get(
        "frame_records",
        [],
    )

    if not isinstance(frame_records, list):
        return CandidateReplayResult(
            frame_index=None,
            reason="",
        )

    for list_index, record in enumerate(frame_records):
        if not isinstance(record, dict):
            continue

        metric = {
            "mean_brightness": _float_value(
                record.get("mean_brightness"),
                0.0,
            ),
            "brightness_delta_adjacent": _float_value(
                record.get("brightness_delta_adjacent"),
                0.0,
            ),
            "changed_pixel_fraction": _float_value(
                record.get("changed_pixel_fraction"),
                0.0,
            ),
        }

        found, reason = candidate_finder.evaluate(
            metric
        )

        if found:
            try:
                frame_index = int(
                    record.get("frame_index", list_index)
                )
            except (TypeError, ValueError):
                frame_index = list_index

            return CandidateReplayResult(
                frame_index=frame_index,
                reason=reason,
            )

    return CandidateReplayResult(
        frame_index=None,
        reason="",
    )


def _float_value(
    value: Any,
    default: float,
) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
