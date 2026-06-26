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

        this._playbackCaptureFile =
            null;

        this._playbackTimeHandler =
            null;

        this._playbackKeyHandler =
            null;
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
            "playback-play-pause-button",
            () => this._togglePlayback()
        );

        this._bindClick(
            "playback-step-forward-1-button",
            () => this._stepPlaybackFrames(1)
        );

        this._bindClick(
            "playback-step-forward-10-button",
            () => this._stepPlaybackFrames(10)
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

        this._playbackCaptureFile =
            null;

        this._setMediaTitle(
            "Live Camera"
        );

        this._detachPlaybackOverlayEvents();
        this._detachPlaybackKeyboardEvents();
        this._hidePlaybackOverlay();
        this._hidePlaybackStepControls();
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

        this._playbackCaptureFile =
            resolvedCaptureFile;

        this._setMediaTitle(
            "Capture Playback"
        );

        this._stopPreviewPolling();
        this._hideImage();
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

        this._updatePlaybackPlayPauseButton();
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


    // ## Load and play the selected MP4 capture.
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
                true;

            video.src =
                videoUrl;

            video.load();

            video.play().catch(
                (error) =>
                {
                    console.error(
                        error
                    );
                }
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


    // ## Attach video time handlers used to refresh the frame timestamp overlay.
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
                () => this._updatePlaybackOverlay();

            video.addEventListener(
                "timeupdate",
                this._playbackTimeHandler
            );

            video.addEventListener(
                "seeked",
                this._playbackTimeHandler
            );

            video.addEventListener(
                "loadedmetadata",
                this._playbackTimeHandler
            );

            video.addEventListener(
                "play",
                this._playbackTimeHandler
            );

            video.addEventListener(
                "pause",
                this._playbackTimeHandler
            );
        }
    }


    // ## Detach playback overlay video handlers.
    _detachPlaybackOverlayEvents()
    {
        const video =
            document.getElementById(
                "camera-video"
            );

        if (video !== null && this._playbackTimeHandler !== null)
        {
            video.removeEventListener(
                "timeupdate",
                this._playbackTimeHandler
            );

            video.removeEventListener(
                "seeked",
                this._playbackTimeHandler
            );

            video.removeEventListener(
                "loadedmetadata",
                this._playbackTimeHandler
            );

            video.removeEventListener(
                "play",
                this._playbackTimeHandler
            );

            video.removeEventListener(
                "pause",
                this._playbackTimeHandler
            );
        }

        this._playbackTimeHandler =
            null;

        this._playbackKeyHandler =
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


    // ## Update timestamp overlay using current video time and sidecar frames.
    _updatePlaybackOverlay()
    {
        const overlay =
            document.getElementById(
                "playback-frame-overlay"
            );

        const video =
            document.getElementById(
                "camera-video"
            );

        const frameRecord =
            this._getCurrentFrameRecord(
                video
            );

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

        this._updatePlaybackPlayPauseButton();
    }


    // ## Move capture graph cursor to the current playback frame.
    _updateCaptureGraphCursor(frameRecord)
    {
        if (
            this._metricsGraphPanel !== null &&
            frameRecord !== null
        )
        {
            this._metricsGraphPanel.setCaptureCursorFrameIndex(
                Number(frameRecord.frame_index ?? 0)
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
            else if (!isTextInput && event.key === " ")
            {
                event.preventDefault();

                this._togglePlayback();
            }
        }
    }


    // ## Toggle video play/pause from the custom playback control bar.
    _togglePlayback()
    {
        const video =
            document.getElementById(
                "camera-video"
            );

        if (video !== null)
        {
            if (video.paused)
            {
                video.play().catch(
                    (error) =>
                    {
                        console.error(
                            error
                        );
                    }
                );
            }
            else
            {
                video.pause();
            }
        }

        this._updatePlaybackPlayPauseButton();
    }


    // ## Step playback by an integer number of sidecar frame records.
    _stepPlaybackFrames(frameDelta)
    {
        const video =
            document.getElementById(
                "camera-video"
            );

        const records =
            this._getPlaybackFrameRecords();

        if (video !== null && records.length > 0)
        {
            video.pause();

            const currentFrameIndex =
                this._getCurrentFrameIndex(
                    video
                );

            const nextFrameIndex =
                Math.min(
                    records.length - 1,
                    Math.max(
                        0,
                        currentFrameIndex + frameDelta
                    )
                );

            this._seekPlaybackToFrameIndex(
                video,
                nextFrameIndex
            );
        }
    }


    // ## Seek video to the requested sidecar frame index.
    _seekPlaybackToFrameIndex(video, frameIndex)
    {
        const records =
            this._getPlaybackFrameRecords();

        if (records.length > 0)
        {
            const record =
                records[frameIndex];

            let targetSeconds =
                null;

            if (record.offset_ms !== null && record.offset_ms !== undefined)
            {
                targetSeconds =
                    Number(record.offset_ms) / 1000.0;
            }

            if (targetSeconds === null || Number.isNaN(targetSeconds))
            {
                targetSeconds =
                    video.duration *
                    frameIndex /
                    Math.max(
                        1,
                        records.length - 1
                    );
            }

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

            this._updatePlaybackOverlay();
        }
    }


    // ## Return current frame index based on video time and sidecar records.
    _getCurrentFrameIndex(video)
    {
        let frameIndex =
            0;

        const records =
            this._getPlaybackFrameRecords();

        if (video !== null && records.length > 0)
        {
            if (records[0]?.offset_ms !== null && records[0]?.offset_ms !== undefined)
            {
                const currentMs =
                    video.currentTime * 1000.0;

                frameIndex =
                    this._findNearestFrameRecordIndex(
                        records,
                        currentMs
                    );
            }
            else
            {
                frameIndex =
                    Math.min(
                        records.length - 1,
                        Math.max(
                            0,
                            Math.round(
                                video.currentTime *
                                Math.max(
                                    records.length - 1,
                                    1
                                ) /
                                Math.max(
                                    video.duration || 0.001,
                                    0.001
                                )
                            )
                        )
                    );
            }
        }

        return frameIndex;
    }


    // ## Find the sidecar frame nearest the requested elapsed milliseconds.
    _findNearestFrameRecordIndex(records, currentMs)
    {
        let low =
            0;

        let high =
            records.length - 1;

        while (low < high)
        {
            const middle =
                Math.floor(
                    (low + high) / 2
                );

            const middleMs =
                Number(records[middle].offset_ms ?? 0.0);

            if (middleMs < currentMs)
            {
                low =
                    middle + 1;
            }
            else
            {
                high =
                    middle;
            }
        }

        let index =
            low;

        if (index > 0)
        {
            const previousDistance =
                Math.abs(
                    Number(records[index - 1].offset_ms ?? 0.0) -
                    currentMs
                );

            const currentDistance =
                Math.abs(
                    Number(records[index].offset_ms ?? 0.0) -
                    currentMs
                );

            if (previousDistance <= currentDistance)
            {
                index =
                    index - 1;
            }
        }

        return index;
    }


    // ## Return frame records for current playback capture.
    _getPlaybackFrameRecords()
    {
        const records =
            this._playbackCaptureFile?.analysis?.frame_records || [];

        return records;
    }


    // ## Update play/pause button label.
    _updatePlaybackPlayPauseButton()
    {
        const button =
            document.getElementById(
                "playback-play-pause-button"
            );

        const video =
            document.getElementById(
                "camera-video"
            );

        if (button !== null && video !== null)
        {
            button.textContent =
                video.paused ? "Play" : "Pause";
        }
    }


    // ## Resolve current video time to the nearest sidecar frame record.
    _getCurrentFrameRecord(video)
    {
        let frameRecord =
            null;

        const analysis =
            this._playbackCaptureFile?.analysis || {};

        const records =
            analysis.frame_records || [];

        if (video !== null && records.length > 0)
        {
            const frameIndex =
                this._getCurrentFrameIndex(
                    video
                );

            frameRecord =
                records[frameIndex];
        }

        return frameRecord;
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
