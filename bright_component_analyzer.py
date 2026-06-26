"""
OpenCV analysis for bright and local-contrast connected components.

This module is used both for live frame metrics and for sidecar analysis
of captured frame lists.
"""

from __future__ import annotations

from pathlib import Path
import json

import cv2
import numpy as np

from cam_config import CamConfig
from camera_reader import CameraFrame


# ## Finds connected bright/local-contrast components and summarizes them.
#
#  A component is a connected group of candidate pixels. A valid component
#  is one that passes the configured area, height, and aspect-ratio filters.
class BrightComponentAnalyzer:

    # ## Store analysis configuration.
    def __init__(
        self,
        config: CamConfig
    ) -> None:
        self._config = config

    # ## Analyze one raw OpenCV frame and return component metrics.
    def analyze_frame(
        self,
        frame: np.ndarray
    ) -> dict:
        result = self._empty_frame_result()

        if self._config.opencv_enabled:
            gray_frame = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2GRAY
            )

            # Build a binary mask from absolute brightness and local contrast.
            candidate_mask = self._create_candidate_mask(
                gray_frame
            )

            # Count all components, then keep only lightning-like components.
            component_count, valid_components = (
                self._find_valid_components(
                    candidate_mask
                )
            )

            largest_component = self._get_largest_component(
                valid_components
            )

            result = {
                "component_count": component_count,
                "valid_component_count": len(valid_components),
                "max_component_area": largest_component["area"],
                "max_component_height": largest_component["height"],
                "max_component_width": largest_component["width"],
                "max_component_aspect": largest_component["aspect"]
            }

        return result

    # ## Analyze one CameraFrame wrapper.
    def analyze_camera_frame(
        self,
        camera_frame: CameraFrame
    ) -> dict:
        result = self.analyze_frame(
            camera_frame.frame
        )

        return result

    # ## Analyze a captured frame list and produce sidecar summary data.
    def analyze_frames(
        self,
        frames: list[CameraFrame],
        metadata: dict | None = None
    ) -> dict:
        component_count = 0
        valid_component_count = 0

        max_component_area = 0
        max_component_height = 0
        max_component_width = 0
        max_component_aspect = 0.0

        longest_event_frames = 0
        current_event_frames = 0
        missing_frame_count = 0

        # Analyze each captured frame using the same rules as live analysis.
        for camera_frame in frames:
            frame_result = self.analyze_camera_frame(
                camera_frame
            )

            component_count += int(
                frame_result["component_count"]
            )

            valid_count = int(
                frame_result["valid_component_count"]
            )

            valid_component_count += valid_count

            max_component_area = max(
                max_component_area,
                int(frame_result["max_component_area"])
            )

            max_component_height = max(
                max_component_height,
                int(frame_result["max_component_height"])
            )

            max_component_width = max(
                max_component_width,
                int(frame_result["max_component_width"])
            )

            max_component_aspect = max(
                max_component_aspect,
                float(frame_result["max_component_aspect"])
            )

            # Track the longest run of frames containing valid components.
            # Small gaps are allowed so one event is not split too easily.
            if valid_count > 0:
                current_event_frames += 1
                missing_frame_count = 0

            elif current_event_frames > 0:
                missing_frame_count += 1

                if (
                    missing_frame_count <=
                    self._config.opencv_event_max_missing_frames
                ):
                    current_event_frames += 1

                else:
                    current_event_frames -= missing_frame_count

                    longest_event_frames = max(
                        longest_event_frames,
                        current_event_frames
                    )

                    current_event_frames = 0
                    missing_frame_count = 0

        # Close the final event window if capture ended during an event.
        if current_event_frames > 0:
            current_event_frames -= missing_frame_count

            longest_event_frames = max(
                longest_event_frames,
                current_event_frames
            )

        longest_event_ms = (
            longest_event_frames *
            1000.0 /
            float(self._config.frame_rate_fps)
        )

        result = {
            "analysis_version": 2,
            "frame_count": len(frames),
            "component_count": component_count,
            "valid_component_count": valid_component_count,
            "max_component_area": max_component_area,
            "max_component_height": max_component_height,
            "max_component_width": max_component_width,
            "max_component_aspect": round(
                max_component_aspect,
                3
            ),
            "longest_event_ms": round(
                longest_event_ms,
                1
            ),
            "frame_records": self._create_frame_records(
                frames
            )
        }

        if metadata is not None:
            result.update(
                metadata
            )

        return result

    # ## Analyze captured frames and write the JSON sidecar next to the MP4.
    def write_sidecar(
        self,
        frames: list[CameraFrame],
        output_file: str | Path,
        metadata: dict | None = None
    ) -> dict:
        sidecar_data = self.analyze_frames(
            frames,
            metadata
        )

        sidecar_path = Path(
            output_file
        ).with_suffix(
            ".json"
        )

        sidecar_path.write_text(
            json.dumps(
                sidecar_data,
                indent=4
            ) + "\n",
            encoding="utf-8"
        )

        return sidecar_data

    # ## Build one lightweight timing record for every captured frame.
    def _create_frame_records(
        self,
        frames: list[CameraFrame]
    ) -> list[dict]:
        records: list[dict] = []

        first_monotonic = 0.0

        if len(frames) > 0:
            first_monotonic = frames[0].timestamp_monotonic

        for frame_index, camera_frame in enumerate(
            frames
        ):
            offset_ms = (
                (
                    camera_frame.timestamp_monotonic -
                    first_monotonic
                ) *
                1000.0
            )

            records.append(
                {
                    "frame_index": frame_index,
                    "sequence_number": camera_frame.sequence_number,
                    "timestamp_utc": camera_frame.timestamp_utc,
                    "offset_ms": round(
                        offset_ms,
                        3
                    )
                }
            )

        return records

    # ## Create a binary mask of pixels worth considering as component pixels.
    def _create_candidate_mask(
        self,
        gray_frame: np.ndarray
    ) -> np.ndarray:
        _, bright_mask = cv2.threshold(
            gray_frame,
            int(self._config.opencv_bright_threshold),
            255,
            cv2.THRESH_BINARY
        )

        window_pixels = self._get_odd_window_pixels(
            int(
                self._config.opencv_local_contrast_window_pixels
            )
        )

        # Estimate local background, then find pixels brighter than that
        # local neighborhood. This helps daylight lightning.
        background_frame = cv2.GaussianBlur(
            gray_frame,
            (window_pixels, window_pixels),
            0
        )

        contrast_frame = cv2.subtract(
            gray_frame,
            background_frame
        )

        _, contrast_mask = cv2.threshold(
            contrast_frame,
            int(self._config.opencv_local_contrast_threshold),
            255,
            cv2.THRESH_BINARY
        )

        candidate_mask = cv2.bitwise_or(
            bright_mask,
            contrast_mask
        )

        return candidate_mask

    # ## Find connected components and return the components passing filters.
    def _find_valid_components(
        self,
        candidate_mask: np.ndarray
    ) -> tuple[int, list[dict]]:
        component_total, labels, stats, centroids = (
            cv2.connectedComponentsWithStats(
                candidate_mask,
                connectivity=8
            )
        )

        component_count = max(
            0,
            int(component_total) - 1
        )

        valid_components: list[dict] = []

        # Label 0 is the background, so real components start at label 1.
        for label_index in range(
            1,
            component_total
        ):
            area = int(
                stats[
                    label_index,
                    cv2.CC_STAT_AREA
                ]
            )

            width = int(
                stats[
                    label_index,
                    cv2.CC_STAT_WIDTH
                ]
            )

            height = int(
                stats[
                    label_index,
                    cv2.CC_STAT_HEIGHT
                ]
            )

            aspect = (
                float(height) /
                max(
                    1.0,
                    float(width)
                )
            )

            if self._is_valid_component(
                area,
                height,
                aspect
            ):
                valid_components.append(
                    {
                        "area": area,
                        "height": height,
                        "width": width,
                        "aspect": aspect
                    }
                )

        result = (
            component_count,
            valid_components
        )

        return result

    # ## Decide whether a component is large and skinny enough to keep.
    def _is_valid_component(
        self,
        area: int,
        height: int,
        aspect: float
    ) -> bool:
        is_valid = (
            area >= self._config.opencv_min_component_area and
            height >= self._config.opencv_min_component_height and
            aspect >= self._config.opencv_min_component_aspect
        )

        return is_valid

    # ## Find the largest component by area, or return zero values if none.
    def _get_largest_component(
        self,
        components: list[dict]
    ) -> dict:
        largest_component = {
            "area": 0,
            "height": 0,
            "width": 0,
            "aspect": 0.0
        }

        if len(components) > 0:
            largest_component = max(
                components,
                key=lambda item: item["area"]
            )

        return largest_component

    # ## Return zero-valued metrics for disabled analysis or empty results.
    def _empty_frame_result(
        self
    ) -> dict:
        result = {
            "component_count": 0,
            "valid_component_count": 0,
            "max_component_area": 0,
            "max_component_height": 0,
            "max_component_width": 0,
            "max_component_aspect": 0.0
        }

        return result

    # ## Force the local contrast window to be odd and at least 3 pixels.
    def _get_odd_window_pixels(
        self,
        value: int
    ) -> int:
        window_pixels = max(
            3,
            value
        )

        if window_pixels % 2 == 0:
            window_pixels += 1

        return window_pixels
