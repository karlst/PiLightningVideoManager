"use strict";

import
{
    postJson,
    getJson
}
from "./httpClient.js";


export class BufferPanel
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
        /* disable ... No longer used
        this._bindClick(
            "buffer-start-button",
            () => this.start()
        );

        this._bindClick(
            "buffer-stop-button",
            () => this.stop()
        );
        // ... end disable */

        this._bindClick(
            "buffer-capture-button",
            () => this.capture()
        );

        /* disable ... No longer used
        this._bindClick(
            "buffer-status-button",
            () => this.status()
        );
        // ... end disable */

        this.status();

    }


    async start()
    {
        try
        {
            const result =
                await postJson(
                    "/buffer_start"
                );

            this._statusPanel.setStatus(
                result.message
            );

            this._eventLogPanel.refresh();
            this.status();
        }
        catch (error)
        {
            this._statusPanel.setStatus(
                "Buffer Start Failed"
            );

            console.error(
                error
            );
        }
    }


    async stop()
    {
        try
        {
            const result =
                await postJson(
                    "/buffer_stop"
                );

            this._statusPanel.setStatus(
                result.message
            );

            this._eventLogPanel.refresh();
            this.status();
        }
        catch (error)
        {
            this._statusPanel.setStatus(
                "Buffer Stop Failed"
            );

            console.error(
                error
            );
        }
    }


    async capture()
    {
        try
        {
            const result =
                await postJson(
                    "/buffer_capture"
                );

            this._statusPanel.setStatus(
                result.message
            );

            this._eventLogPanel.refresh();
        }
        catch (error)
        {
            this._statusPanel.setStatus(
                "Buffer Capture Failed"
            );

            console.error(
                error
            );
        }
    }


    async status()
    {
        try
        {
            const result =
                await getJson(
                    "/buffer_status"
                );

            document.getElementById(
                "buffer-status-value"
            ).textContent =
                JSON.stringify(
                    result,
                    null,
                    2
                );

            this._statusPanel.setStatus(
                result.message
            );
        }
        catch (error)
        {
            this._statusPanel.setStatus(
                "Buffer Status Failed"
            );

            console.error(
                error
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
