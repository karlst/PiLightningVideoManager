# Handoff.md

# Pi Camera Capture — ChatGPT Handoff

## Purpose

This document is **not** user documentation.

It exists so ChatGPT (or any new developer) can become productive on this project within a few minutes without rereading months of chat history.

The source code is the primary documentation.

This file records the architectural decisions that are not obvious from the code.

---

# Project Goal

Detect and capture cloud-to-ground (CG) lightning using a Raspberry Pi 4 and a high-speed USB camera.

Primary goals:

* Never miss a CG lightning event.
* Support daylight lightning.
* Preserve pre-trigger frames.
* Analyze captures after recording.
* Build a personal lightning database for future tuning.

Machine learning is intentionally **not** part of the design.

---

# Hardware

* Raspberry Pi 4
* ELP USB camera
* Typical operating mode:

  * 640 × 360
  * 260 FPS

The Pi hosts the web UI on port **8080**.

---

# General Design Philosophy

Capture first.

Analyze later.

Storage is inexpensive.

Missing lightning is expensive.

The system intentionally tolerates false positives during development.

---

# UI Philosophy

The main screen is an **instrument panel**, not a configuration page.

Main screen should answer:

* Is the system healthy?
* Is the camera running?
* Is triggering enabled?
* What is happening now?

Configuration belongs in dialogs.

Playback temporarily replaces operational information with forensic analysis.

---

# Trigger Philosophy

Current trigger is intentionally simple.

Current algorithm:

Adjacent-frame brightness delta.

Every incoming frame is evaluated.

Graphs are **not** part of trigger evaluation.

Graphs exist only for display.

The trigger path must always remain lightweight.

Expensive OpenCV analysis occurs after capture.

---

# Ring Buffer Philosophy

The ring buffer is always running.

Captures consist of:

* Pre-trigger frames
* Trigger frame
* Post-trigger frames

The trigger frame should always be identifiable during playback.

---

# Frame Analysis Philosophy

Frame analysis exists for measurement.

Not classification.

Each frame is processed independently.

Current processing:

* grayscale
* absolute brightness threshold
* local contrast threshold
* connected components
* geometry filters

Measurements are written to the sidecar.

The sidecar should contain facts, not opinions.

Avoid fields like:

* lightning_probability
* continuing_current_candidate
* ML scores

Instead store measurable quantities.

---

# Playback Philosophy

Playback is a forensic tool.

Desired workflow:

Trigger occurs

↓

Open capture

↓

Step frame-by-frame

↓

Graphs follow playback

↓

Read analysis panel

↓

Understand why the trigger fired

Playback should help improve triggering.

---

# Sidecar Philosophy

Sidecar accompanies every capture.

Purpose:

Preserve measurements that would otherwise require expensive re-analysis.

Examples:

* trigger type
* trigger frame
* trigger offset
* component counts
* duration
* frame records

Sidecars should remain versioned.

---

# Event Log

Recent Events shows concise summaries.

Dialog shows complete messages.

Every significant event should be logged.

Health entries are periodic.

---

# Coding Conventions

Python

Every class:

#

Every method:

#

Paragraph comments encouraged.

Prefer one return statement unless multiple returns improve readability.

Preserve comments.

For substantial changes return complete files.

---

JavaScript

Same conventions.

Use

// ##

before classes and methods.

Return complete files for substantial changes.

---

# ChatGPT Rules

Never guess.

If source files are needed:

Ask.

Always modify uploaded versions.

Do not regenerate old code from memory.

Preserve comments.

Preserve architecture.

---

# Things Already Learned

Several architectural decisions were made after experimentation.

Do not revert them without good reason.

Examples:

* Instrument panel instead of configuration page.
* Playback replaces live mode.
* Adjacent-frame trigger instead of moving-average trigger.
* Sidecars contain measurements only.
* Trigger first, analyze later.
* No machine learning.
* Daylight lightning is a primary requirement.

---

# Current State

Implemented:

✓ Ring buffer

✓ MP4 recording

✓ Trigger metadata

✓ JSON sidecars

✓ Frame stepping

✓ Arrow-key playback

✓ Capture analysis panel

✓ Playback graphs

✓ Connected-component analysis

✓ Local contrast

Current work:

Improve trigger quality while avoiding missed lightning.

---

# Near-Term Priorities

1. Continue trigger tuning.

2. Improve daylight lightning detection.

3. Add more per-frame metrics to playback graphs.

4. Continue OpenCV-based geometry measurements.

5. Tune connected-component filters using real lightning captures.

---

# Long-Term Vision

Eventually the system should become an engineering instrument for studying lightning.

The capture itself is only the first step.

The long-term value comes from building a library of measured lightning events that can be replayed, analyzed, compared, and used to improve future trigger algorithms.

Whenever possible, preserve data instead of throwing it away.

Future algorithms can always re-analyze stored captures.
