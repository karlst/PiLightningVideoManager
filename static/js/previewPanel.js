"use strict";

import
{
    postJson,
    getJson
}
from "./httpClient.js";


export class PreviewPanel
{
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


    showPreviewMode()
    {
        this._mode =
            "preview";

        this._setMediaTitle(
            "Live Camera"
        );

        this._hideVideo();
        this._showImageShell();
        this._startPreviewPolling();
        this._hideClosePlaybackButton();
    }


    showPlaybackMode(videoUrl)
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

        this._showClosePlaybackButton();
    }


    closePlayback()
    {
        this.showPreviewMode();
    }

    _showClosePlaybackButton()
    {
        const button =
            document.getElementById("close-playback-button");

        if (button !== null)
        {
            button.classList.remove("cameraImageHidden");
        }
    }


    _hideClosePlaybackButton()
    {
        const button =
            document.getElementById("close-playback-button");

        if (button !== null)
        {
            button.classList.add("cameraImageHidden");
        }
    }


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


    _loadPreviewImage()
    {
        if (this._mode !== "preview")
        {
            return;
        }

        const image =
            document.getElementById(
                "camera-image"
            );

        const placeholder =
            document.getElementById(
                "preview-placeholder"
            );

        if (image === null)
        {
            return;
        }

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
                if (this._mode !== "preview")
                {
                    return;
                }

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
            };

        image.src =
            "/preview.jpg?ts=" + Date.now();
    }


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


    _updateImageAge()
    {
        const imageAge =
            document.getElementById(
                "image-age"
            );

        if (imageAge === null)
        {
            return;
        }

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