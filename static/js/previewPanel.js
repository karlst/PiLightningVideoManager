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
    constructor(statusPanel, eventLogPanel)
    {
        this._statusPanel =
            statusPanel;

        this._eventLogPanel =
            eventLogPanel;

        this._previewTimerId =
            null;

        this._lastImageLoadTimeMs =
            null;

        this._previewRefreshMs =
            1000;

        this._mode =
            "preview";
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


    // ## Request a manual capture from the server.
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

        this._setMediaTitle(
            "Live Camera"
        );

        this._hideCaptureAnalysis();
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
        this._mode =
            "playback";

        this._setMediaTitle(
            "Capture Playback"
        );

        this._stopPreviewPolling();
        this._hideImage();
        this._showVideo(
            videoUrl
        );

        this._showCaptureAnalysis(
            captureFile
        );

        this._showClosePlaybackButton();
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


    // ## Show readable sidecar analysis during capture playback.
    _showCaptureAnalysis(captureFile)
    {
        const panel =
            this._getCaptureAnalysisPanel();

        if (panel !== null)
        {
            panel.replaceChildren();

            if (captureFile === null)
            {
                panel.textContent =
                    "No capture analysis available.";
            }
            else
            {
                this._appendAnalysisHeader(
                    panel,
                    captureFile
                );

                this._appendAnalysisGrid(
                    panel,
                    captureFile.analysis || captureFile
                );
            }

            panel.classList.remove(
                "cameraImageHidden"
            );
        }
    }


    // ## Hide the playback analysis panel.
    _hideCaptureAnalysis()
    {
        const panel =
            document.getElementById(
                "capture-analysis-panel"
            );

        if (panel !== null)
        {
            panel.classList.add(
                "cameraImageHidden"
            );
        }
    }


    // ## Create the analysis panel lazily inside the media viewport.
    _getCaptureAnalysisPanel()
    {
        let panel =
            document.getElementById(
                "capture-analysis-panel"
            );

        if (panel === null)
        {
            const viewport =
                document.querySelector(
                    ".mediaViewport"
                );

            if (viewport !== null)
            {
                panel =
                    document.createElement(
                        "div"
                    );

                panel.id =
                    "capture-analysis-panel";

                panel.className =
                    "captureAnalysisPanel cameraImageHidden";

                viewport.appendChild(
                    panel
                );
            }
        }

        return panel;
    }


    // ## Add capture name/title to the analysis panel.
    _appendAnalysisHeader(panel, captureFile)
    {
        const title =
            document.createElement(
                "div"
            );

        title.className =
            "captureAnalysisTitle";

        title.textContent =
            captureFile.display_name ||
            captureFile.name ||
            "Capture Analysis";

        panel.appendChild(
            title
        );
    }


    // ## Add the sidecar values as a compact readable table.
    _appendAnalysisGrid(panel, analysis)
    {
        const grid =
            document.createElement(
                "div"
            );

        grid.className =
            "captureAnalysisGrid";

        this._appendAnalysisRow(
            grid,
            "Frames",
            this._formatCount(analysis.frame_count)
        );

        this._appendAnalysisRow(
            grid,
            "Components",
            this._formatCount(analysis.component_count)
        );

        this._appendAnalysisRow(
            grid,
            "Valid Components",
            this._formatCount(analysis.valid_component_count)
        );

        this._appendAnalysisRow(
            grid,
            "Longest Event",
            this._formatDuration(analysis.longest_event_ms)
        );

        this._appendAnalysisRow(
            grid,
            "Max Area",
            this._formatCount(analysis.max_component_area)
        );

        this._appendAnalysisRow(
            grid,
            "Max Height",
            this._formatCount(analysis.max_component_height)
        );

        this._appendAnalysisRow(
            grid,
            "Max Width",
            this._formatCount(analysis.max_component_width)
        );

        this._appendAnalysisRow(
            grid,
            "Max Aspect",
            this._formatNumber(analysis.max_component_aspect)
        );

        panel.appendChild(
            grid
        );
    }


    // ## Add one label/value row to the analysis grid.
    _appendAnalysisRow(grid, labelText, valueText)
    {
        const label =
            document.createElement(
                "div"
            );

        label.className =
            "captureAnalysisLabel";

        label.textContent =
            labelText;

        const value =
            document.createElement(
                "div"
            );

        value.className =
            "captureAnalysisValue";

        value.textContent =
            valueText;

        grid.appendChild(
            label
        );

        grid.appendChild(
            value
        );
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
