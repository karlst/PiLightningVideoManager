"use strict";

import { postJson } from "./httpClient.js";


/*
 * Modeless live preview plus transition into/out of the shared capture viewer.
 *
 * The dashboard itself does not poll /preview.jpg.  Preview traffic exists only
 * while the user explicitly opens the floating preview window.
 */
export class PreviewPanel
{
    constructor(statusPanel, eventLogPanel, metricsGraphPanel = null)
    {
        this._statusPanel = statusPanel;
        this._eventLogPanel = eventLogPanel;
        this._metricsGraphPanel = metricsGraphPanel;

        this._previewTimerId = null;
        this._countdownTimerId = null;
        this._lastImageLoadTimeMs = null;
        this._previewRefreshMs = 200;
        this._previewTimeoutMs = 5 * 60 * 1000;
        this._previewDeadlineMs = null;
        this._previewOpen = false;
        this._mode = "dashboard";
        this._captureViewer = null;

        document.body.classList.remove("capturePlaybackMode");
    }


    initialize()
    {
        this._captureViewer =
            document.getElementById("capture-viewer");

        this._bindClick(
            "show-preview-button",
            () => this.openPreview()
        );

        this._bindClick(
            "close-preview-button",
            () => this.closePreview()
        );

        this._bindClick(
            "capture-button",
            () => this.captureOnce()
        );

        this._bindClick(
            "close-playback-button",
            () => this.closePlayback()
        );

        this.closePreview();
    }


    // The regular /system_status heartbeat carries preview configuration, so
    // PreviewPanel never needs its own status request.
    updateConfiguration(result)
    {
        const refreshSeconds = Number(
            result?.camera_preview_refresh_seconds ?? 0.2
        );

        const timeoutSeconds = Number(
            result?.camera_preview_timeout_seconds ?? 300
        );

        if (Number.isFinite(refreshSeconds) && refreshSeconds > 0)
        {
            this._previewRefreshMs = Math.max(
                100,
                refreshSeconds * 1000
            );
        }

        if (Number.isFinite(timeoutSeconds) && timeoutSeconds > 0)
        {
            this._previewTimeoutMs = timeoutSeconds * 1000;
        }
    }


    async captureOnce()
    {
        this._statusPanel.setStatus("Capturing...");

        try
        {
            const result = await postJson("/capture_once");

            this._statusPanel.setStatus(
                result.success ? "Capture Complete" : "Capture Failed"
            );
        }
        catch (error)
        {
            this._statusPanel.setStatus("Communication Error");
            console.error(error);
        }
    }


    openPreview()
    {
        if (this._mode === "playback")
        {
            return;
        }

        this._previewOpen = true;
        this._previewDeadlineMs = Date.now() + this._previewTimeoutMs;
        this._lastImageLoadTimeMs = null;

        const panel = document.getElementById("preview-window");
        panel?.classList.remove("previewWindowHidden");

        const placeholder = document.getElementById("camera-image-placeholder");
        if (placeholder !== null)
        {
            placeholder.textContent = "Waiting for preview frame";
            placeholder.classList.remove("cameraImageHidden");
        }

        document.getElementById("camera-preview-image")?.classList.add(
            "cameraImageHidden"
        );

        this._stopPreviewPolling();
        this._loadPreviewImage();
        this._startCountdown();
    }


    closePreview()
    {
        this._previewOpen = false;
        this._previewDeadlineMs = null;
        this._stopPreviewPolling();
        this._stopCountdown();

        document.getElementById("preview-window")?.classList.add(
            "previewWindowHidden"
        );
    }


    async showPlaybackMode(videoUrl, captureFile = null)
    {
        let resolvedVideoUrl = videoUrl;
        let resolvedCaptureFile = captureFile;

        if (typeof videoUrl === "object" && videoUrl !== null)
        {
            resolvedCaptureFile = videoUrl;
            resolvedVideoUrl = videoUrl.url;
        }

        if (this._captureViewer === null)
        {
            console.error("capture-viewer element is not available.");
            return;
        }

        this.closePreview();
        this._mode = "playback";

        try
        {
            await this._captureViewer.loadCapture(
                {
                    videoUrl: resolvedVideoUrl,
                    captureFile: resolvedCaptureFile
                }
            );

            document.body.classList.add("capturePlaybackMode");
        }
        catch (error)
        {
            console.error(error);
            this._statusPanel.setStatus("Capture Load Failed");
            this._mode = "dashboard";
        }
    }


    closePlayback()
    {
        this._mode = "dashboard";
        document.body.classList.remove("capturePlaybackMode");

        if (this._captureViewer !== null)
        {
            this._captureViewer.clearCapture();
        }
    }


    // Completion-driven preview loop: the next request is scheduled only after
    // the current image has loaded or failed.  Requests can never overlap.
    _loadPreviewImage()
    {
        if (!this._previewOpen || this._mode === "playback")
        {
            return;
        }

        if (
            this._previewDeadlineMs !== null &&
            Date.now() >= this._previewDeadlineMs
        )
        {
            this.closePreview();
            return;
        }

        const image = document.getElementById("camera-preview-image");
        const placeholder = document.getElementById("camera-image-placeholder");

        if (image === null)
        {
            return;
        }

        image.onload =
            () =>
            {
                if (!this._previewOpen)
                {
                    return;
                }

                this._lastImageLoadTimeMs = Date.now();
                image.classList.remove("cameraImageHidden");
                placeholder?.classList.add("cameraImageHidden");
                this._scheduleNextPreview();
            };

        image.onerror =
            () =>
            {
                if (!this._previewOpen)
                {
                    return;
                }

                if (placeholder !== null)
                {
                    placeholder.textContent = "No preview frame";
                    placeholder.classList.remove("cameraImageHidden");
                }

                image.classList.add("cameraImageHidden");
                this._lastImageLoadTimeMs = null;
                this._scheduleNextPreview();
            };

        image.src = "/preview.jpg?ts=" + Date.now();
    }


    _scheduleNextPreview()
    {
        this._stopPreviewPolling();

        if (!this._previewOpen)
        {
            return;
        }

        this._previewTimerId = window.setTimeout(
            () => this._loadPreviewImage(),
            this._previewRefreshMs
        );
    }


    _stopPreviewPolling()
    {
        if (this._previewTimerId !== null)
        {
            window.clearTimeout(this._previewTimerId);
            this._previewTimerId = null;
        }
    }


    _startCountdown()
    {
        this._stopCountdown();
        this._updateCountdown();

        this._countdownTimerId = window.setInterval(
            () => this._updateCountdown(),
            1000
        );
    }


    _stopCountdown()
    {
        if (this._countdownTimerId !== null)
        {
            window.clearInterval(this._countdownTimerId);
            this._countdownTimerId = null;
        }
    }


    _updateCountdown()
    {
        const element = document.getElementById("preview-time-remaining");

        if (element === null || this._previewDeadlineMs === null)
        {
            return;
        }

        const remainingSeconds = Math.max(
            0,
            Math.ceil((this._previewDeadlineMs - Date.now()) / 1000)
        );

        if (remainingSeconds <= 0)
        {
            this.closePreview();
            return;
        }

        const minutes = Math.floor(remainingSeconds / 60);
        const seconds = remainingSeconds % 60;
        element.textContent =
            `Closes in ${minutes}:${String(seconds).padStart(2, "0")}`;
    }


    _bindClick(elementId, handler)
    {
        const element = document.getElementById(elementId);

        if (element !== null)
        {
            element.addEventListener("click", handler);
        }
    }
}
