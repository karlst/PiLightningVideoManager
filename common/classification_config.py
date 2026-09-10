"""Configuration for the production capture classifier."""

# Recall-oriented cutoff selected by cross-validation on the original training set.
# This is policy, not a trained model parameter, so it may be changed without retraining.
CLASSIFICATION_FLASH_CONFIDENCE_THRESHOLD = 0.30
