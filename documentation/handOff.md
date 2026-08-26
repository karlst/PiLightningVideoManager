# Pi Camera Capture --- ChatGPT Handoff

## Purpose

This is a developer handoff document, not end-user documentation.

Its purpose is to let a new developer understand the
current architecture and the important design decisions.

## Project Goal

Detect, capture, and analyze lightning with a Raspberry Pi and a
high-speed camera while minimizing the chance of missing a real event.

The project intentionally separates real-time capture from more
expensive post-capture classification.

Machine learning is not currently part of the design.

## Core Architecture: Candidate First, Solution Second

The most important architectural concept is the **two-stage detection
process**.

### Candidate

A **Candidate** is a saved video clip that might contain a frame showing
lightning.

CandidateFinder does **not** attempt to prove that lightning occurred.
Its job is to recognize an event that is sufficiently interesting to
preserve for later analysis.

False positives at this stage are acceptable. Missing a real lightning
event is much worse than saving an unnecessary clip.

### Solution

A **Solution** is a Candidate that passes the desktop `SolutionFilter`
and is classified as a likely true lightning flash.

Solution filtering is deliberately separate from real-time Candidate
detection. It can use the **entire saved clip**, including frames before
and after the trigger, to identify false-positive patterns that cannot
be recognized reliably from the triggering frame alone.

The conceptual pipeline is:

``` text
Camera frames
    |
    v
CandidateFinder                  real time, Raspberry Pi
    |
    v
Candidate MP4 + JSON sidecar
    |
    v
SolutionFilter                   post-capture, desktop
    |
    +---- false positive
    |
    v
Solution / true flash
```

The short version is:

**CandidateFinder asks whether to save. SolutionFilter asks whether the
saved Candidate is really lightning.**

## `video_capture`

`video_capture` runs on the Raspberry Pi.

Its responsibilities include:

-   reading the high-speed camera,
-   maintaining a continuously running ring buffer,
-   calculating the lightweight metrics needed for real-time Candidate
    detection,
-   running CandidateFinder,
-   preserving pre-trigger and post-trigger frames,
-   writing Candidate clips as H.264 MP4 files,
-   writing matching JSON sidecars,
-   serving the web interface,
-   managing saved captures.

The trigger path must remain lightweight enough to run continuously
without interfering with high-speed capture.

### CandidateFinder

CandidateFinder is shared code used by both the Pi capture application
and the desktop Analyzer.

It evaluates per-frame metrics and returns when a Candidate trigger
condition is met. Current Candidate measurements include mean
brightness, adjacent-frame brightness change, and changed/bright-pixel
fraction measurements.

Because the same CandidateFinder is used on both sides, the Analyzer can
replay a capture with the same algorithm used by the Pi.

## Ring Buffer and Capture

The ring buffer runs continuously and retains the most recent camera
frames.

When CandidateFinder triggers, the saved Candidate contains a window
around that event rather than beginning only after detection. This
preserves the frames leading into the event as well as the trigger and
post-trigger frames.

The trigger frame must remain identifiable in the saved capture.

## Capture Writer Architecture and Timing

This is a critical implementation detail. Do not simplify the capture path by
moving file writing back into `CameraReader` or its frame callback.

The camera currently runs at roughly 260 FPS, leaving about 3.8 ms between
frames. Timing tests showed that FFmpeg encoding could consume enough CPU to
starve camera acquisition and create large gaps in the frame timestamps. The
current architecture was introduced specifically to prevent that failure mode.

### Automatic capture tasking

Automatic captures use three execution contexts:

1. **CameraReader Python thread** --- performs `camera.read()`, timestamps the
   frame, and calls `BufferManager._on_frame()`. This is the time-critical path.
2. **CaptureWriter Python thread** --- consumes queued automatic capture jobs and
   performs MP4 + sidecar writing. There is exactly one worker so automatic
   encodes are serialized rather than competing with one another.
3. **FFmpeg OS process** --- launched synchronously by `ClipWriter.write_frames()`
   from the CaptureWriter thread. FFmpeg being a separate process does *not* make
   `write_frames()` asynchronous; the caller still feeds stdin and waits for
   FFmpeg to exit.

When an automatic Candidate triggers, BufferManager first waits for
`post_trigger_seconds` so the ring buffer contains the required later frames. It
then takes a snapshot of the ring-buffer frame references and places that fixed
frame list on `_capture_queue`. Queue insertion is intentionally cheap.

CaptureWriter does not necessarily encode immediately. It waits until:

``` text
original trigger monotonic time + capture_write_delay_seconds
```

If that time has already passed, it starts immediately. The delay is therefore
relative to the original trigger, **not** relative to queue insertion.

Current tested configuration is a 2-second write delay. Capture writing itself
was measured at roughly 1.8 seconds on the current Pi/camera configuration. The
trigger cooldown was increased to keep captures from being initiated too close
together; see `cam_config.py` for the current values rather than duplicating
configuration constants here.

### Manual captures

Manual `BufferManager.capture()` remains synchronous. Both manual and automatic
writes pass through `_capture_write_lock`, so ClipWriter and SidecarWriter cannot
be used concurrently. A manual capture can therefore wait behind an automatic
write, or vice versa. This is intentional; protecting camera acquisition is more
important than maximizing file-write concurrency.

### FFmpeg tasking choices

`ClipWriter` currently launches FFmpeg with:

- `nice -n 5` --- modestly lowers FFmpeg CPU scheduling priority;
- `-threads 1` --- limits libx264 encoding workers;
- `-preset ultrafast` --- minimizes encoding CPU cost;
- **no `taskset`/CPU affinity** --- affinity experiments did not provide a
  compelling improvement, so Linux is allowed to schedule normally.

`-threads 1` does not mean process monitors will show exactly one FFmpeg thread.
FFmpeg can create additional framework/I/O threads; the option constrains codec
threading.

### Result of the timing work

Before these changes, capture-associated encoding produced substantial frame
timestamp gaps. After moving automatic writing to CaptureWriter, delaying the
write, and constraining FFmpeg, production sidecars showed frame intervals
clustered near the expected camera cadence with no sequence-number
discontinuities in the validation sample. Treat this architecture as a
performance requirement unless new measurements demonstrate that it can safely
be changed.

## MP4 and JSON Sidecar

A normal Candidate consists of a matching pair:

trigger_<timestamp>.mp4
trigger_<timestamp>.json


The MP4 contains the encoded video.

The JSON file is a **sidecar**: a separate metadata file that
accompanies the video. It preserves information such as
application/configuration, camera and capture metadata,
Candidate trigger information, CandidateFinder settings, and per-frame
measurements.

The MP4/JSON pair should be treated as one portable capture record.

Sidecars should contain measured facts and provenance rather than
speculative classifications. Final Solution classification belongs to
the Analyzer.

`rebuild_sidecars.py` exists to reconstruct missing sidecars from MP4
files where possible. Reconstruction cannot recover information that
existed only on the Pi at capture time, so unrecoverable values must not
be fabricated.

## `video_analyzer`

`video_analyzer` is the desktop forensic-analysis application.

It loads a saved MP4 and matching JSON sidecar and provides:

-   random-access frame-by-frame playback,
-   capture metadata,
-   current-frame metadata,
-   brightness graphs,
-   original Pi trigger display,
-   CandidateFinder replay,
-   experimental Candidate threshold changes,
-   SolutionFilter classification,
-   experimental Solution-filter settings.

The Analyzer can reconstruct some measurements from the encoded MP4 when
necessary, but original Pi sidecar measurements are preferred when
available.

Changes made in Analyzer settings are experimental playback settings.
They do not modify the original capture.

## Candidate Replay

The Analyzer replays archived/reconstructed frame metrics through the
shared CandidateFinder.

This serves two purposes:

1.  verify or compare the Candidate trigger against the original Pi
    trigger;
2.  experiment with Candidate thresholds and see where the trigger would
    move.

The original Pi trigger remains part of the capture record and should
not be overwritten by replay results.

## SolutionFilter

`SolutionFilter` is desktop-only post-capture classification.

It examines the Candidate after it has safely been recorded and can
evaluate behavior across the clip rather than being limited to one
incoming frame.

The current filter chain includes specialized rejection rules for:

-   sustained brightness noise,
-   frame-dropout anomalies,
-   steady-state brightness changes.

Filters run in sequence. The first filter that recognizes a
false-positive pattern rejects the Candidate and supplies the
classification reason.

If no rejection filter fires, the Candidate is classified as a true
flash/Solution.

This architecture is intentional: keep CandidateFinder permissive and
fast, then use whole-clip context to remove false positives later.

## Batch Classification

`batch_classifier.py` applies SolutionFilter to collections of Candidate
MP4/JSON pairs and moves them into category directories.

Current categories include true flashes and known anomaly types.
Captures without sufficient sidecar information are treated as
unclassified.

## Web Application

The Raspberry Pi web application is built with Flask.

`webApp.py` assembles the capture services and Flask application.
`webController.py` registers URL routes that allow the browser to query
or control those services.

The web interface is primarily an operational instrument panel: it
should make camera/capture/trigger status easy to understand without
turning the main screen into a large configuration form.

## Hardware

Current primary hardware:

-   Raspberry Pi 4
-   ELP high-speed USB camera
-   typical capture mode: 640 × 360 at approximately 260 FPS

The Pi web application normally serves on port 8080.

The architecture should not unnecessarily prevent later camera-driver or
hardware changes.







