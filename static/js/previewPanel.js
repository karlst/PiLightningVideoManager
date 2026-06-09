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
    }


    initialize()
    {
        this._bindClick(
            "capture-button",
            () => this.captureOnce()
        );

        this._bindClick(
            "preview-start-button",
            () => this.startPreview()
        );

        this._bindClick(
            "preview-stop-button",
            () => this.stopPreview()
        );

        this.updatePreviewStatus();
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


    async startPreview()
    {
        try
        {
            const result =
                await postJson(
                    "/preview_start"
                );

            this._statusPanel.setStatus(
                result.message
            );

            if (result.success)
            {
                this._showPreview();
            }

            this._eventLogPanel.refresh();
        }
        catch (error)
        {
            this._statusPanel.setStatus(
                "Preview Start Failed"
            );

            console.error(
                error
            );
        }
    }


    async stopPreview()
    {
        try
        {
            const result =
                await postJson(
                    "/preview_stop"
                );

            this._statusPanel.setStatus(
                result.message
            );

            if (result.success)
            {
                this._hidePreview();
            }

            this._eventLogPanel.refresh();
        }
        catch (error)
        {
            this._statusPanel.setStatus(
                "Preview Stop Failed"
            );

            console.error(
                error
            );
        }
    }


    async updatePreviewStatus()
    {
        try
        {
            const result =
                await getJson(
                    "/preview_status"
                );

            if (result.running)
            {
                this._statusPanel.setStatus(
                    "Preview Running"
                );

                this._showPreview();
            }
            else
            {
                this._hidePreview();
            }
        }
        catch (error)
        {
            console.error(
                error
            );
        }
    }


    _showPreview()
    {
        const video =
            document.getElementById(
                "camera-video"
            );

        const placeholder =
            document.getElementById(
                "preview-placeholder"
            );

        if ((video !== null) && (placeholder !== null))
        {
            placeholder.classList.add(
                "cameraImageHidden"
            );

            video.classList.remove(
                "cameraImageHidden"
            );

            video.src =
                "/hls/stream.m3u8";

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


    _hidePreview()
    {
        const video =
            document.getElementById(
                "camera-video"
            );

        const placeholder =
            document.getElementById(
                "preview-placeholder"
            );

        if ((video !== null) && (placeholder !== null))
        {
            video.pause();

            video.removeAttribute(
                "src"
            );

            video.load();

            video.classList.add(
                "cameraImageHidden"
            );

            placeholder.classList.remove(
                "cameraImageHidden"
            );
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
