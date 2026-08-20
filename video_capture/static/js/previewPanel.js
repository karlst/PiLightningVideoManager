"use strict";

import
{
    postJson,
    getJson
}
from "./httpClient.js";


// ## Manages live preview, playback mode, and capture analysis display.
export class PreviewPanel
{
    // ## Initialize preview state and related panels.
    constructor(statusPanel, eventLogPanel, metricsGraphPanel = null)
    {
        this._statusPanel =
            statusPanel;

        this._eventLogPanel =
            eventLogPanel;

        this._metricsGraphPanel =
            metricsGraphPanel;

        this._previewTimerId =
            null;

        this._lastImageLoadTimeMs =
            null;

        this._previewRefreshMs =
            1000;

        this._mode =
            "preview";

        document.body.classList.remove(
            "capturePlaybackMode"
        );

        this._playbackCaptureFile =
            null;

        this._playbackTimeHandler =
            null;

        this._playbackKeyHandler =
            null;

        // Logical frame selected by the viewer. This is authoritative while
        // playback mode is active; video.currentTime is only a transport used
        // to ask the browser to display that frame.
        this._playbackFrameIndex =
            0;

        this._playbackSeekPending =
            false;

        this._playbackCapturePath =
            null;

        this._replayRequestSerial =
            0;

        this._viewerSensitivityProfiles =
            {};
    }


    // ## Bind UI controls and load preview timing from the server.
    initialize()
    {
        this._bindClick(
            "capture-button",
            () => this.captureOnce()
        );

        this._bindClick(
            "close-playback-button",
            () => this.closePlayback()
        );

        this._bindClick(
            "playback-step-back-10-button",
            () => this._stepPlaybackFrames(-10)
        );

        this._bindClick(
            "playback-step-back-1-button",
            () => this._stepPlaybackFrames(-1)
        );

        this._bindClick(
            "playback-step-forward-1-button",
            () => this._stepPlaybackFrames(1)
        );

        this._bindClick(
            "playback-step-forward-10-button",
            () => this._stepPlaybackFrames(10)
        );

        const frameSlider =
            document.getElementById(
                "playback-frame-slider"
            );

        if (frameSlider !== null)
        {
            frameSlider.addEventListener(
                "input",
                () => this._previewSliderFrame()
            );

            frameSlider.addEventListener(
                "change",
                () => this._commitSliderFrame()
            );
        }

        document.querySelectorAll(
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
                            this._handleViewerSensitivityChange(
                                radio.value
                            );
                        }
                    }
                );
            }
        );

        this._ensurePlaybackOverlay();
        this._loadPreviewConfig();
    }


    // ## Read preview refresh timing and start live preview mode.
    async _loadPreviewConfig()
    {
        try
        {
            const result =
                await getJson(
                    "/system_status"
                );

            this._previewRefreshMs =
                Math.max(
                    100,
                    Number(result.camera_preview_refresh_seconds ?? 1.0) * 1000
                );
        }
        catch (error)
        {
            console.error(
                error
            );
        }

        this.showPreviewMode();
    }


    // ## Request a single legacy camera capture from the server.
    async captureOnce()
    {
        this._statusPanel.setStatus(
            "Capturing..."
        );

        try
        {
            const result =
                await postJson(
                    "/capture_once"
                );

            this._statusPanel.setStatus(
                result.success ? "Capture Complete" : "Capture Failed"
            );

            this._eventLogPanel.refresh();
        }
        catch (error)
        {
            this._statusPanel.setStatus(
                "Communication Error"
            );

            console.error(
                error
            );
        }
    }


    // ## Switch the media panel back to live camera preview.
    showPreviewMode()
    {
        this._mode =
            "preview";

        document.body.classList.remove(
            "capturePlaybackMode"
        );

        this._playbackCaptureFile =
            null;

        this._playbackCapturePath =
            null;

        this._playbackFrameIndex =
            0;

        this._playbackSeekPending =
            false;

        this._setMediaTitle(
            "Live Camera"
        );

        this._detachPlaybackOverlayEvents();
        this._detachPlaybackKeyboardEvents();
        this._hidePlaybackOverlay();
        this._hidePlaybackStepControls();
        this._hidePlaybackViewer();
        this._showImageAge();
        this._showStatusContext();
        this._showLiveGraphs();
        this._hideVideo();
        this._showImageShell();
        this._startPreviewPolling();
        this._hideClosePlaybackButton();
    }


    // ## Switch the media panel to capture playback and show sidecar analysis.
    showPlaybackMode(
        videoUrl,
        captureFile = null
    )
    {
        let resolvedVideoUrl =
            videoUrl;

        let resolvedCaptureFile =
            captureFile;

        if (
            typeof videoUrl === "object" &&
            videoUrl !== null
        )
        {
            resolvedCaptureFile =
                videoUrl;

            resolvedVideoUrl =
                videoUrl.url;
        }

        this._mode =
            "playback";

        document.body.classList.add(
            "capturePlaybackMode"
        );

        this._playbackCaptureFile =
            resolvedCaptureFile;

        this._playbackCapturePath =
            this._resolvePlaybackCapturePath(
                resolvedVideoUrl,
                resolvedCaptureFile
            );

        this._setMediaTitle(
            "Capture Playback"
        );

        this._stopPreviewPolling();
        this._hideImage();

        this._playbackFrameIndex =
            0;

        this._playbackSeekPending =
            false;

        this._configurePlaybackSlider();

        this._showVideo(
            resolvedVideoUrl
        );

        this._showFrameAnalysisContext(
            resolvedCaptureFile
        );

        this._showCaptureGraphs(
            resolvedCaptureFile
        );

        this._attachPlaybackOverlayEvents();
        this._attachPlaybackKeyboardEvents();
        this._updatePlaybackOverlay();
        this._showClosePlaybackButton();
        this._showPlaybackStepControls();
        this._showPlaybackViewer();

        this._updatePlaybackViewerCaptureValues(
            resolvedCaptureFile
        );

        this._loadInitialReplay();

        this._hideImageAge();
    }


    // ## Show frame-by-frame capture graphs during playback.
    _showCaptureGraphs(captureFile)
    {
        if (this._metricsGraphPanel !== null)
        {
            this._metricsGraphPanel.showCaptureMetrics(
                captureFile
            );
        }
    }


    // ## Restore live long-term graphs after playback closes.
    _showLiveGraphs()
    {
        if (this._metricsGraphPanel !== null)
        {
            this._metricsGraphPanel.showLiveMetrics();
        }
    }


    // ## Close playback and return to live preview.
    closePlayback()
    {
        this.showPreviewMode();
    }


    // ## Show the playback close button.
    _showClosePlaybackButton()
    {
        const button =
            document.getElementById(
                "close-playback-button"
            );

        if (button !== null)
        {
            button.classList.remove(
                "cameraImageHidden"
            );
        }
    }


    // ## Hide the playback close button.
    _hideClosePlaybackButton()
    {
        const button =
            document.getElementById(
                "close-playback-button"
            );

        if (button !== null)
        {
            button.classList.add(
                "cameraImageHidden"
            );
        }
    }


    // ## Show playback step controls.
    _showPlaybackStepControls()
    {
        const controls =
            document.getElementById(
                "playback-step-controls"
            );

        if (controls !== null)
        {
            controls.classList.remove(
                "cameraImageHidden"
            );
        }

    }


    // ## Hide playback step controls.
    _hidePlaybackStepControls()
    {
        const controls =
            document.getElementById(
                "playback-step-controls"
            );

        if (controls !== null)
        {
            controls.classList.add(
                "cameraImageHidden"
            );
        }
    }


    // ## Start polling for live preview JPEG frames.
    _startPreviewPolling()
    {
        this._stopPreviewPolling();

        this._loadPreviewImage();

        this._previewTimerId =
            setInterval(
                () => this._loadPreviewImage(),
                this._previewRefreshMs
            );
    }


    // ## Stop live preview polling.
    _stopPreviewPolling()
    {
        if (this._previewTimerId !== null)
        {
            clearInterval(
                this._previewTimerId
            );

            this._previewTimerId =
                null;
        }
    }


    // ## Load one live preview JPEG frame.
    _loadPreviewImage()
    {
        if (this._mode === "preview")
        {
            const image =
                document.getElementById(
                    "camera-image"
                );

            const placeholder =
                document.getElementById(
                    "preview-placeholder"
                );

            if (image !== null)
            {
                image.onload =
                    () =>
                    {
                        this._lastImageLoadTimeMs =
                            Date.now();

                        image.classList.remove(
                            "cameraImageHidden"
                        );

                        if (placeholder !== null)
                        {
                            placeholder.classList.add(
                                "cameraImageHidden"
                            );
                        }

                        this._updateImageAge();
                    };

                image.onerror =
                    () =>
                    {
                        if (this._mode === "preview")
                        {
                            if (placeholder !== null)
                            {
                                placeholder.textContent =
                                    "No preview frame";

                                placeholder.classList.remove(
                                    "cameraImageHidden"
                                );
                            }

                            image.classList.add(
                                "cameraImageHidden"
                            );

                            this._lastImageLoadTimeMs =
                                null;

                            this._updateImageAge();
                        }
                    };

                image.src =
                    "/preview.jpg?ts=" + Date.now();
            }
        }
    }


    // ## Show the live preview placeholder shell.
    _showImageShell()
    {
        const placeholder =
            document.getElementById(
                "preview-placeholder"
            );

        if (placeholder !== null)
        {
            placeholder.textContent =
                "Waiting for preview frame";

            placeholder.classList.remove(
                "cameraImageHidden"
            );
        }
    }


    // ## Hide live preview image and placeholder.
    _hideImage()
    {
        const image =
            document.getElementById(
                "camera-image"
            );

        const placeholder =
            document.getElementById(
                "preview-placeholder"
            );

        if (image !== null)
        {
            image.classList.add(
                "cameraImageHidden"
            );
        }

        if (placeholder !== null)
        {
            placeholder.classList.add(
                "cameraImageHidden"
            );
        }
    }


    // ## Load the selected MP4 capture for frame-oriented inspection.
    _showVideo(videoUrl)
    {
        const video =
            document.getElementById(
                "camera-video"
            );

        if (video !== null)
        {
            video.classList.remove(
                "cameraImageHidden"
            );

            video.controls =
                false;

            video.pause();

            video.src =
                videoUrl;

            video.load();

            const onLoadedMetadata =
                () =>
                {
                    video.removeEventListener(
                        "loadedmetadata",
                        onLoadedMetadata
                    );

                    this._setPlaybackFrameIndex(
                        this._playbackFrameIndex,
                        true
                    );
                };

            video.addEventListener(
                "loadedmetadata",
                onLoadedMetadata
            );
        }
    }


    // ## Hide playback video and unload the MP4 source.
    _hideVideo()
    {
        const video =
            document.getElementById(
                "camera-video"
            );

        if (video !== null)
        {
            video.pause();

            video.removeAttribute(
                "src"
            );

            video.load();

            video.classList.add(
                "cameraImageHidden"
            );
        }
    }


    // ## Show the live Status panel and hide frame-analysis fields.
    _showStatusContext()
    {
        const title =
            document.getElementById(
                "context-panel-title"
            );

        const statusPanel =
            document.getElementById(
                "system-summary-panel"
            );

        const analysisPanel =
            document.getElementById(
                "capture-analysis-panel"
            );

        if (title !== null)
        {
            title.textContent =
                "Status";
        }

        if (analysisPanel !== null)
        {
            analysisPanel.classList.add(
                "cameraImageHidden"
            );
        }

        if (statusPanel !== null)
        {
            statusPanel.classList.remove(
                "cameraImageHidden"
            );
        }
    }


    // ## Show the Frame Analysis panel and hide live status fields.
    _showFrameAnalysisContext(captureFile)
    {
        const title =
            document.getElementById(
                "context-panel-title"
            );

        const statusPanel =
            document.getElementById(
                "system-summary-panel"
            );

        const analysisPanel =
            document.getElementById(
                "capture-analysis-panel"
            );

        if (title !== null)
        {
            title.textContent =
                "Frame Analysis";
        }

        if (statusPanel !== null)
        {
            statusPanel.classList.add(
                "cameraImageHidden"
            );
        }

        if (analysisPanel !== null)
        {
            this._updateCaptureAnalysisValues(
                captureFile
            );

            analysisPanel.classList.remove(
                "cameraImageHidden"
            );
        }
    }


    // ## Copy sidecar values into the fixed frame-analysis fields.
    _updateCaptureAnalysisValues(captureFile)
    {
        const analysis =
            captureFile?.analysis || {};

        this._ensureCaptureAnalysisRow(
            "Trigger",
            "analysis-trigger-value",
            "analysis-duration-value"
        );

        this._ensureCaptureAnalysisRow(
            "Trigger Frame",
            "analysis-trigger-frame-value",
            "analysis-duration-value"
        );

        this._setElementText(
            "analysis-capture-value",
            captureFile?.capture_time_display ||
                captureFile?.display_name ||
                captureFile?.name ||
                "--"
        );

        this._setElementText(
            "analysis-trigger-value",
            this._formatTriggerDisplay(
                analysis
            )
        );

        this._setElementText(
            "analysis-trigger-frame-value",
            this._formatTriggerFrame(
                analysis
            )
        );

        this._setElementText(
            "analysis-duration-value",
            this._formatDuration(
                analysis.longest_event_ms
            )
        );

        this._setElementText(
            "analysis-frames-value",
            this._formatCount(
                analysis.frame_count
            )
        );

        this._setElementText(
            "analysis-components-value",
            this._formatCount(
                analysis.component_count
            )
        );

        this._setElementText(
            "analysis-valid-value",
            this._formatCount(
                analysis.valid_component_count
            )
        );

        this._setElementText(
            "analysis-area-value",
            this._formatCount(
                analysis.max_component_area
            )
        );

        this._setElementText(
            "analysis-height-width-value",
            (
                this._formatCount(
                    analysis.max_component_height
                ) +
                " / " +
                this._formatCount(
                    analysis.max_component_width
                )
            )
        );

        this._setElementText(
            "analysis-aspect-value",
            this._formatNumber(
                analysis.max_component_aspect
            )
        );
    }


    // ## Add a Frame Analysis row when older HTML does not define it.
    _ensureCaptureAnalysisRow(labelText, valueId, beforeValueId)
    {
        const existingValue =
            document.getElementById(
                valueId
            );

        const panel =
            document.getElementById(
                "capture-analysis-panel"
            );

        const beforeValue =
            document.getElementById(
                beforeValueId
            );

        if (existingValue === null && panel !== null)
        {
            const label =
                document.createElement(
                    "div"
                );

            const value =
                document.createElement(
                    "div"
                );

            label.textContent =
                labelText;

            value.id =
                valueId;

            value.textContent =
                "--";

            if (beforeValue !== null && beforeValue.previousElementSibling !== null)
            {
                panel.insertBefore(
                    label,
                    beforeValue.previousElementSibling
                );

                panel.insertBefore(
                    value,
                    beforeValue.previousElementSibling
                );
            }
            else
            {
                panel.appendChild(
                    label
                );

                panel.appendChild(
                    value
                );
            }
        }
    }


    // ## Create the playback timestamp overlay if the HTML does not define it.
    _ensurePlaybackOverlay()
    {
        let overlay =
            document.getElementById(
                "playback-frame-overlay"
            );

        const viewport =
            document.querySelector(
                ".mediaViewport"
            );

        if (overlay === null && viewport !== null)
        {
            overlay =
                document.createElement(
                    "div"
                );

            overlay.id =
                "playback-frame-overlay";

            overlay.className =
                "playbackFrameOverlay cameraImageHidden";

            viewport.appendChild(
                overlay
            );
        }
    }


    // ## Attach seek-completion handlers used to synchronize viewer state.
    _attachPlaybackOverlayEvents()
    {
        const video =
            document.getElementById(
                "camera-video"
            );

        if (video !== null)
        {
            this._detachPlaybackOverlayEvents();

            this._playbackTimeHandler =
                () =>
                {
                    this._playbackSeekPending =
                        false;

                    this._updatePlaybackOverlay();
                };

            video.addEventListener(
                "seeked",
                this._playbackTimeHandler
            );
        }
    }


    // ## Detach playback seek handlers.
    _detachPlaybackOverlayEvents()
    {
        const video =
            document.getElementById(
                "camera-video"
            );

        if (video !== null && this._playbackTimeHandler !== null)
        {
            video.removeEventListener(
                "seeked",
                this._playbackTimeHandler
            );
        }

        this._playbackTimeHandler =
            null;
    }


    // ## Hide the playback timestamp overlay.
    _hidePlaybackOverlay()
    {
        const overlay =
            document.getElementById(
                "playback-frame-overlay"
            );

        if (overlay !== null)
        {
            overlay.classList.add(
                "cameraImageHidden"
            );

            overlay.textContent =
                "";
        }
    }


    // ## Update overlay, graphs, slider, and frame label from logical frame state.
    _updatePlaybackOverlay()
    {
        const overlay =
            document.getElementById(
                "playback-frame-overlay"
            );

        const frameRecord =
            this._getCurrentFrameRecord();

        if (overlay !== null && frameRecord !== null)
        {
            overlay.textContent =
                this._formatFrameOverlayText(
                    frameRecord
                );

            overlay.classList.remove(
                "cameraImageHidden"
            );
        }
        else if (overlay !== null)
        {
            overlay.classList.add(
                "cameraImageHidden"
            );
        }

        this._updateCaptureGraphCursor(
            frameRecord
        );

        this._updatePlaybackViewerFrameValues(
            frameRecord
        );

        this._syncPlaybackSlider();
        this._updatePlaybackFrameLabel();
    }


    // ## Move capture graph cursor to the current logical playback frame.
    _updateCaptureGraphCursor(frameRecord)
    {
        if (
            this._metricsGraphPanel !== null &&
            frameRecord !== null
        )
        {
            this._metricsGraphPanel.setCaptureCursorFrameIndex(
                this._playbackFrameIndex
            );
        }
    }


    // ## Attach keyboard shortcuts for frame stepping during playback.
    _attachPlaybackKeyboardEvents()
    {
        this._detachPlaybackKeyboardEvents();

        this._playbackKeyHandler =
            (event) => this._handlePlaybackKeyDown(
                event
            );

        document.addEventListener(
            "keydown",
            this._playbackKeyHandler
        );
    }


    // ## Detach playback keyboard shortcuts.
    _detachPlaybackKeyboardEvents()
    {
        if (this._playbackKeyHandler !== null)
        {
            document.removeEventListener(
                "keydown",
                this._playbackKeyHandler
            );
        }

        this._playbackKeyHandler =
            null;

        // Logical frame selected by the viewer. This is authoritative while
        // playback mode is active; video.currentTime is only a transport used
        // to ask the browser to display that frame.
        this._playbackFrameIndex =
            0;

        this._playbackSeekPending =
            false;
    }


    // ## Handle arrow-key stepping while capture playback is active.
    _handlePlaybackKeyDown(event)
    {
        if (this._mode === "playback")
        {
            const activeTagName =
                String(document.activeElement?.tagName || "")
                    .toUpperCase();

            const isTextInput =
                activeTagName === "INPUT" ||
                activeTagName === "TEXTAREA" ||
                activeTagName === "SELECT";

            if (!isTextInput && event.key === "ArrowLeft")
            {
                event.preventDefault();

                this._stepPlaybackFrames(
                    event.shiftKey ? -10 : -1
                );
            }
            else if (!isTextInput && event.key === "ArrowRight")
            {
                event.preventDefault();

                this._stepPlaybackFrames(
                    event.shiftKey ? 10 : 1
                );
            }

        }
    }


    // ## Step by an integer number of logical sidecar frames.
    _stepPlaybackFrames(frameDelta)
    {
        this._setPlaybackFrameIndex(
            this._playbackFrameIndex + frameDelta
        );
    }


    // ## Select one logical frame and ask the video element to display it.
    _setPlaybackFrameIndex(
        frameIndex,
        force = false
    )
    {
        const video =
            document.getElementById(
                "camera-video"
            );

        const records =
            this._getPlaybackFrameRecords();

        if (video === null || records.length === 0)
        {
            return;
        }

        const clampedFrameIndex =
            Math.min(
                records.length - 1,
                Math.max(
                    0,
                    Number(frameIndex) || 0
                )
            );

        if (
            !force &&
            clampedFrameIndex === this._playbackFrameIndex
        )
        {
            this._updatePlaybackOverlay();
            return;
        }

        this._playbackFrameIndex =
            clampedFrameIndex;

        video.pause();

        const record =
            records[this._playbackFrameIndex];

        let targetSeconds =
            null;

        if (
            record.offset_ms !== null &&
            record.offset_ms !== undefined
        )
        {
            targetSeconds =
                Number(record.offset_ms) / 1000.0;
        }

        if (
            targetSeconds === null ||
            Number.isNaN(targetSeconds)
        )
        {
            targetSeconds =
                video.duration *
                this._playbackFrameIndex /
                Math.max(
                    1,
                    records.length - 1
                );
        }

        this._playbackSeekPending =
            true;

        video.currentTime =
            Math.min(
                Math.max(
                    targetSeconds,
                    0.0
                ),
                Math.max(
                    video.duration || targetSeconds,
                    targetSeconds
                )
            );

        // The selected frame is authoritative immediately for the slider/label.
        // Graphs and sidecar display will be refreshed again on the seeked event.
        this._syncPlaybackSlider();
        this._updatePlaybackFrameLabel();
    }


    // ## Configure the custom integer frame slider for the active capture.
    _configurePlaybackSlider()
    {
        const slider =
            document.getElementById(
                "playback-frame-slider"
            );

        const records =
            this._getPlaybackFrameRecords();

        if (slider !== null)
        {
            slider.min =
                "0";

            slider.max =
                String(
                    Math.max(
                        0,
                        records.length - 1
                    )
                );

            slider.step =
                "1";

            slider.value =
                String(
                    this._playbackFrameIndex
                );
        }

        this._updatePlaybackFrameLabel();
    }


    // ## Preview slider position on graphs without seeking the video.
    _previewSliderFrame()
    {
        const slider =
            document.getElementById(
                "playback-frame-slider"
            );

        const label =
            document.getElementById(
                "playback-frame-label"
            );

        const records =
            this._getPlaybackFrameRecords();

        if (
            slider !== null &&
            label !== null &&
            records.length > 0
        )
        {
            const previewIndex =
                Math.min(
                    records.length - 1,
                    Math.max(
                        0,
                        Number(slider.value) || 0
                    )
                );

            label.textContent =
                `${previewIndex + 1} / ${records.length}`;

            if (this._metricsGraphPanel !== null)
            {
                this._metricsGraphPanel.setCaptureCursorFrameIndex(
                    previewIndex
                );
            }
        }
    }


    // ## Commit one slider-selected frame after the user releases the slider.
    _commitSliderFrame()
    {
        const slider =
            document.getElementById(
                "playback-frame-slider"
            );

        if (slider !== null)
        {
            this._setPlaybackFrameIndex(
                Number(slider.value)
            );
        }
    }


    // ## Keep the custom slider synchronized with the logical frame index.
    _syncPlaybackSlider()
    {
        const slider =
            document.getElementById(
                "playback-frame-slider"
            );

        if (slider !== null)
        {
            slider.value =
                String(
                    this._playbackFrameIndex
                );
        }
    }


    // ## Display the current logical frame number and total frame count.
    _updatePlaybackFrameLabel()
    {
        const label =
            document.getElementById(
                "playback-frame-label"
            );

        const records =
            this._getPlaybackFrameRecords();

        if (label !== null)
        {
            if (records.length > 0)
            {
                label.textContent =
                    `${this._playbackFrameIndex + 1} / ${records.length}`;
            }
            else
            {
                label.textContent =
                    "0 / 0";
            }
        }
    }


    // ## Return frame records for current playback capture.
    _getPlaybackFrameRecords()
    {
        const records =
            this._playbackCaptureFile?.analysis?.frame_records || [];

        return records;
    }


    // ## Return the sidecar record for the current logical playback frame.
    _getCurrentFrameRecord()
    {
        const records =
            this._getPlaybackFrameRecords();

        if (records.length === 0)
        {
            return null;
        }

        const frameIndex =
            Math.min(
                records.length - 1,
                Math.max(
                    0,
                    this._playbackFrameIndex
                )
            );

        return records[
            frameIndex
        ];
    }


    // ## Format one frame overlay with UTC timestamp, frame, and offset.
    _formatFrameOverlayText(frameRecord)
    {
        const totalFrames =
            this._playbackCaptureFile?.analysis?.frame_count ||
            this._playbackCaptureFile?.analysis?.frame_records?.length ||
            "--";

        const frameNumber =
            Number(frameRecord.frame_index ?? 0) + 1;

        const timestamp =
            this._formatUtcText(
                frameRecord.timestamp_utc
            );

        const offsetText =
            this._formatElapsedMs(
                frameRecord.offset_ms
            );

        const text =
            `${timestamp}\n` +
            `Frame ${frameNumber} / ${totalFrames}\n` +
            `${offsetText}`;

        return text;
    }


    // ## Format UTC ISO text as readable overlay text.
    _formatUtcText(value)
    {
        let text =
            "-- UTC";

        if (value !== null && value !== undefined && value !== "")
        {
            text =
                String(value)
                    .replace("T", " ")
                    .replace("Z", "");

            if (text.includes("."))
            {
                const parts =
                    text.split(".");

                text =
                    parts[0] +
                    "." +
                    parts[1].slice(
                        0,
                        3
                    );
            }

            text +=
                " UTC";
        }

        return text;
    }


    // ## Format elapsed time from capture start.
    _formatElapsedMs(value)
    {
        let text =
            "+-- ms";

        if (value !== null && value !== undefined)
        {
            text =
                `+${Number(value).toFixed(1)} ms`;
        }

        return text;
    }


    // ## Format the trigger condition stored in the capture sidecar.
    _formatTriggerDisplay(analysis)
    {
        let text =
            "--";

        if (analysis.trigger_display !== null &&
            analysis.trigger_display !== undefined &&
            analysis.trigger_display !== "")
        {
            text =
                String(analysis.trigger_display);
        }

        if (analysis.trigger_reason !== null &&
            analysis.trigger_reason !== undefined &&
            analysis.trigger_reason !== "")
        {
            text +=
                ` (${analysis.trigger_reason})`;
        }

        return text;
    }


    // ## Format where the trigger was recognized inside the saved capture.
    _formatTriggerFrame(analysis)
    {
        let text =
            "--";

        const frameNumber =
            analysis.trigger_frame_number;

        if (frameNumber !== null && frameNumber !== undefined)
        {
            const totalFrames =
                analysis.frame_count ||
                analysis.frame_records?.length ||
                "--";

            text =
                `Frame ${frameNumber} / ${totalFrames}`;

            if (analysis.trigger_offset_ms !== null &&
                analysis.trigger_offset_ms !== undefined)
            {
                text +=
                    `, +${Number(analysis.trigger_offset_ms).toFixed(1)} ms`;
            }
        }
        else if (analysis.trigger_sequence_number !== null &&
            analysis.trigger_sequence_number !== undefined)
        {
            text =
                `Seq ${analysis.trigger_sequence_number}`;
        }

        return text;
    }


    // ## Format a millisecond duration for display.
    _formatDuration(value)
    {
        let text =
            "--";

        if (value !== null && value !== undefined)
        {
            text =
                `${Number(value).toFixed(1)} ms`;
        }

        return text;
    }


    // ## Format an integer count for display.
    _formatCount(value)
    {
        let text =
            "--";

        if (value !== null && value !== undefined)
        {
            text =
                String(value);
        }

        return text;
    }


    // ## Format a numeric value for display.
    _formatNumber(value)
    {
        let text =
            "--";

        if (value !== null && value !== undefined)
        {
            text =
                Number(value).toFixed(3);
        }

        return text;
    }


    // ## Resolve the capture path expected by the Pi replay endpoint.
    _resolvePlaybackCapturePath(
        videoUrl,
        captureFile
    )
    {
        const explicitPath =
            captureFile?.relative_path ||
            captureFile?.capture_path;

        if (
            explicitPath !== null &&
            explicitPath !== undefined &&
            explicitPath !== ""
        )
        {
            return String(
                explicitPath
            );
        }

        const urlText =
            String(
                videoUrl || ""
            );

        const marker =
            "/capture_files/";

        const markerIndex =
            urlText.indexOf(
                marker
            );

        if (markerIndex >= 0)
        {
            return decodeURIComponent(
                urlText.substring(
                    markerIndex +
                    marker.length
                )
            );
        }

        return (
            captureFile?.name ||
            ""
        );
    }


    // ## Replay the newly opened capture at the Pi's currently active sensitivity.
    async _loadInitialReplay()
    {
        try
        {
            const settings =
                await getJson(
                    "/candidate_settings"
                );

            this._viewerSensitivityProfiles =
                settings?.profiles || {};

            const sensitivity =
                String(
                    settings?.active?.sensitivity ||
                    "medium"
                ).toLowerCase();

            this._selectViewerSensitivity(
                sensitivity
            );

            this._showViewerSensitivityThresholds(
                sensitivity
            );

            await this._requestCaptureReplay(
                sensitivity
            );
        }
        catch (error)
        {
            this._setReplayFailure(
                "Unable to load replay settings"
            );

            console.error(
                error
            );
        }
    }


    // ## Rerun CandidateFinder/SolutionFilter when a sensitivity radio is clicked.
    async _handleViewerSensitivityChange(
        sensitivity
    )
    {
        // Threshold fields respond immediately to the selected profile.
        // MP4 replay may take longer because CandidateFinder reconstructs
        // bright-pixel metrics from the saved video.
        this._showViewerSensitivityThresholds(
            sensitivity
        );

        await this._requestCaptureReplay(
            sensitivity
        );
    }


    // ## Display the effective read-only thresholds for one sensitivity profile.
    _showViewerSensitivityThresholds(
        sensitivity
    )
    {
        const config =
            this._viewerSensitivityProfiles?.[
                sensitivity
            ] || {};

        this._setElementText(
            "viewer-threshold-brightness-delta",
            this._formatViewerNumber(
                config.
                    candidate_brightness_delta_threshold,
                3
            )
        );

        this._setElementText(
            "viewer-threshold-bright-pixel-delta",
            this._formatViewerNumber(
                config.
                    candidate_bright_pixel_delta_threshold,
                3
            )
        );

        this._setElementText(
            "viewer-threshold-bright-pixel-fraction",
            this._formatViewerNumber(
                config.
                    candidate_bright_pixel_fraction_threshold,
                6
            )
        );
    }


    // ## Ask the Pi backend to replay CandidateFinder and SolutionFilter.
    async _requestCaptureReplay(
        sensitivity
    )
    {
        if (
            this._mode !== "playback" ||
            !this._playbackCapturePath
        )
        {
            return;
        }

        const requestSerial =
            ++this._replayRequestSerial;

        this._setElementText(
            "viewer-replay-trigger-frame",
            "Evaluating..."
        );

        this._setSolutionViewer(
            "EVALUATING",
            "Running CandidateFinder and SolutionFilter..."
        );

        try
        {
            const response =
                await fetch(
                    "/capture_replay",
                    {
                        method: "POST",

                        headers:
                        {
                            "Content-Type":
                                "application/json"
                        },

                        body:
                            JSON.stringify(
                                {
                                    capture_path:
                                        this._playbackCapturePath,

                                    sensitivity:
                                        sensitivity
                                }
                            )
                    }
                );

            const result =
                await response.json();

            // Ignore an older replay result if the user clicked another radio.
            if (
                requestSerial !==
                this._replayRequestSerial
            )
            {
                return;
            }

            if (
                !response.ok ||
                !result.success
            )
            {
                throw new Error(
                    result.message ||
                    "Capture replay failed"
                );
            }

            this._applyReplayResult(
                result
            );
        }
        catch (error)
        {
            if (
                requestSerial ===
                this._replayRequestSerial
            )
            {
                this._setReplayFailure(
                    error.message ||
                    "Capture replay failed"
                );
            }

            console.error(
                error
            );
        }
    }


    // ## Update replay trigger, thresholds, graph marker, and Solution panel.
    _applyReplayResult(result)
    {
        const sensitivity =
            String(
                result.sensitivity ||
                "medium"
            ).toLowerCase();

        this._selectViewerSensitivity(
            sensitivity
        );

        const config =
            result.candidate_config || {};

        this._viewerSensitivityProfiles[
            sensitivity
        ] =
            config;

        this._setElementText(
            "viewer-threshold-brightness-delta",
            this._formatViewerNumber(
                config.
                    candidate_brightness_delta_threshold,
                3
            )
        );

        this._setElementText(
            "viewer-threshold-bright-pixel-delta",
            this._formatViewerNumber(
                config.
                    candidate_bright_pixel_delta_threshold,
                3
            )
        );

        this._setElementText(
            "viewer-threshold-bright-pixel-fraction",
            this._formatViewerNumber(
                config.
                    candidate_bright_pixel_fraction_threshold,
                6
            )
        );

        const candidate =
            result.candidate || {};

        if (
            candidate.frame_number !== null &&
            candidate.frame_number !== undefined
        )
        {
            this._setElementText(
                "viewer-replay-trigger-frame",
                String(
                    candidate.frame_number
                )
            );
        }
        else
        {
            this._setElementText(
                "viewer-replay-trigger-frame",
                "No candidate"
            );
        }

        if (this._metricsGraphPanel !== null)
        {
            this._metricsGraphPanel.
                setCaptureReplayTriggerFrameIndex(
                    candidate.frame_index
                );
        }

        const solution =
            result.solution || {};

        this._setSolutionViewer(
            solution.category || "UNCLASSIFIED",
            solution.reason || "--"
        );
    }


    // ## Select one sensitivity radio without firing another replay request.
    _selectViewerSensitivity(
        sensitivity
    )
    {
        document.querySelectorAll(
            'input[name="viewer-sensitivity"]'
        ).forEach(
            (radio) =>
            {
                radio.checked =
                    radio.value === sensitivity;
            }
        );
    }


    // ## Display Solution category/reason using Analyzer-like result color.
    _setSolutionViewer(
        category,
        reason
    )
    {
        const resultElement =
            document.getElementById(
                "viewer-solution-result"
            );

        if (resultElement !== null)
        {
            const normalizedCategory =
                String(
                    category || ""
                ).toUpperCase();

            resultElement.textContent =
                normalizedCategory ||
                "UNCLASSIFIED";

            resultElement.classList.remove(
                "solutionViewerPending",
                "solutionViewerTrue",
                "solutionViewerFalse"
            );

            if (
                normalizedCategory ===
                "TRUE_FLASH"
            )
            {
                resultElement.classList.add(
                    "solutionViewerTrue"
                );
            }
            else if (
                normalizedCategory ===
                "EVALUATING"
            )
            {
                resultElement.classList.add(
                    "solutionViewerPending"
                );
            }
            else
            {
                resultElement.classList.add(
                    "solutionViewerFalse"
                );
            }
        }

        this._setElementText(
            "viewer-solution-reason",
            reason || "--"
        );
    }


    // ## Show a replay failure without breaking video/frame inspection.
    _setReplayFailure(
        message
    )
    {
        this._setElementText(
            "viewer-replay-trigger-frame",
            "--"
        );

        if (this._metricsGraphPanel !== null)
        {
            this._metricsGraphPanel.
                setCaptureReplayTriggerFrameIndex(
                    null
                );
        }

        this._setSolutionViewer(
            "UNCLASSIFIED",
            message
        );
    }


    // ## Show the Analyzer-style capture viewer layout.
    _showPlaybackViewer()
    {
        const sidebar =
            document.getElementById(
                "playback-sidebar"
            );

        const navigation =
            document.getElementById(
                "playback-navigation"
            );

        if (sidebar !== null)
        {
            sidebar.classList.remove(
                "cameraImageHidden"
            );
        }

        if (navigation !== null)
        {
            navigation.classList.remove(
                "cameraImageHidden"
            );
        }
    }


    // ## Hide playback-only layout elements when returning to camera mode.
    _hidePlaybackViewer()
    {
        const sidebar =
            document.getElementById(
                "playback-sidebar"
            );

        const navigation =
            document.getElementById(
                "playback-navigation"
            );

        if (sidebar !== null)
        {
            sidebar.classList.add(
                "cameraImageHidden"
            );
        }

        if (navigation !== null)
        {
            navigation.classList.add(
                "cameraImageHidden"
            );
        }
    }


    // ## Read a nested sidecar value with a flat legacy fallback.
    _sidecarValue(
        sidecar,
        sectionName,
        key,
        legacyKey = null
    )
    {
        const section =
            sidecar?.[sectionName];

        if (
            section !== null &&
            typeof section === "object" &&
            section[key] !== undefined
        )
        {
            return section[key];
        }

        const fallbackKey =
            legacyKey ?? key;

        return sidecar?.[fallbackKey];
    }


    // ## Populate capture-level fields from current or legacy sidecars.
    _updatePlaybackViewerCaptureValues(captureFile)
    {
        const sidecar =
            captureFile?.analysis || {};

        const camera =
            sidecar.camera || {};

        const candidate =
            sidecar.candidate || {};

        this._setElementText(
            "viewer-capture-video",
            captureFile?.name ||
                captureFile?.display_name ||
                "--"
        );

        this._setElementText(
            "viewer-capture-start",
            this._formatUtcText(
                this._sidecarValue(
                    sidecar,
                    "capture",
                    "start_utc",
                    "capture_start_utc"
                )
            )
        );

        this._setElementText(
            "viewer-capture-trigger",
            candidate.trigger_display ||
                sidecar.trigger_display ||
                candidate.trigger_type ||
                sidecar.trigger_type ||
                "--"
        );

        this._setElementText(
            "viewer-capture-trigger-reason",
            candidate.trigger_reason ||
                sidecar.trigger_reason ||
                "--"
        );

        const piTriggerIndex =
            candidate.trigger_frame_index ??
            sidecar.trigger_frame_index;

        const piTriggerNumber =
            candidate.trigger_frame_number ??
            sidecar.trigger_frame_number ??
            (
                piTriggerIndex !== null &&
                piTriggerIndex !== undefined
                    ? Number(piTriggerIndex) + 1
                    : null
            );

        this._setElementText(
            "viewer-pi-trigger-frame",
            piTriggerNumber !== null &&
            piTriggerNumber !== undefined
                ? String(piTriggerNumber)
                : "--"
        );

        this._setElementText(
            "viewer-replay-trigger-frame",
            "--"
        );

        const triggerOffset =
            candidate.trigger_offset_ms ??
            sidecar.trigger_offset_ms;

        this._setElementText(
            "viewer-trigger-offset",
            triggerOffset !== null &&
            triggerOffset !== undefined
                ? `${Number(triggerOffset).toFixed(3)} ms`
                : "--"
        );

        this._setElementText(
            "viewer-site-name",
            camera.site_name ??
            sidecar.site_name ??
            "Flagstaff"
        );

        this._setElementText(
            "viewer-site-latitude",
            this._formatViewerNumber(
                camera.latitude_degrees ??
                sidecar.camera_latitude_degrees,
                7,
                "°"
            )
        );

        this._setElementText(
            "viewer-site-longitude",
            this._formatViewerNumber(
                camera.longitude_degrees ??
                sidecar.camera_longitude_degrees,
                7,
                "°"
            )
        );

        this._setElementText(
            "viewer-site-bearing",
            this._formatViewerNumber(
                camera.bearing_degrees ??
                sidecar.camera_bearing_degrees,
                1,
                "°"
            )
        );

        this._setElementText(
            "viewer-site-hfov",
            this._formatViewerNumber(
                camera.hfov_degrees ??
                sidecar.camera_hfov_degrees,
                1,
                "°"
            )
        );

        this._setElementText(
            "viewer-site-vfov",
            this._formatViewerNumber(
                camera.vfov_degrees ??
                sidecar.camera_vfov_degrees,
                1,
                "°"
            )
        );

        const bounds =
            sidecar.search_bounding_box ||
            camera.search_bounding_box;

        let boundsText =
            "--";

        if (bounds && typeof bounds === "object")
        {
            const minLat =
                bounds.min_latitude ??
                bounds.min_latitude_degrees;

            const maxLat =
                bounds.max_latitude ??
                bounds.max_latitude_degrees;

            const minLon =
                bounds.min_longitude ??
                bounds.min_longitude_degrees;

            const maxLon =
                bounds.max_longitude ??
                bounds.max_longitude_degrees;

            if (
                [minLat, maxLat, minLon, maxLon].every(
                    (value) =>
                        value !== null &&
                        value !== undefined &&
                        Number.isFinite(
                            Number(value)
                        )
                )
            )
            {
                boundsText =
                    `${Number(minLat).toFixed(5)}, ` +
                    `${Number(minLon).toFixed(5)} to ` +
                    `${Number(maxLat).toFixed(5)}, ` +
                    `${Number(maxLon).toFixed(5)}`;
            }
        }

        this._setElementText(
            "viewer-search-bounds",
            boundsText
        );

        document.querySelectorAll(
            'input[name="viewer-sensitivity"]'
        ).forEach(
            (radio) =>
            {
                radio.disabled =
                    false;
            }
        );

        const config =
            candidate.config ||
            sidecar.candidate_config ||
            {};

        this._setElementText(
            "viewer-threshold-brightness-delta",
            this._formatViewerNumber(
                config.candidate_brightness_delta_threshold,
                3
            )
        );

        this._setElementText(
            "viewer-threshold-bright-pixel-delta",
            this._formatViewerNumber(
                config.candidate_bright_pixel_delta_threshold,
                3
            )
        );

        this._setElementText(
            "viewer-threshold-bright-pixel-fraction",
            this._formatViewerNumber(
                config.candidate_bright_pixel_fraction_threshold,
                6
            )
        );
    }


    // ## Populate fields that change as the user steps through the capture.
    _updatePlaybackViewerFrameValues(frameRecord)
    {
        const records =
            this._getPlaybackFrameRecords();

        if (
            frameRecord === null ||
            frameRecord === undefined
        )
        {
            return;
        }

        const frameIndex =
            Number(
                frameRecord.frame_index ??
                this._playbackFrameIndex
            );

        this._setElementText(
            "viewer-current-frame",
            `${frameIndex + 1} / ${records.length}`
        );

        this._setElementText(
            "viewer-current-timestamp",
            this._formatUtcText(
                frameRecord.timestamp_utc
            )
        );

        this._setElementText(
            "viewer-current-offset",
            frameRecord.offset_ms !== null &&
            frameRecord.offset_ms !== undefined
                ? `${Number(frameRecord.offset_ms).toFixed(3)} ms`
                : "--"
        );

        this._setElementText(
            "viewer-current-brightness",
            this._formatViewerNumber(
                frameRecord.mean_brightness,
                3
            )
        );

        this._setElementText(
            "viewer-current-brightness-change",
            this._formatViewerNumber(
                frameRecord.brightness_delta_adjacent,
                3
            )
        );
    }


    // ## Format a viewer numeric field with optional suffix.
    _formatViewerNumber(
        value,
        digits = 3,
        suffix = ""
    )
    {
        if (
            value === null ||
            value === undefined ||
            value === ""
        )
        {
            return "--";
        }

        const numericValue =
            Number(value);

        if (!Number.isFinite(numericValue))
        {
            return String(value);
        }

        return (
            numericValue.toFixed(
                digits
            ) +
            suffix
        );
    }


    // ## Update the media panel title text.
    _setMediaTitle(titleText)
    {
        const mediaTitle =
            document.getElementById(
                "media-title"
            );

        if (mediaTitle !== null)
        {
            mediaTitle.textContent =
                titleText;
        }
    }


    // ## Set text on an element if it exists.
    _setElementText(elementId, text)
    {
        const element =
            document.getElementById(
                elementId
            );

        if (element !== null)
        {
            element.textContent =
                text;
        }
    }


    // ## Show live-preview image age when the camera preview is active.
    _showImageAge()
    {
        const imageAge =
            document.getElementById(
                "image-age"
            );

        if (imageAge !== null)
        {
            imageAge.classList.remove(
                "cameraImageHidden"
            );
        }
    }


    // ## Hide live-preview image age while inspecting a saved capture.
    _hideImageAge()
    {
        const imageAge =
            document.getElementById(
                "image-age"
            );

        if (imageAge !== null)
        {
            imageAge.classList.add(
                "cameraImageHidden"
            );
        }
    }


    // ## Update the displayed live preview image age.
    _updateImageAge()
    {
        const imageAge =
            document.getElementById(
                "image-age"
            );

        if (imageAge !== null)
        {
            if (this._lastImageLoadTimeMs === null)
            {
                imageAge.textContent =
                    "Age: --";
            }
            else
            {
                const ageSeconds =
                    Math.floor(
                        (
                            Date.now() -
                            this._lastImageLoadTimeMs
                        ) / 1000
                    );

                imageAge.textContent =
                    `Age: ${ageSeconds}s`;
            }
        }
    }


    // ## Bind a click handler if the element exists.
    _bindClick(elementId, handler)
    {
        const element =
            document.getElementById(
                elementId
            );

        if (element !== null)
        {
            element.addEventListener(
                "click",
                handler
            );
        }
    }
}
