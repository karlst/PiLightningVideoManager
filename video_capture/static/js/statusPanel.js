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




// ## Sum selected telemetry fields over buckets overlapping the last N minutes.
function sumRecentBuckets(telemetry, minutes, fields)
{
    const totals = {};

    fields.forEach(
        (field) =>
        {
            totals[field] = 0;
        }
    );

    const buckets =
        Array.isArray(telemetry?.buckets)
            ? telemetry.buckets
            : [];

    const bucketSeconds =
        Number(telemetry?.bucket_seconds ?? 300);

    const cutoffMs =
        Date.now() - (minutes * 60 * 1000);

    buckets.forEach(
        (bucket) =>
        {
            const startMs =
                Date.parse(bucket?.start_utc ?? "");

            if (
                Number.isFinite(startMs) &&
                (startMs + bucketSeconds * 1000) > cutoffMs
            )
            {
                fields.forEach(
                    (field) =>
                    {
                        totals[field] +=
                            Number(bucket?.[field] ?? 0);
                    }
                );
            }
        }
    );

    return totals;
}


// ## Compact UTC timestamp for status rows.
function formatUtcTimestamp(value)
{
    if (!value)
    {
        return "--";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime()))
    {
        return String(value);
    }

    return date.toLocaleString(
        undefined,
        {
            timeZone: "UTC",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false
        }
    ) + " UTC";
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

        const captureTelemetry =
            result.capture_telemetry || {};

        const psfTelemetry =
            result.psf_telemetry || {};

        let psfText =
            "Not running";

        if (psfTelemetry.available)
        {
            psfText =
                psfTelemetry.running
                    ? "Running"
                    : "Not running (stale)";
        }

        setElementText(
            "summary-psf-value",
            psfText
        );

        const captureHour =
            sumRecentBuckets(
                captureTelemetry,
                60,
                ["captures"]
            );

        setElementText(
            "summary-captures-hour-value",
            captureTelemetry.available
                ? String(captureHour.captures)
                : "--"
        );

        const psfHour =
            sumRecentBuckets(
                psfTelemetry,
                60,
                [
                    "flash",
                    "anomaly",
                    "s3_success",
                    "s3_failure"
                ]
            );

        setElementText(
            "summary-classifications-hour-value",
            psfTelemetry.available
                ? (
                    `${psfHour.flash} FLASH / ` +
                    `${psfHour.anomaly} ANOMALY`
                )
                : "--"
        );

        const fieldPi =
            psfTelemetry.ap_active === true;

        let s3HourText = "--";
        let s3LastText = "--";

        if (fieldPi)
        {
            s3HourText = "N/A — offline";
            s3LastText = "N/A — offline";
        }
        else if (psfTelemetry.available)
        {
            if (psfTelemetry.configured_upload_to_s3 === false)
            {
                s3HourText = "Disabled";
                s3LastText = "Disabled";
            }
            else
            {
                s3HourText =
                    `${psfHour.s3_success} OK / ` +
                    `${psfHour.s3_failure} failed`;

                s3LastText =
                    formatUtcTimestamp(
                        psfTelemetry.last_upload_utc
                    );
            }
        }

        setElementText(
            "summary-s3-hour-value",
            s3HourText
        );

        setElementText(
            "summary-s3-last-value",
            s3LastText
        );

        setElementText(
            "summary-error-value",
            result.last_error ||
            psfTelemetry.last_error ||
            "None"
        );
    }
}