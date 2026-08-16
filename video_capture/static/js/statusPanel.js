"use strict";

import
{
    getJson
}
from "./httpClient.js";


// ## Set text on an element if it exists.
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


// ## Format a numeric value with a fixed number of decimal places.
function formatNumber(value, digits, fallback)
{
    const numberValue =
        Number(value);

    let result =
        fallback;

    if (Number.isFinite(numberValue))
    {
        result =
            numberValue.toFixed(
                digits
            );
    }

    return result;
}


// ## Format a boolean value as On or Off.
function formatOnOff(value)
{
    const result =
        value ? "On" : "Off";

    return result;
}


// ## Updates the top status bar and operational status panel.
export class StatusPanel
{
    // ## Initialize status callbacks.
    constructor()
    {
        this._systemSampleHandler =
            null;

        this._systemStatusHandler =
            null;
    }


    // ## Register a callback for graph/system samples.
    setSystemSampleHandler(handler)
    {
        this._systemSampleHandler =
            handler;
    }


    // ## Register a callback for full system status updates.
    setSystemStatusHandler(handler)
    {
        this._systemStatusHandler =
            handler;
    }


    // ## Update the short status message in the header.
    setStatus(statusText)
    {
        setElementText(
            "status-value",
            statusText
        );
    }


    // ## Fetch current system status and update dependent panels.
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

            this._updateSystemSummary(
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


    // ## Update camera configuration values when those elements are present.
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


    // ## Header no longer shows operational status; keep method as a no-op.
    _updateHeartbeat(result)
    {
        void result;
    }


    // ## Update UTC and legacy trigger state fields if present.
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

        setElementText(
            "trigger-enabled-text",
            result.trigger_enabled ? "Trigger: Enabled" : "Trigger: Disabled"
        );
    }


    // ## Update the operational Status panel.
    _updateSystemSummary(result)
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

        const chipTemperature =
            formatNumber(
                result.chip_temperature_c,
                1,
                "--"
            );

        setElementText(
            "header-version-value",
            result.app_version ?? "--"
        );

        setElementText(
            "summary-version-value",
            result.app_version ?? "--"
        );

        setElementText(
            "summary-started-value",
            result.application_start_utc ?? "--"
        );

        setElementText(
            "summary-trigger-value",
            result.trigger_enabled ? "Enabled" : "Disabled"
        );

        const sensitivity =
            result.
                trigger_status?.
                candidate_config?.
                sensitivity;

        setElementText(
            "summary-sensitivity-value",
            sensitivity
                ? (
                    sensitivity.charAt(0).toUpperCase() +
                    sensitivity.slice(1)
                )
                : "--"
        );

        setElementText(
            "summary-fps-value",
            fps
        );

        setElementText(
            "summary-chip-temp-value",
            `${chipTemperature} °C`
        );

        setElementText(
            "summary-buffer-value",
            `${result.buffer_count ?? "--"} / ${result.buffer_capacity ?? "--"}`
        );

        setElementText(
            "summary-frames-value",
            result.camera_frames ?? "--"
        );

        setElementText(
            "summary-ram-value",
            `${memoryMb} MB`
        );

        setElementText(
            "summary-preview-value",
            formatOnOff(
                result.preview_running
            )
        );

        setElementText(
            "summary-error-value",
            result.last_error || "None"
        );
    }
}