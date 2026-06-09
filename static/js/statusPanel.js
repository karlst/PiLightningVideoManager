"use strict";

import
{
    getJson
}
from "./httpClient.js";


function setElementText(elementId, text)
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


function formatNumber(value, digits, fallback)
{
    const numberValue =
        Number(value);

    if (!Number.isFinite(numberValue))
    {
        return fallback;
    }

    return numberValue.toFixed(
        digits
    );
}


export class StatusPanel
{
    constructor()
    {
        this._systemSampleHandler =
            null;

        this._systemStatusHandler =
            null;
    }


    setSystemSampleHandler(handler)
    {
        this._systemSampleHandler =
            handler;
    }


    setSystemStatusHandler(handler)
    {
        this._systemStatusHandler =
            handler;
    }


    setStatus(statusText)
    {
        setElementText(
            "status-value",
            statusText
        );
    }


    async updateSystemStatus()
    {
        try
        {
            const result =
                await getJson(
                    "/system_status"
                );

            this._updateHeartbeat(
                result
            );

            this._updateLiveStatus(
                result
            );

            this._updateCameraInfo(
                result
            );

            if (this._systemStatusHandler !== null)
            {
                this._systemStatusHandler(
                    result
                );
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

            this.setStatus(
                "System status failed"
            );
        }
    }

    _updateCameraInfo(result)
    {
        setElementText(
            "camera-name-value",
            result.camera_name
        );

        setElementText(
            "camera-format-value",
            result.camera_format
        );

        setElementText(
            "camera-frame-value",
            `${result.camera_frame_width_pixels} x ${result.camera_frame_height_pixels}`
        );

        setElementText(
            "camera-target-fps-value",
            result.camera_target_fps
        );

        if (result.camera_geometry)
        {
            setElementText(
                "camera-latitude-value",
                Number(
                    result.camera_geometry.latitude_degrees
                ).toFixed(7)
            );

            setElementText(
                "camera-longitude-value",
                Number(
                    result.camera_geometry.longitude_degrees
                ).toFixed(7)
            );

            setElementText(
                "camera-bearing-value",
                Number(
                    result.camera_geometry.bearing_degrees
                ).toFixed(1) + "°"
            );

            setElementText(
                "camera-hfov-value",
                Number(
                    result.camera_geometry.hfov_degrees
                ).toFixed(1) + "°"
            );

            setElementText(
                "camera-vfov-value",
                Number(
                    result.camera_geometry.vfov_degrees
                ).toFixed(1) + "°"
            );
        }
    }


    _updateHeartbeat(result)
    {
        const fps =
            formatNumber(
                result.camera_fps,
                1,
                "--"
            );

        const memoryMb =
            formatNumber(
                result.memory_mb,
                0,
                "--"
            );

        setElementText(
            "heartbeat-value",
            `| Server: ${result.server_time_utc} ` +
            `| Preview: ${result.preview_running ? "on" : "off"} ` +
            `| Buffer: ${result.buffer_running ? "on" : "off"} ` +
            `| FPS: ${fps} ` +
            `| Frames: ${result.camera_frames ?? "--"} ` +
            `| Buffer: ${result.buffer_count ?? "--"}/${result.buffer_capacity ?? "--"} ` +
            `| RAM: ${memoryMb} MB`
        );
    }


    _updateLiveStatus(result)
    {
        setElementText(
            "utc-time-value",
            result.server_time_utc ?? "--:--:--"
        );

        setElementText(
            "trigger-state-value",
            result.trigger_enabled ? "Armed" : "Disabled"
        );
    }
}