"use strict";

import
{
    getJson
}
from "./httpClient.js";


export class DialogPanel
{
    constructor(previewPanel)
    {
        this._previewPanel =
            previewPanel;

        this._dialog =
            null;

        this._title =
            null;

        this._body =
            null;
    }


    initialize()
    {
        this._dialog =
            document.getElementById(
                "app-dialog"
            );

        this._title =
            document.getElementById(
                "app-dialog-title"
            );

        this._body =
            document.getElementById(
                "app-dialog-body"
            );

        this._bindClick(
            "trigger-settings-button",
            () => this.showTriggerSettings()
        );

        this._bindClick(
            "camera-settings-button",
            () => this.showCameraSettings()
        );

        this._bindClick(
            "browse-captures-button",
            () => this.showBrowseCaptures()
        );

        this._bindClick(
            "app-dialog-close-button",
            () => this.close()
        );

        this._bindClick(
            "about-button",
            () => this.showAbout()
        );
    }

    showAbout()
    {
        this._showText(
            "About",
            "Pi Camera Capture\n\nSnapshot preview from ring buffer.\nMP4 trigger captures.\nMetrics graphs.\nEvent logging."
        );
    }


    showTriggerSettings()
    {
        this._showText(
            "Trigger Settings",
            "TODO\n\nBrightness delta threshold\nMotion threshold\nPre-trigger seconds\nPost-trigger seconds"
        );
    }


    showCameraSettings()
    {
        this._showText(
            "Camera Settings",
            "TODO\n\nDevice\nFormat\nFrame size\nFPS\nLocation\nBearing\nFOV"
        );
    }


    async showBrowseCaptures()
    {
        this._setTitle(
            "Browse Captures"
        );

        this._clearBody();

        const captureList =
            document.createElement(
                "div"
            );

        captureList.className =
            "captureList";

        this._body.appendChild(
            captureList
        );

        try
        {
            const result =
                await getJson(
                    "/captures"
                );

            if (!result.success || result.files.length === 0)
            {
                captureList.textContent =
                    "No captures found.";
            }
            else
            {
                result.files.forEach(
                    (captureFile) =>
                    {
                        const button =
                            document.createElement(
                                "button"
                            );

                        button.className =
                            "captureListButton";

                        button.type =
                            "button";

                        button.textContent =
                            captureFile.name;

                        button.addEventListener(
                            "click",
                            () =>
                            {
                                this.close();

                                this._previewPanel.showPlaybackMode(
                                    captureFile.url
                                );
                            }
                        );

                        captureList.appendChild(
                            button
                        );
                    }
                );
            }
        }
        catch (error)
        {
            captureList.textContent =
                "Failed to load captures.";

            console.error(
                error
            );
        }

        this._dialog.showModal();
    }


    close()
    {
        if (this._dialog !== null)
        {
            this._dialog.close();
        }
    }


    _showText(titleText, bodyText)
    {
        this._setTitle(
            titleText
        );

        this._clearBody();

        this._body.textContent =
            bodyText;

        this._dialog.showModal();
    }


    _setTitle(titleText)
    {
        if (this._title !== null)
        {
            this._title.textContent =
                titleText;
        }
    }


    _clearBody()
    {
        if (this._body !== null)
        {
            this._body.replaceChildren();
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