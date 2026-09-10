"""
@file classification_model.py

@brief Production FLASH-versus-ANOMALY classifier for saved Pi Camera captures.

This module contains the fixed feature extraction and generic logistic-regression
calculation used in production. Trained parameters are deliberately isolated in
common.models.logistic_v1 so a future retrained model can be added as a new file
without rewriting the classifier algorithm.

Classification uses only the per-frame brightness measurements and recorded
trigger frame already present in the JSON sidecar. No MP4 decoding and no
legacy SolutionFilter rules are required.

The decision threshold lives separately in classification_config.py because it
is operating policy rather than a trained parameter.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from common.classification_config import CLASSIFICATION_FLASH_CONFIDENCE_THRESHOLD
from common.models.logistic_v1 import MODEL_FEATURES, MODEL_INTERCEPT, MODEL_NAME


CLASSIFICATION_FLASH = "FLASH"
CLASSIFICATION_ANOMALY = "ANOMALY"
CLASSIFICATION_MODEL_NAME = MODEL_NAME


# Frozen feature order used during feature extraction. Do not reorder or alter.
# The model file is keyed by these names, so scaler/coefficient values cannot
# silently drift out of alignment with their features.
FEATURE_NAMES = (
    "pos_after_ratio",      # Positive post-rise brightness-change activity / main rise magnitude.
    "recovery4_ratio",      # Negative recovery in the first four frames after the main rise / rise.
    "neg_pos_ratio",        # Total negative recovery after the main rise / rise magnitude.
    "pre_slope",            # Linear slope of brightness during the 30 frames before the trigger.
    "dpre_std",             # Standard deviation of brightness change during 100 pre-trigger frames.
    "trigger_delta",        # Adjacent-frame brightness change at the recorded trigger frame.
    "post_dev_max",         # Largest positive post-trigger departure from the pre-trigger baseline.
    "post_std",             # Standard deviation of brightness during 150 post-trigger frames.
    "post_dev_min",         # Largest negative post-trigger departure from the pre-trigger baseline.
    "cnt_abs05",            # Number of clip frames with absolute brightness change >= 0.5.
    "global_range",         # Full-clip brightness range: maximum minus minimum brightness.
    "pre_std",              # Standard deviation of brightness during 100 pre-trigger frames.
    "cnt_pos1",             # Number of clip frames with brightness change >= +1.0.
    "dd_q99",               # 99th percentile of adjacent-frame brightness change over the clip.
    "cnt_abs1",             # Number of clip frames with absolute brightness change >= 1.0.
    "post_absdev_mean",     # Mean absolute post-trigger departure from the pre-trigger baseline.
    "pre_mad",              # Median absolute deviation of brightness during 100 pre-trigger frames.
    "global_std",           # Standard deviation of brightness over the complete capture.
    "post30_shift",         # Mean first-30 post-trigger brightness minus pre-trigger baseline.
    "cnt_neg1",             # Number of clip frames with brightness change <= -1.0.
)


def _model_arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    missing = [name for name in FEATURE_NAMES if name not in MODEL_FEATURES]
    extra = [name for name in MODEL_FEATURES if name not in FEATURE_NAMES]
    if missing or extra:
        raise RuntimeError(
            f"Model feature mismatch; missing={missing}, extra={extra}"
        )

    means = np.asarray(
        [MODEL_FEATURES[name][0] for name in FEATURE_NAMES],
        dtype=np.float64,
    )
    scales = np.asarray(
        [MODEL_FEATURES[name][1] for name in FEATURE_NAMES],
        dtype=np.float64,
    )
    coefficients = np.asarray(
        [MODEL_FEATURES[name][2] for name in FEATURE_NAMES],
        dtype=np.float64,
    )

    if np.any(scales == 0.0):
        raise RuntimeError("Classifier model contains a zero feature scale")

    return means, scales, coefficients


_MODEL_MEANS, _MODEL_SCALES, _MODEL_COEFFICIENTS = _model_arrays()


@dataclass(frozen=True)
class ClassificationResult:
    classification: str
    flash_probability: float
    reason: str


def _median_absolute_deviation(values: np.ndarray) -> float:
    finite_values = values[np.isfinite(values)]
    if finite_values.size == 0:
        return 0.0
    median = float(np.median(finite_values))
    return float(np.median(np.abs(finite_values - median)))


def _finite_quantile(values: np.ndarray, quantile: float) -> float:
    finite_values = values[np.isfinite(values)]
    if finite_values.size == 0:
        return 0.0
    return float(np.quantile(finite_values, quantile))


# Step 2 - Extract the exact 20 engineered features used during model training.
def build_classification_features(
    brightness: np.ndarray,
    brightness_delta: np.ndarray,
    trigger_frame_index: int,
) -> np.ndarray:
    brightness = np.asarray(brightness, dtype=np.float64)
    brightness_delta = np.asarray(brightness_delta, dtype=np.float64)

    if (
        brightness.size == 0
        or brightness_delta.size == 0
        or brightness.size != brightness_delta.size
    ):
        raise RuntimeError(
            "Classifier requires equal non-empty brightness arrays"
        )

    trigger_index = int(trigger_frame_index)
    if not 0 <= trigger_index < brightness.size:
        raise RuntimeError("Classifier trigger frame is outside capture")

    pre = brightness[max(0, trigger_index - 100):trigger_index]
    pre30 = brightness[max(0, trigger_index - 30):trigger_index]
    post = brightness[trigger_index:min(brightness.size, trigger_index + 150)]
    post30 = brightness[trigger_index:min(brightness.size, trigger_index + 30)]
    dpre = brightness_delta[max(0, trigger_index - 100):trigger_index]

    near_start = max(0, trigger_index - 10)
    near_stop = min(brightness_delta.size, trigger_index + 51)
    near = brightness_delta[near_start:near_stop]

    baseline = (
        float(np.median(pre30))
        if pre30.size > 0
        else float(brightness[trigger_index])
    )

    pre_slope = 0.0
    if pre30.size >= 2:
        pre_x = np.arange(pre30.size, dtype=np.float64)
        pre_slope = float(np.polyfit(pre_x, pre30, 1)[0])

    if near.size > 0:
        near_peak_index = int(np.argmax(near))
        global_peak_index = near_start + near_peak_index
        rise = float(brightness_delta[global_peak_index])
    else:
        global_peak_index = trigger_index
        rise = float(brightness_delta[trigger_index])

    after = brightness_delta[
        global_peak_index + 1:min(brightness_delta.size, global_peak_index + 41)
    ]

    if after.size > 0:
        negative_after = after[after < 0.0]
        positive_after = after[after > 0.0]
        cumulative_negative = float(-np.sum(negative_after))
        cumulative_positive = float(np.sum(positive_after))
        first_four = after[:4]
        recovery4 = float(-np.sum(first_four[first_four < 0.0]))
    else:
        cumulative_negative = 0.0
        cumulative_positive = 0.0
        recovery4 = 0.0

    denominator = abs(rise) + 1.0e-6
    post_deviation = post - baseline

    features = np.asarray(
        (
            cumulative_positive / denominator,
            recovery4 / denominator,
            cumulative_negative / denominator,
            pre_slope,
            float(np.std(dpre)) if dpre.size > 0 else 0.0,
            float(brightness_delta[trigger_index]),
            float(np.max(post_deviation)) if post_deviation.size > 0 else 0.0,
            float(np.std(post)) if post.size > 0 else 0.0,
            float(np.min(post_deviation)) if post_deviation.size > 0 else 0.0,
            float(np.sum(np.abs(brightness_delta) >= 0.5)),
            float(np.ptp(brightness)),
            float(np.std(pre)) if pre.size > 0 else 0.0,
            float(np.sum(brightness_delta >= 1.0)),
            _finite_quantile(brightness_delta, 0.99),
            float(np.sum(np.abs(brightness_delta) >= 1.0)),
            (
                float(np.mean(np.abs(post_deviation)))
                if post_deviation.size > 0
                else 0.0
            ),
            _median_absolute_deviation(pre),
            float(np.std(brightness)),
            float(np.mean(post30) - baseline) if post30.size > 0 else 0.0,
            float(np.sum(brightness_delta <= -1.0)),
        ),
        dtype=np.float64,
    )

    if not np.all(np.isfinite(features)):
        raise RuntimeError("Classifier produced non-finite feature values")

    return features


def classification_diagnostics(
    brightness: np.ndarray,
    brightness_delta: np.ndarray,
    trigger_frame_index: int,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Return features, standardized features, logit, P(FLASH) for regression tests."""
    # Step 2 - Extract the 20 measurements from the brightness time series.
    features = build_classification_features(
        brightness,
        brightness_delta,
        trigger_frame_index,
    )

    # Step 3 - Standardize each feature with the selected model's frozen scaler.
    standardized = (features - _MODEL_MEANS) / _MODEL_SCALES

    # Step 4 - Form the logistic-regression weighted sum plus its intercept.
    logit = float(MODEL_INTERCEPT + np.dot(standardized, _MODEL_COEFFICIENTS))

    # Step 5 - Convert the raw logit to the model probability P(FLASH).
    if logit >= 0.0:
        flash_probability = 1.0 / (1.0 + np.exp(-logit))
    else:
        exp_logit = np.exp(logit)
        flash_probability = exp_logit / (1.0 + exp_logit)

    return features, standardized, logit, float(flash_probability)


def classify_arrays(
    brightness: np.ndarray,
    brightness_delta: np.ndarray,
    trigger_frame_index: int,
) -> ClassificationResult:
    """Classify one capture as FLASH or ANOMALY using the selected model."""
    # Step 1 - The caller supplies brightness arrays and the recorded trigger.
    _features, _standardized, _logit, flash_probability = classification_diagnostics(
        brightness,
        brightness_delta,
        trigger_frame_index,
    )

    # Step 6 - Apply the configured operating threshold to P(FLASH).
    threshold = CLASSIFICATION_FLASH_CONFIDENCE_THRESHOLD
    classification = (
        CLASSIFICATION_FLASH
        if flash_probability >= threshold
        else CLASSIFICATION_ANOMALY
    )

    return ClassificationResult(
        classification=classification,
        flash_probability=flash_probability,
        reason=(
            f"{CLASSIFICATION_MODEL_NAME} {classification} "
            f"p_flash={flash_probability:.4f}; threshold={threshold:.2f}"
        ),
    )
