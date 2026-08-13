#!/usr/bin/env bash
#
# solutionFilterStressTest.sh
#
# Repeatedly runs BatchClassifier in --copy mode, deletes the classification
# subfolders it created, waits one second, and repeats.
#
# Usage:
#   ./solutionFilterStressTest.sh /path/to/candidate/folder
#
# Run this from the repository root so:
#   python3 -m video_analyzer.batch_classifier
# resolves correctly.
#

set -u

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 /path/to/candidate/folder"
    exit 1
fi

CANDIDATE_DIR="$1"

if [ ! -d "$CANDIDATE_DIR" ]; then
    echo "Candidate folder not found: $CANDIDATE_DIR"
    exit 1
fi

# These are the subfolders created by the current BatchClassifier.
CLASSIFICATION_DIRS=(
    "true_flashes"
    "frame_dropout_anomalies"
    "bright_noise_anomalies"
    "steady_state_anomalies"
    "unclassified"
)

iteration=0

cleanup() {
    echo
    echo "Stopping stress test."
    exit 0
}

trap cleanup INT TERM

echo "Candidate folder: $CANDIDATE_DIR"
echo "Press Ctrl-C to stop."
echo

while true; do
    iteration=$((iteration + 1))

    candidate_count=$(find "$CANDIDATE_DIR" -maxdepth 1 -type f -name '*.mp4' | wc -l)

    start_ns=$(date +%s%N)

    python3 -m video_analyzer.batch_classifier \
        "$CANDIDATE_DIR" \
        --copy \
        --verbosity 0

    status=$?

    end_ns=$(date +%s%N)
    elapsed_ms=$(( (end_ns - start_ns) / 1000000 ))

    if [ "$status" -ne 0 ]; then
        echo "Iteration $iteration FAILED (exit $status)"
        exit "$status"
    fi

    printf "Iteration %d: %d candidates, batch time %d ms\n" \
        "$iteration" \
        "$candidate_count" \
        "$elapsed_ms"

    for folder in "${CLASSIFICATION_DIRS[@]}"; do
        rm -rf -- "$CANDIDATE_DIR/$folder"
    done

    sleep 1
done
