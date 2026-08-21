"use strict";

import
{
    postJson,
    getJson
}
from "./httpClient.js";


/*
 * Manages only the P Site's live camera preview and the transition into/out of
 * the shared <capture-viewer> component.
 *
 * Capture playback itself intentionally no longer lives here.  That logic is
 * isolated in captureViewer.js so the exact same viewer can be used on the Pi
 * and on soloran.com.
 */
export class PreviewPanel
{
    constructor(statusPanel, eventLogPanel, metricsGraphPanel = null)
    {
        this._statusPanel = statusPanel;
        this._eventLogPanel = eventLogPanel;
        this._metricsGraphPanel = metricsGraphPanel;
        this._previewTimerId = null;
        this._lastImageLoadTimeMs = null;
        this._previewRefreshMs = 1000;
        this._mode = "preview";
        this._captureViewer = null;

        document.body.classList.remove("capturePlaybackMode");
    }


    // Bind live-preview controls and locate the shared capture viewer.
    initialize()
    {
        this._captureViewer =
            document.getElementById("capture-viewer");

        this._bindClick(
            "capture-button",
            () => this.captureOnce()
        );

        this._bindClick(
            "close-playback-button",
            () => this.closePlayback()
        );

        this._loadPreviewConfig();
    }


    // Read preview refresh timing and start live preview mode.
    async _loadPreviewConfig()
    {
        try
        {
            const result =
                await getJson("/system_status");

            this._previewRefreshMs =
                Math.max(
                    100,
                    Number(result.camera_preview_refresh_seconds ?? 1.0) * 1000
                );
        }
        catch (error)
        {
            console.error(error);
        }

        this.showPreviewMode();
    }


    // Request a single legacy camera capture from the server.
    async captureOnce()
    {
        this._statusPanel.setStatus("Capturing...");

        try
        {
            const result = await postJson("/capture_once");

            this._statusPanel.setStatus(
                result.success ? "Capture Complete" : "Capture Failed"
            );

            this._eventLogPanel.refresh();
        }
        catch (error)
        {
            this._statusPanel.setStatus("Communication Error");
            console.error(error);
        }
    }


    // Restore the normal Pi live-camera page.
    showPreviewMode()
    {
        this._mode = "preview";
        document.body.classList.remove("capturePlaybackMode");

        if (this._captureViewer !== null)
        {
            this._captureViewer.clearCapture();
        }

        this._showImageShell();
        this._startPreviewPolling();
    }


    /*
     * Enter shared capture playback.  DialogPanel deliberately keeps calling
     * this method, so Browse Captures does not need to know anything about the
     * Web Component refactor.
     */
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

        this._mode = "playback";
        this._stopPreviewPolling();
        this._hideImage();

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
            this.showPreviewMode();
        }
    }


    // Return from the shared viewer to the live Pi camera page.
    closePlayback()
    {
        this.showPreviewMode();
    }


    // Start polling for live preview JPEG frames.
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


    // Stop live preview polling.
    _stopPreviewPolling()
    {
        if (this._previewTimerId !== null)
        {
            clearInterval(this._previewTimerId);
            this._previewTimerId = null;
        }
    }


    // Load one live preview JPEG frame.
    _loadPreviewImage()
    {
        if (this._mode !== "preview")
        {
            return;
        }

        const image = document.getElementById("camera-image");
        const placeholder = document.getElementById("preview-placeholder");

        if (image === null)
        {
            return;
        }

        image.onload =
            () =>
            {
                this._lastImageLoadTimeMs = Date.now();
                image.classList.remove("cameraImageHidden");
                placeholder?.classList.add("cameraImageHidden");
                this._updateImageAge();
            };

        image.onerror =
            () =>
            {
                if (this._mode !== "preview")
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
                this._updateImageAge();
            };

        image.src = "/preview.jpg?ts=" + Date.now();
    }


    // Show the live preview placeholder shell.
    _showImageShell()
    {
        const placeholder = document.getElementById("preview-placeholder");
        const imageAge = document.getElementById("image-age");

        if (placeholder !== null)
        {
            placeholder.textContent = "Waiting for preview frame";
            placeholder.classList.remove("cameraImageHidden");
        }

        imageAge?.classList.remove("cameraImageHidden");
    }


    // Hide live preview image and placeholder while the capture viewer is open.
    _hideImage()
    {
        document.getElementById("camera-image")?.classList.add("cameraImageHidden");
        document.getElementById("preview-placeholder")?.classList.add("cameraImageHidden");
        document.getElementById("image-age")?.classList.add("cameraImageHidden");
    }


    // Update the displayed live preview image age.
    _updateImageAge()
    {
        const imageAge = document.getElementById("image-age");

        if (imageAge === null)
        {
            return;
        }

        if (this._lastImageLoadTimeMs === null)
        {
            imageAge.textContent = "Age: --";
        }
        else
        {
            const ageSeconds = Math.floor(
                (Date.now() - this._lastImageLoadTimeMs) / 1000
            );

            imageAge.textContent = `Age: ${ageSeconds}s`;
        }
    }


    // Bind a click handler if the P Site element exists.
    _bindClick(elementId, handler)
    {
        const element = document.getElementById(elementId);

        if (element !== null)
        {
            element.addEventListener("click", handler);
        }
    }
}
