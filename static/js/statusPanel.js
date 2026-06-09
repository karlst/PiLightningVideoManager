"use strict";

import
{
    getJson
}
from "./httpClient.js";


export class StatusPanel
{
    constructor()
    {
        this._systemSampleHandler =
            null;
    }


    setSystemSampleHandler(handler)
    {
        this._systemSampleHandler =
            handler;
    }


    setStatus(statusText)
    {
        const statusValue =
            document.getElementById(
                "status-value"
            );

        if (statusValue !== null)
        {
            statusValue.textContent =
                statusText;
        }
    }


    async updateSystemStatus()
    {
        try
        {
            const result =
                await getJson(
                    "/system_status"
                );

            const heartbeatValue =
                document.getElementById(
                    "heartbeat-value"
                );

            if (heartbeatValue !== null)
            {
                heartbeatValue.textContent =
                    `| Server: ${result.server_time_utc} ` +
                    `| Preview: ${result.preview_running ? "on" : "off"} ` +
                    `| Buffer: ${result.buffer_running ? "on" : "off"} ` +
                    `| FPS: ${result.camera_fps.toFixed(1)} ` +
                    `| Frames: ${result.camera_frames} ` +
                    `| Buffer: ${result.buffer_count}/${result.buffer_capacity} ` +
                    `| RAM: ${result.memory_mb.toFixed(0)} MB`;
            }

            if (this._systemSampleHandler !== null)
            {
                this._systemSampleHandler(
                    result
                );
            }
        }
        catch (error)
        {
            console.error(
                error
            );
        }
    }
}
