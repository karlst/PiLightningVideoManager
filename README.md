# Video Camera Manager

**Video Camera Manager is a high-speed video capture and analysis system
designed to automatically detect, record, and analyze lightning
events.**

The current system uses a Raspberry Pi 4 and a high-speed USB camera for
unattended capture. A browser-based interface provides camera preview,
system status, and trigger controls. Captured events are saved as
approximately **2-second MP4 clips** with matching JSON metadata
sidecars.

On a Windows PC, the **Video Analyzer** provides frame-by-frame
playback, brightness graphs, trigger information, and automatic Solution
filtering. A **Batch Classifier** can process collections of captures
and sort them by classification.

## Try It First

You do **not** need to build a Raspberry Pi camera system to explore the
software.

Prospective users are encouraged to download the Windows Analyzer and
the supplied sample captures. The samples include true lightning flashes
as well as representative false positives. Open them in the Analyzer,
step through the clips frame-by-frame, inspect the brightness graphs and
trigger location, and see how the Solution filters classify each event.

Release downloads and sample captures will be available from the
repository's **Releases** page.

## Who Is It For?

Video Camera Manager is intended for people who want unattended
high-speed recording and verification of lightning events, including:

-   lightning and atmospheric researchers,
-   weather and storm observers,
-   lightning photographers and enthusiasts,
-   developers experimenting with high-speed camera capture and event
    detection.

The system is particularly useful when continuous high-speed recording
would generate too much data to retain. It continuously watches the
camera stream, saves only events that might contain lightning, and
performs more selective analysis after the clip has safely been
captured.

## Main Components

-   **`video_capture`** --- Runs continuously on the Raspberry Pi. It
    buffers high-speed camera frames, detects possible lightning events,
    and automatically saves approximately 2-second Candidate clips.
-   **Web interface** --- Provides camera preview for focus and aiming,
    system/capture status, and adjustment of Candidate trigger settings
    from a browser.
-   **`video_analyzer`** --- Runs on Windows. It opens saved captures
    for frame-by-frame playback, graphical inspection, Candidate replay,
    and Solution filtering.
-   **`batch_classifier`** --- Processes collections of saved
    Candidates, applies Solution filtering, and sorts MP4/JSON capture
    pairs into classification folders.
-   **`rebuild_sidecars`** --- Reconstructs missing JSON sidecars from
    saved MP4 files when recoverable capture information is available
    from the video.

# Design

The central design is deliberately a **two-stage process**:

**Candidate detection → Solution filtering**

The first stage is designed to avoid missing lightning. The second stage
is designed to remove false positives.

## Candidate and Solution

A **Candidate** is a saved video clip that **might contain a frame
showing lightning**.

A Candidate is not a declaration that lightning occurred. It means only
that the real-time `CandidateFinder` saw enough evidence to justify
preserving the surrounding video for later analysis.

A **Solution** is a Candidate that survives the desktop `SolutionFilter`
and is therefore classified as a likely true lightning flash.

False positives are expected at the Candidate stage. The system would
rather save an extra clip than discard a real lightning event before it
can be examined.

## Two-Stage Detection

### Stage 1 --- Find Candidates on the Raspberry Pi

`video_capture` receives high-speed camera frames continuously and keeps
a rolling buffer of recent frames.

Each incoming frame is evaluated by the shared `CandidateFinder`.
Candidate detection is intentionally lightweight because it must operate
in real time while the camera is running at high frame rates.

CandidateFinder can use measurements including:

-   mean frame brightness,
-   adjacent-frame brightness change,
-   fraction of pixels whose brightness changed significantly.

When a Candidate is detected, the capture pipeline saves a clip
containing frames from around the trigger, including frames that were
already in the ring buffer before the trigger.

The result is an **MP4/JSON pair**:

-   the `.mp4` contains the video,
-   the `.json` sidecar contains capture metadata, trigger information,
    CandidateFinder configuration, and per-frame measurements.

The Pi's job is therefore **capture-oriented**. It tries to preserve
anything that could plausibly be useful rather than performing expensive
final classification while frames are arriving.

### Stage 2 --- Apply Solution Filtering on the Desktop

`video_analyzer` loads the saved MP4 and its matching JSON sidecar.

The desktop `SolutionFilter` then performs the more selective
second-stage classification. Unlike the real-time CandidateFinder,
Solution filtering can examine the **entire saved clip**, including
behavior before and after the Candidate trigger.

This whole-clip context is important because many false positives cannot
be identified reliably from a single triggering frame. For example, a
brightness change may look interesting at the instant it occurs but
reveal itself over subsequent frames as noise, a dropped-frame anomaly,
or a persistent change in scene illumination.

The current SolutionFilter runs specialized rejection filters in
sequence, including filters for:

-   sustained brightness noise,
-   frame-dropout anomalies,
-   steady-state brightness changes.

If a filter identifies a known false-positive pattern, the Candidate is
rejected as a Solution. If the Candidate passes all Solution filters, it
is classified as a true flash.

## How `video_capture` and `video_analyzer` Work Together

The normal workflow is:

``` text
High-speed camera
        |
        v
video_capture on Raspberry Pi
        |
        | continuously buffers frames
        | CandidateFinder evaluates incoming frames
        v
Candidate detected
        |
        v
Save MP4 + JSON sidecar
        |
        v
video_analyzer on desktop
        |
        | load video and sidecar
        | replay/inspect CandidateFinder behavior
        | examine frame and brightness data
        | SolutionFilter examines the clip
        v
Solution or false positive
```

Both sides use the shared CandidateFinder implementation. This allows
the Analyzer to replay a saved capture using the same Candidate logic
used on the Pi and to experiment with different Candidate thresholds
without changing the original capture.

## Desktop Analyzer

The Analyzer is also a forensic and tuning tool. It provides:

-   frame-by-frame video navigation,
-   capture and current-frame information,
-   brightness and brightness-change graphs,
-   the original Pi trigger location,
-   CandidateFinder replay,
-   editable experimental Candidate settings,
-   SolutionFilter results,
-   editable experimental Solution-filter settings.

Changing settings in the Analyzer affects playback/reclassification
only. It does not alter the original Pi capture.

## Sidecars

Every normal capture has a JSON **sidecar** with the same basename as
the MP4.

For example:

``` text
trigger_20260809T120000Z.mp4
trigger_20260809T120000Z.json
```

The MP4 contains the encoded video. The sidecar preserves information
that is easier or more useful to retain separately, including
camera/capture metadata, trigger information, CandidateFinder
configuration, and per-frame measurements.

Together, the MP4 and JSON form the portable record of one Candidate
event.

## Design Principle

The project deliberately separates **fast detection** from **careful
classification**:

> Capture first. Analyze later.

Real-time detection should remain fast enough to protect the camera
capture pipeline. More expensive analysis belongs after the Candidate
has safely been recorded, where the entire clip is available and there
is no risk of losing incoming frames.

