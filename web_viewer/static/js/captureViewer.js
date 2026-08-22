"use strict";

/*
 * Shared capture viewer used by both the Raspberry Pi P Site and the public
 * Soloran G Site.
 *
 * The component owns all capture-display behavior: MP4 playback, frame
 * stepping, slider seeking, capture graphs, sidecar metadata, Solution status,
 * and High / Medium / Low stored sensitivity results.  It deliberately knows
 * nothing about how a site discovers captures.  A host page supplies a capture
 * with loadCapture() and may place site-specific controls in the "actions"
 * slot.
 *
 * The Shadow DOM keeps the viewer's HTML element ids and CSS isolated from the
 * surrounding P/G page so both sites can use this exact file unchanged.
 */
export class CaptureViewer extends HTMLElement
{
    constructor()
    {
        super();

        this.attachShadow({ mode: "open" });

        this._captureFile = null;
        this._sidecar = null;
        this._frameIndex = 0;
        this._selectedSensitivity = null;
        this._keyHandler = null;
        this._resizeObserver = null;
        this.shadowRoot.innerHTML = this._template();
    }


    connectedCallback()
    {
        this._bindControls();

        this._resizeObserver =
            new ResizeObserver(
                () => this._drawGraphs()
            );

        this._resizeObserver.observe(this);
    }


    disconnectedCallback()
    {
        this._detachKeyboard();

        if (this._resizeObserver !== null)
        {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
    }

    /*
     * Load one capture.  P Site can pass the already-loaded captureFile object:
     *
     *   viewer.loadCapture({ videoUrl, captureFile });
     *
     * G Site can instead pass a sidecar URL:
     *
     *   viewer.loadCapture({ videoUrl, sidecarUrl, name });
     *
     * Supporting both forms keeps the component independent of capture browsing
     * while allowing P and G to converge on the same viewer immediately.
     */
    async loadCapture(options)
    {
        const videoUrl = options?.videoUrl || options?.url;

        if (!videoUrl)
        {
            throw new Error("CaptureViewer requires a videoUrl.");
        }

        let captureFile = options?.captureFile || null;
        let sidecar = options?.sidecar || captureFile?.analysis || null;

        if (sidecar === null && options?.sidecarUrl)
        {
            const response = await fetch(options.sidecarUrl, { cache: "no-store" });

            if (!response.ok)
            {
                throw new Error(
                    `Unable to load sidecar: HTTP ${response.status}`
                );
            }

            sidecar = await response.json();
        }

        if (sidecar === null)
        {
            throw new Error("CaptureViewer requires sidecar data or sidecarUrl.");
        }

        if (captureFile === null)
        {
            captureFile =
            {
                name: options?.name || this._filenameFromUrl(videoUrl),
                display_name: options?.displayName,
                capture_time_display: options?.captureTimeDisplay,
                url: videoUrl,
                analysis: sidecar
            };
        }

        this._captureFile = captureFile;
        this._sidecar = sidecar;
        this._frameIndex = 0;
        this._selectedSensitivity = null;

        this._populateCaptureValues();
        this._configureSlider();
        this._initializeSensitivity();
        this._loadVideo(videoUrl);
        this._attachKeyboard();
    }


    // Unload the current MP4 while leaving the component ready for another capture.
    clearCapture()
    {
        const video = this._byId("video");

        if (video !== null)
        {
            video.pause();
            video.removeAttribute("src");
            video.load();
        }

        this._captureFile = null;
        this._sidecar = null;
        this._frameIndex = 0;
        this._selectedSensitivity = null;
        this._detachKeyboard();
    }

    _bindControls()
    {
        this._byId("step-back-10")?.addEventListener(
            "click",
            () => this._stepFrames(-10)
        );

        this._byId("step-back-1")?.addEventListener(
            "click",
            () => this._stepFrames(-1)
        );

        this._byId("step-forward-1")?.addEventListener(
            "click",
            () => this._stepFrames(1)
        );

        this._byId("step-forward-10")?.addEventListener(
            "click",
            () => this._stepFrames(10)
        );

        this.shadowRoot.querySelectorAll(
            'input[name="viewer-sensitivity"]'
        ).forEach(
            (radio) =>
            {
                radio.addEventListener(
                    "change",
                    () =>
                    {
                        if (radio.checked)
                        {
                            this._applyStoredSensitivityResult(radio.value);
                        }
                    }
                );
            }
        );
    }


    _loadVideo(videoUrl)
    {
        const video = this._byId("video");

        if (video === null)
        {
            return;
        }

        video.controls = false;
        video.pause();
        video.src = videoUrl;
        video.load();

        const onLoadedMetadata =
            () =>
            {
                video.removeEventListener(
                    "loadedmetadata",
                    onLoadedMetadata
                );

                const initialIndex =
                    this._initialFrameIndex();

                const targetSeconds =
                    initialIndex /
                    this._videoFrameRate();

                const onInitialSeeked =
                    () =>
                    {
                        video.removeEventListener(
                            "seeked",
                            onInitialSeeked
                        );

                        /*
                         * Startup synchronization point:
                         * do not claim a current frame until Edge has completed
                         * the initial video seek.
                         */
                        /*
                         * Edge's paused H.264 seek presents the picture
                         * immediately preceding the requested trigger
                         * timestamp. Treat that displayed picture as the
                         * current frame so the image, graph cursor, and frame
                         * metadata agree. This also opens the viewer one frame
                         * before the trigger, which is useful for inspection.
                         */
                        const displayedInitialIndex =
                            Math.max(
                                0,
                                initialIndex - 1
                            );

                        this._frameIndex =
                            displayedInitialIndex;

                        const records =
                            this._frameRecords();

                        this._syncSlider();
                        this._updateFrameLabel();

                        if (
                            displayedInitialIndex >= 0 &&
                            displayedInitialIndex < records.length
                        )
                        {
                            this._updateCurrentFrameValues(
                                records[
                                    displayedInitialIndex
                                ]
                            );
                        }

                        this._drawGraphs();
                    };

                video.addEventListener(
                    "seeked",
                    onInitialSeeked,
                    {
                        once: true
                    }
                );

                video.currentTime =
                    Math.max(
                        0,
                        Math.min(
                            targetSeconds,
                            video.duration || targetSeconds
                        )
                    );
            };

        video.addEventListener(
            "loadedmetadata",
            onLoadedMetadata
        );
    }

    _attachKeyboard()
    {
        this._detachKeyboard();

        this._keyHandler =
            (event) =>
            {
                const path = event.composedPath();
                const active = path[0];
                const tagName = String(active?.tagName || "").toUpperCase();

                if (["INPUT", "TEXTAREA", "SELECT"].includes(tagName))
                {
                    return;
                }

                if (event.key === "ArrowLeft")
                {
                    event.preventDefault();
                    this._stepFrames(event.shiftKey ? -10 : -1);
                }
                else if (event.key === "ArrowRight")
                {
                    event.preventDefault();
                    this._stepFrames(event.shiftKey ? 10 : 1);
                }
            };

        document.addEventListener("keydown", this._keyHandler);
    }


    _detachKeyboard()
    {
        if (this._keyHandler !== null)
        {
            document.removeEventListener("keydown", this._keyHandler);
            this._keyHandler = null;
        }
    }


    /*
     * Deliberately simple frame-step experiment.
     *
     * Do not use requestVideoFrameCallback(), mediaTime mapping, seek-backward
     * priming, or slow sequential playback.  Just pause the browser video and
     * move currentTime by one nominal 260-fps frame period per requested frame.
     *
     * This is intentionally close to the simple behavior of the earlier viewer
     * so we can determine whether Edge's visible frame stepping itself is sound
     * before rebuilding graph/metadata synchronization around it.
     */
    _stepFrames(delta)
    {
        const video = this._byId("video");
        const records = this._frameRecords();

        if (
            video === null ||
            records.length === 0
        )
        {
            return;
        }

        const frameSeconds =
            1.0 /
            this._videoFrameRate();

        video.pause();

        const requestedTime =
            video.currentTime +
            (
                Number(delta) *
                frameSeconds
            );

        video.currentTime =
            Math.max(
                0,
                Math.min(
                    requestedTime,
                    video.duration || requestedTime
                )
            );

        /*
         * For this experiment, keep our logical frame count moving by the same
         * requested delta.  We are testing the visible video behavior first.
         */
        this._frameIndex =
            Math.min(
                records.length - 1,
                Math.max(
                    0,
                    this._frameIndex +
                    Number(delta)
                )
            );

        this._syncSlider();
        this._updateFrameLabel();
        this._updateCurrentFrameValues(
            records[
                this._frameIndex
            ]
        );
        this._drawGraphs();
    }


    _previewSliderFrame()
    {
        const slider = this._byId("frame-slider");
        const records = this._frameRecords();

        if (slider === null || records.length === 0)
        {
            return;
        }

        const previewIndex = Math.min(
            records.length - 1,
            Math.max(0, Number(slider.value) || 0)
        );

        this._byId("frame-label").textContent =
            `${previewIndex + 1} / ${records.length}`;

        this._drawGraphs(previewIndex);
    }


    _commitSliderFrame()
    {
        const slider = this._byId("frame-slider");
        const video = this._byId("video");
        const records = this._frameRecords();

        if (
            slider === null ||
            video === null ||
            records.length === 0
        )
        {
            return;
        }

        const targetIndex =
            Math.min(
                records.length - 1,
                Math.max(
                    0,
                    Math.round(
                        Number(
                            slider.value
                        ) || 0
                    )
                )
            );

        video.pause();

        const targetSeconds =
            targetIndex /
            this._videoFrameRate();

        video.currentTime =
            Math.max(
                0,
                Math.min(
                    targetSeconds,
                    video.duration || targetSeconds
                )
            );

        this._frameIndex =
            targetIndex;

        this._syncSlider();
        this._updateFrameLabel();
        this._updateCurrentFrameValues(
            records[
                targetIndex
            ]
        );
        this._drawGraphs();
    }


    _configureSlider()
    {
        const slider = this._byId("frame-slider");
        const records = this._frameRecords();

        if (slider !== null)
        {
            slider.min = "0";
            slider.max = String(Math.max(0, records.length - 1));
            slider.step = "1";
            slider.value = "0";
        }

        this._updateFrameLabel();
    }


    _syncSlider()
    {
        const slider = this._byId("frame-slider");

        if (slider !== null)
        {
            slider.value = String(this._frameIndex);
        }
    }


    _updateFrameLabel()
    {
        const records = this._frameRecords();
        const label = this._byId("frame-label");

        if (label !== null)
        {
            label.textContent = records.length > 0
                ? `${this._frameIndex + 1} / ${records.length}`
                : "0 / 0";
        }
    }


    _updateCurrentFrame()
    {
        const record = this._currentFrameRecord();

        if (record === null)
        {
            return;
        }

        this._updateCurrentFrameValues(record);
        this._syncSlider();
        this._updateFrameLabel();
        this._drawGraphs();
    }


    _updateCurrentFrameValues(record)
    {
        const records = this._frameRecords();
        const frameIndex = Number(record.frame_index ?? this._frameIndex);

        this._setText("current-frame", `${frameIndex + 1} / ${records.length}`);
        this._setText("current-timestamp", this._formatUtcText(record.timestamp_utc));
        this._setText(
            "current-offset",
            record.offset_ms !== null && record.offset_ms !== undefined
                ? `${Number(record.offset_ms).toFixed(3)} ms`
                : "--"
        );
        this._setText(
            "current-brightness",
            this._formatNumber(record.mean_brightness, 3)
        );
        this._setText(
            "current-brightness-change",
            this._formatNumber(record.brightness_delta_adjacent, 3)
        );
    }


    _populateCaptureValues()
    {
        const sidecar = this._sidecar || {};
        const camera = sidecar.camera || {};
        const candidate = sidecar.candidate || {};

        this._setText(
            "capture-video",
            this._captureFile?.name || this._captureFile?.display_name || "--"
        );

        this._setText(
            "capture-start",
            this._formatUtcText(
                this._sidecarValue(sidecar, "capture", "start_utc", "capture_start_utc")
            )
        );

        this._setText(
            "capture-trigger",
            candidate.trigger_display ||
                sidecar.trigger_display ||
                candidate.trigger_type ||
                sidecar.trigger_type ||
                "--"
        );

        this._setText(
            "capture-trigger-reason",
            candidate.trigger_reason || sidecar.trigger_reason || "--"
        );

        const piTriggerIndex =
            candidate.trigger_frame_index ?? sidecar.trigger_frame_index;

        const piTriggerNumber =
            candidate.trigger_frame_number ??
            sidecar.trigger_frame_number ??
            (piTriggerIndex !== null && piTriggerIndex !== undefined
                ? Number(piTriggerIndex) + 1
                : null);

        this._setText(
            "pi-trigger-frame",
            piTriggerNumber !== null && piTriggerNumber !== undefined
                ? String(piTriggerNumber)
                : "--"
        );

        const triggerOffset =
            candidate.trigger_offset_ms ?? sidecar.trigger_offset_ms;

        this._setText(
            "trigger-offset",
            triggerOffset !== null && triggerOffset !== undefined
                ? `${Number(triggerOffset).toFixed(3)} ms`
                : "--"
        );

        this._setText(
            "site-name",
            camera.site_name ?? sidecar.site_name ?? "Flagstaff"
        );
        this._setText(
            "site-latitude",
            this._formatNumber(
                camera.latitude_degrees ?? sidecar.camera_latitude_degrees,
                7,
                "°"
            )
        );
        this._setText(
            "site-longitude",
            this._formatNumber(
                camera.longitude_degrees ?? sidecar.camera_longitude_degrees,
                7,
                "°"
            )
        );
        this._setText(
            "site-bearing",
            this._formatNumber(
                camera.bearing_degrees ?? sidecar.camera_bearing_degrees,
                1,
                "°"
            )
        );
        this._setText(
            "site-hfov",
            this._formatNumber(
                camera.hfov_degrees ?? sidecar.camera_hfov_degrees,
                1,
                "°"
            )
        );
        this._setText(
            "site-vfov",
            this._formatNumber(
                camera.vfov_degrees ?? sidecar.camera_vfov_degrees,
                1,
                "°"
            )
        );

        this._setText(
            "search-bounds",
            this._formatSearchBounds(
                sidecar.search_bounding_box || camera.search_bounding_box
            )
        );
    }


    _initializeSensitivity()
    {
        const sidecar = this._sidecar || {};
        const results = sidecar.sensitivity_results;

        if (results === null || typeof results !== "object")
        {
            this._selectedSensitivity = null;
            this._setSensitivityEnabled(false);
            this._selectSensitivity(null);
            this._setText("replay-trigger-frame", "--");
            this._clearThresholds();
            this._setSolution(
                "UNAVAILABLE",
                "Stored High / Medium / Low analysis is not present in this older sidecar. Migrate the sidecar to the current version to enable sensitivity selection."
            );
            return;
        }

        this._setSensitivityEnabled(true);

        const originalSensitivity = String(
            sidecar?.candidate?.config?.sensitivity || ""
        ).toLowerCase();

        let initial = "medium";

        if (["high", "medium", "low"].includes(originalSensitivity) &&
            results[originalSensitivity] !== undefined)
        {
            initial = originalSensitivity;
        }
        else if (results.medium === undefined)
        {
            initial = ["high", "low"].find(
                (name) => results[name] !== undefined
            ) || "medium";
        }

        this._applyStoredSensitivityResult(initial);
    }


    _applyStoredSensitivityResult(sensitivity)
    {
        const normalized = String(sensitivity || "").toLowerCase();
        const result = this._sidecar?.sensitivity_results?.[normalized];

        if (result === null || result === undefined || typeof result !== "object")
        {
            this._setSolution(
                "UNAVAILABLE",
                `No stored result is available for ${normalized || "this"} sensitivity.`
            );
            return;
        }

        this._selectedSensitivity = normalized;
        this._selectSensitivity(normalized);

        const config = result.candidate_config || {};

        this._setText(
            "threshold-brightness-delta",
            this._formatNumber(config.candidate_brightness_delta_threshold, 3)
        );
        this._setText(
            "threshold-bright-pixel-delta",
            this._formatNumber(config.candidate_bright_pixel_delta_threshold, 3)
        );
        this._setText(
            "threshold-bright-pixel-fraction",
            this._formatNumber(config.candidate_bright_pixel_fraction_threshold, 6)
        );

        this._setText(
            "replay-trigger-frame",
            result.trigger_frame_number !== null && result.trigger_frame_number !== undefined
                ? String(result.trigger_frame_number)
                : "No candidate"
        );

        this._setSolution(
            result.solution_category || "UNCLASSIFIED",
            result.solution_reason || result.trigger_reason || "--"
        );

        this._drawGraphs();
    }


    _setSensitivityEnabled(enabled)
    {
        this.shadowRoot.querySelectorAll(
            'input[name="viewer-sensitivity"]'
        ).forEach(
            (radio) => radio.disabled = !enabled
        );
    }


    _selectSensitivity(sensitivity)
    {
        this.shadowRoot.querySelectorAll(
            'input[name="viewer-sensitivity"]'
        ).forEach(
            (radio) => radio.checked = radio.value === sensitivity
        );
    }


    _clearThresholds()
    {
        this._setText("threshold-brightness-delta", "--");
        this._setText("threshold-bright-pixel-delta", "--");
        this._setText("threshold-bright-pixel-fraction", "--");
    }


    _setSolution(category, reason)
    {
        const element = this._byId("solution-result");
        const normalized = String(category || "").toUpperCase();

        if (element !== null)
        {
            element.textContent = normalized || "UNCLASSIFIED";
            element.classList.remove(
                "solutionPending",
                "solutionTrue",
                "solutionFalse"
            );

            if (normalized === "TRUE_FLASH")
            {
                element.classList.add("solutionTrue");
            }
            else if (normalized === "UNAVAILABLE")
            {
                element.classList.add("solutionPending");
            }
            else
            {
                element.classList.add("solutionFalse");
            }
        }

        this._setText("solution-reason", reason || "--");
    }


    _drawGraphs(cursorIndex = this._frameIndex)
    {
        this._drawGraph("brightness-graph", "mean_brightness", "Brightness", cursorIndex);
        this._drawGraph("delta-graph", "brightness_delta_adjacent", "Delta brightness", cursorIndex);
    }


    _drawGraph(canvasId, valueKey, label, cursorIndex)
    {
        const canvas = this._byId(canvasId);
        const records = this._frameRecords();

        if (canvas === null)
        {
            return;
        }

        const rect = canvas.getBoundingClientRect();
        canvas.width = Math.max(1, Math.floor(rect.width));
        canvas.height = Math.max(1, Math.floor(rect.height));

        const context = canvas.getContext("2d");
        const values = records.map((record) => Number(record[valueKey] ?? 0.0));
        const limits = this._valueLimits(values);
        const plot = this._drawAxes(context, canvas.width, canvas.height, limits, records);

        if (records.length >= 2)
        {
            const range = Math.max(0.000001, limits.max - limits.min);
            context.strokeStyle = "#2f80ed";
            context.lineWidth = 1.5;
            context.beginPath();

            records.forEach(
                (record, index) =>
                {
                    const x =
                        this._frameX(
                            plot,
                            records,
                            index
                        );
                    const value = Number(record[valueKey] ?? 0);
                    const y = plot.bottom -
                        ((value - limits.min) * (plot.bottom - plot.top) / range);

                    if (index === 0)
                    {
                        context.moveTo(x, y);
                    }
                    else
                    {
                        context.lineTo(x, y);
                    }
                }
            );

            context.stroke();
        }

        this._drawMarker(
            context,
            plot,
            records,
            this._piTriggerIndex(),
            "#7a3db8",
            "Pi",
            1.5
        );

        this._drawMarker(
            context,
            plot,
            records,
            this._replayTriggerIndex(),
            "#d47a00",
            "Replay",
            1.5
        );

        this._drawMarker(
            context,
            plot,
            records,
            cursorIndex,
            "#c00020",
            `F${Number(cursorIndex) + 1}`,
            2,
            true
        );

        context.fillStyle = "#2f80ed";
        context.font = "10px Arial";
        context.textAlign = "left";
        context.fillText(label, plot.left + 4, plot.top + 12);
    }


    _drawAxes(context, width, height, limits, records)
    {
        const plot =
        {
            left: 46,
            right: width - 8,
            top: 8,
            bottom: height - 38
        };

        context.clearRect(0, 0, width, height);
        context.strokeStyle = "#d0d0d0";
        context.lineWidth = 1;

        for (let grid = 0; grid <= 4; grid += 1)
        {
            const y = plot.top + (plot.bottom - plot.top) * grid / 4;
            context.beginPath();
            context.moveTo(plot.left, y);
            context.lineTo(plot.right, y);
            context.stroke();
        }

        context.strokeStyle = "#888888";
        context.beginPath();
        context.moveTo(plot.left, plot.top);
        context.lineTo(plot.left, plot.bottom);
        context.lineTo(plot.right, plot.bottom);
        context.stroke();

        context.fillStyle = "#333333";
        context.font = "10px Arial";
        context.textAlign = "center";

        const lastFrameIndex =
            Math.max(
                0,
                records.length - 1
            );

        for (let tick = 0; tick <= 4; tick += 1)
        {
            const fraction =
                tick / 4;

            const x =
                plot.left +
                (
                    plot.right -
                    plot.left
                ) *
                fraction;

            const frameIndex =
                Math.round(
                    lastFrameIndex *
                    fraction
                );

            context.beginPath();
            context.moveTo(x, plot.bottom);
            context.lineTo(x, plot.bottom + 4);
            context.stroke();

            context.fillText(
                String(
                    frameIndex
                ),
                x,
                plot.bottom + 22
            );
        }

        context.textAlign = "left";
        context.fillText(limits.max.toFixed(1), 4, plot.top + 8);
        context.fillText(limits.min.toFixed(1), 4, plot.bottom);

        return plot;
    }


    _drawMarker(context, plot, records, requestedIndex, color, label, width, labelBelow = false)
    {
        const index = this._clampFrameIndex(requestedIndex);

        if (index === null || records.length === 0)
        {
            return;
        }

        const x =
            this._frameX(
                plot,
                records,
                index
            );

        context.save();
        context.strokeStyle = color;
        context.lineWidth = width;
        context.beginPath();
        context.moveTo(x, plot.top);
        context.lineTo(x, plot.bottom);
        context.stroke();
        context.fillStyle = color;
        context.textAlign = "center";
        context.font = "10px Arial";
        context.fillText(
            label,
            x,
            labelBelow ? plot.bottom + 34 : plot.top + 11
        );
        context.restore();
    }


    /*
     * Graph X position is based on logical frame index, not historical Pi
     * offset_ms.  Rebuilt sidecars can preserve acquisition-time gaps that do
     * not exist in the encoded MP4 timeline; using those offsets distorts the
     * graph badly.  Frame index matches Analyzer behavior and remains stable.
     */
    _frameX(plot, records, frameIndex)
    {
        const lastFrameIndex =
            Math.max(
                1,
                records.length - 1
            );

        const fraction =
            Math.max(
                0,
                Math.min(
                    1,
                    Number(frameIndex) /
                    lastFrameIndex
                )
            );

        return (
            plot.left +
            (
                plot.right -
                plot.left
            ) *
            fraction
        );
    }


    /*
     * Return the MP4 presentation frame rate.  Historical frame_records
     * offset_ms remains useful for display, but must not be used to seek the
     * encoded MP4 because rebuilt sidecars may preserve Pi acquisition gaps.
     */
    _videoFrameRate()
    {
        const fps =
            Number(
                this._sidecar?.camera?.
                    frame_rate_fps
            );

        return (
            Number.isFinite(fps) &&
            fps > 0
        )
            ? fps
            : 260.0;
    }


    _valueLimits(values)
    {
        if (values.length === 0)
        {
            return { min: 0, max: 1 };
        }

        let min = Math.min(...values);
        let max = Math.max(...values);

        if (min === max)
        {
            min -= 1;
            max += 1;
        }

        return { min, max };
    }


    _initialFrameIndex()
    {
        return this._clampFrameIndex(this._piTriggerIndex()) ?? 0;
    }


    _piTriggerIndex()
    {
        const candidate = this._sidecar?.candidate || {};

        if (candidate.trigger_frame_index !== null && candidate.trigger_frame_index !== undefined)
        {
            return Number(candidate.trigger_frame_index);
        }

        if (this._sidecar?.trigger_frame_index !== null && this._sidecar?.trigger_frame_index !== undefined)
        {
            return Number(this._sidecar.trigger_frame_index);
        }

        const frameNumber = candidate.trigger_frame_number ?? this._sidecar?.trigger_frame_number;

        return frameNumber !== null && frameNumber !== undefined
            ? Number(frameNumber) - 1
            : null;
    }


    _replayTriggerIndex()
    {
        return this._sidecar?.sensitivity_results?.[this._selectedSensitivity]?.trigger_frame_index ?? null;
    }


    _clampFrameIndex(index)
    {
        const records = this._frameRecords();

        if (index === null || index === undefined || records.length === 0)
        {
            return null;
        }

        const number = Math.round(Number(index));

        if (!Number.isFinite(number))
        {
            return null;
        }

        return Math.min(records.length - 1, Math.max(0, number));
    }


    _frameRecords()
    {
        return Array.isArray(this._sidecar?.frame_records)
            ? this._sidecar.frame_records
            : [];
    }


    _currentFrameRecord()
    {
        const records = this._frameRecords();
        return records.length > 0
            ? records[this._clampFrameIndex(this._frameIndex) ?? 0]
            : null;
    }


    _sidecarValue(sidecar, sectionName, key, legacyKey = null)
    {
        const section = sidecar?.[sectionName];

        if (section !== null && typeof section === "object" && section[key] !== undefined)
        {
            return section[key];
        }

        return sidecar?.[legacyKey ?? key];
    }


    _formatSearchBounds(bounds)
    {
        if (!bounds || typeof bounds !== "object")
        {
            return "--";
        }

        const minLat = bounds.min_latitude ?? bounds.min_latitude_degrees;
        const maxLat = bounds.max_latitude ?? bounds.max_latitude_degrees;
        const minLon = bounds.min_longitude ?? bounds.min_longitude_degrees;
        const maxLon = bounds.max_longitude ?? bounds.max_longitude_degrees;

        if (![minLat, maxLat, minLon, maxLon].every(
            (value) => value !== null && value !== undefined && Number.isFinite(Number(value))))
        {
            return "--";
        }

        return `${Number(minLat).toFixed(5)}, ${Number(minLon).toFixed(5)} to ` +
            `${Number(maxLat).toFixed(5)}, ${Number(maxLon).toFixed(5)}`;
    }


    _formatUtcText(value)
    {
        if (value === null || value === undefined || value === "")
        {
            return "-- UTC";
        }

        let text = String(value).replace("T", " ").replace("Z", "");

        if (text.includes("."))
        {
            const parts = text.split(".");
            text = parts[0] + "." + parts[1].slice(0, 3);
        }

        return text + " UTC";
    }


    _formatNumber(value, digits = 3, suffix = "")
    {
        if (value === null || value === undefined || value === "")
        {
            return "--";
        }

        const number = Number(value);
        return Number.isFinite(number)
            ? number.toFixed(digits) + suffix
            : String(value);
    }


    _filenameFromUrl(url)
    {
        try
        {
            return decodeURIComponent(new URL(url, window.location.href).pathname.split("/").pop());
        }
        catch
        {
            return String(url);
        }
    }


    _byId(id)
    {
        return this.shadowRoot.getElementById(id);
    }


    _setText(id, text)
    {
        const element = this._byId(id);
        if (element !== null)
        {
            element.textContent = text;
        }
    }


    _template()
    {
        return `
        <style>
            :host
            {
                display: block;
                min-width: 0;
                min-height: 0;
                height: 100%;
                font-family: Arial, sans-serif;
                color: #111;
            }

            *, *::before, *::after
            {
                box-sizing: border-box;
            }

            .viewerGrid
            {
                display: grid;
                grid-template-columns: minmax(0, 7fr) minmax(300px, 3fr);
                grid-template-rows: minmax(240px, 0.95fr) minmax(270px, 1.05fr) auto;
                grid-template-areas:
                    "media sidebar"
                    "graphs sidebar"
                    "navigation sidebar";
                gap: 8px;
                min-height: 0;
                height: 100%;
            }

            .panel
            {
                border: 1px solid #777;
                background: white;
                padding: 8px;
                min-height: 0;
                overflow: hidden;
            }

            .panel h2
            {
                margin: 0 0 7px 0;
                font-size: 15px;
            }

            .mediaPanel
            {
                grid-area: media;
                display: grid;
                grid-template-rows: 26px minmax(0, 1fr);
                gap: 6px;
            }

            .mediaViewport
            {
                position: relative;
                min-height: 0;
                overflow: hidden;
                background: #111;
            }

            video
            {
                display: block;
                width: 100%;
                height: 100%;
                object-fit: contain;
                background: #111;
            }

            .graphsPanel
            {
                grid-area: graphs;
                display: grid;
                grid-template-rows: 26px minmax(0, 1fr) minmax(0, 1fr);
                gap: 6px;
            }

            canvas
            {
                display: block;
                width: 100%;
                height: 100%;
                background: #fafafa;
            }

            .navigation
            {
                grid-area: navigation;
            }

            .stepControls
            {
                display: flex;
                align-items: center;
                gap: 4px;
                width: 100%;
            }

            .miniButton
            {
                min-width: 42px;
                padding: 3px 6px;
                font-size: 11px;
                font-weight: 600;
                border: 1px solid #888;
                border-radius: 4px;
                background: #eee;
                cursor: pointer;
            }

            .miniButton:hover
            {
                background: #e0e0e0;
            }

            #frame-slider
            {
                flex: 1 1 auto;
                min-width: 80px;
            }

            #frame-label
            {
                min-width: 70px;
                text-align: center;
                font-family: Consolas, monospace;
                font-size: 12px;
            }

            .sidebar
            {
                grid-area: sidebar;
                display: grid;
                align-content: start;
                gap: 8px;
                min-height: 0;
                overflow-y: auto;
            }

            .actions
            {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 6px;
            }

            ::slotted([slot="actions"])
            {
                margin-bottom: 6px;
            }

            .infoGrid
            {
                display: grid;
                grid-template-columns: max-content minmax(0, 1fr);
                column-gap: 12px;
                row-gap: 4px;
                min-width: 0;
                font-family: Consolas, monospace;
                font-size: 12px;
            }

            .infoGrid > div:nth-child(odd)
            {
                color: #555;
                white-space: nowrap;
            }

            .infoGrid > div:nth-child(even)
            {
                min-width: 0;
                overflow-wrap: anywhere;
                text-align: right;
                font-weight: 700;
            }

            .solutionResult
            {
                padding: 9px;
                border: 1px solid #999;
                border-radius: 4px;
                text-align: center;
                font-weight: 700;
            }

            .solutionPending { background: #eee; }
            .solutionTrue { background: #b7e4c7; }
            .solutionFalse { background: #f4b8b8; }

            .solutionReasonBlock
            {
                margin-top: 8px;
            }

            .solutionReasonLabel
            {
                margin-bottom: 3px;
                color: #555;
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
            }

            .solutionReason
            {
                padding: 6px 8px;
                border: 1px solid #ccc;
                border-radius: 4px;
                background: #fafafa;
                font-size: 12px;
                line-height: 1.3;
            }

            .sensitivityChoices
            {
                display: flex;
                gap: 14px;
                flex-wrap: wrap;
                margin-bottom: 8px;
                font-size: 12px;
                font-weight: 700;
            }

            .sensitivityChoices input:disabled
            {
                cursor: wait;
            }

            @media (max-width: 900px) and (orientation: portrait)
            {
                :host { height: auto; }

                .viewerGrid
                {
                    grid-template-columns: minmax(0, 1fr);
                    grid-template-rows: 360px 430px auto auto;
                    grid-template-areas:
                        "media"
                        "graphs"
                        "navigation"
                        "sidebar";
                    height: auto;
                }

                .sidebar { overflow-y: visible; }
            }

            @media (max-width: 700px)
            {
                .viewerGrid
                {
                    grid-template-rows: 280px 400px auto auto;
                }

                .actions { grid-template-columns: 1fr; }

                .stepControls { flex-wrap: wrap; }

                #frame-slider
                {
                    order: 3;
                    flex-basis: 100%;
                    width: 100%;
                }

                #frame-label
                {
                    order: 4;
                    flex-basis: 100%;
                }

                .infoGrid
                {
                    grid-template-columns: minmax(0, 1fr);
                }

                .infoGrid > div:nth-child(even)
                {
                    text-align: left;
                    margin-bottom: 3px;
                }
            }
        </style>

        <div class="viewerGrid">
            <section class="panel mediaPanel">
                <h2>Capture Playback</h2>
                <div class="mediaViewport">
                    <video id="video" muted playsinline></video>
                </div>
            </section>

            <section class="panel graphsPanel">
                <h2>Graphs</h2>
                <canvas id="brightness-graph"></canvas>
                <canvas id="delta-graph"></canvas>
            </section>

            <section class="panel navigation">
                <div class="stepControls">
                    <button class="miniButton" id="step-back-10" type="button" title="Back 10 frames: Shift+Left">-10</button>
                    <button class="miniButton" id="step-back-1" type="button" title="Back 1 frame: Left">-1</button>
                    <input id="frame-slider" type="range" min="0" max="0" step="1" value="0" disabled aria-label="Playback frame">
                    <span id="frame-label">1 / 1</span>
                    <button class="miniButton" id="step-forward-1" type="button" title="Forward 1 frame: Right">+1</button>
                    <button class="miniButton" id="step-forward-10" type="button" title="Forward 10 frames: Shift+Right">+10</button>
                </div>
            </section>

            <aside class="sidebar">
                <div class="actions"><slot name="actions"></slot></div>

                <section class="panel">
                    <h2>Site Info</h2>
                    <div class="infoGrid">
                        <div>Site name</div><div id="site-name">--</div>
                        <div>Latitude</div><div id="site-latitude">--</div>
                        <div>Longitude</div><div id="site-longitude">--</div>
                        <div>Bearing</div><div id="site-bearing">--</div>
                        <div>Horizontal FOV</div><div id="site-hfov">--</div>
                        <div>Vertical FOV</div><div id="site-vfov">--</div>
                        <div>Search bounding box</div><div id="search-bounds">--</div>
                    </div>
                </section>

                <section class="panel">
                    <h2>Current Capture</h2>
                    <div class="infoGrid">
                        <div>Video</div><div id="capture-video">--</div>
                        <div>Capture start UTC</div><div id="capture-start">--</div>
                        <div>Trigger</div><div id="capture-trigger">--</div>
                        <div>Trigger reason</div><div id="capture-trigger-reason">--</div>
                        <div>Pi Trigger Frame</div><div id="pi-trigger-frame">--</div>
                        <div>Replay Trigger Frame</div><div id="replay-trigger-frame">--</div>
                        <div>Trigger Offset</div><div id="trigger-offset">--</div>
                    </div>
                </section>

                <section class="panel">
                    <h2>Current Frame</h2>
                    <div class="infoGrid">
                        <div>Frame</div><div id="current-frame">--</div>
                        <div>Timestamp UTC</div><div id="current-timestamp">--</div>
                        <div>Offset</div><div id="current-offset">--</div>
                        <div>Pi brightness</div><div id="current-brightness">--</div>
                        <div>Pi brightness change</div><div id="current-brightness-change">--</div>
                    </div>
                </section>

                <section class="panel">
                    <h2>Solution</h2>
                    <div class="solutionResult solutionPending" id="solution-result">Not evaluated</div>
                    <div class="solutionReasonBlock">
                        <div class="solutionReasonLabel">Reason</div>
                        <div class="solutionReason" id="solution-reason">--</div>
                    </div>
                </section>

                <section class="panel">
                    <h2>Sensitivity</h2>
                    <div class="sensitivityChoices">
                        <label><input type="radio" name="viewer-sensitivity" value="high" disabled> High</label>
                        <label><input type="radio" name="viewer-sensitivity" value="medium" disabled> Medium</label>
                        <label><input type="radio" name="viewer-sensitivity" value="low" disabled> Low</label>
                    </div>
                    <div class="infoGrid">
                        <div>Brightness delta threshold</div><div id="threshold-brightness-delta">--</div>
                        <div>Bright pixel delta</div><div id="threshold-bright-pixel-delta">--</div>
                        <div>Bright pixel fraction</div><div id="threshold-bright-pixel-fraction">--</div>
                    </div>
                </section>
            </aside>
        </div>`;
    }
}


if (!customElements.get("capture-viewer"))
{
    customElements.define("capture-viewer", CaptureViewer);
}
