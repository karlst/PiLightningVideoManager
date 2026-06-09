"use strict";


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


function formatDegrees(value, digits, fallback)
{
    const numberValue =
        Number(value);

    if (!Number.isFinite(numberValue))
    {
        return fallback;
    }

    return (
        numberValue.toFixed(
            digits
        ) +
        "°"
    );
}


export class CameraPanel
{
    updateFromSystemStatus(result)
    {
        setElementText(
            "camera-device-value",
            result.camera_device ?? "--"
        );

        setElementText(
            "camera-format-value",
            result.camera_format ?? "--"
        );

        setElementText(
            "camera-frame-size-value",
            (
                `${result.camera_width_pixels ?? "--"} x ` +
                `${result.camera_height_pixels ?? "--"}`
            )
        );

        setElementText(
            "camera-target-fps-value",
            formatNumber(
                result.camera_target_fps,
                0,
                "--"
            )
        );

        this._updateGeometry(
            result.camera_geometry
        );
    }


    _updateGeometry(cameraGeometry)
    {
        if (!cameraGeometry)
        {
            return;
        }

        setElementText(
            "camera-latitude-value",
            formatNumber(
                cameraGeometry.latitude_degrees,
                7,
                "--.-------"
            )
        );

        setElementText(
            "camera-longitude-value",
            formatNumber(
                cameraGeometry.longitude_degrees,
                7,
                "--.-------"
            )
        );

        setElementText(
            "camera-bearing-value",
            formatDegrees(
                cameraGeometry.bearing_degrees,
                1,
                "---.-°"
            )
        );

        setElementText(
            "camera-hfov-value",
            formatDegrees(
                cameraGeometry.hfov_degrees,
                1,
                "--.-°"
            )
        );

        setElementText(
            "camera-vfov-value",
            formatDegrees(
                cameraGeometry.vfov_degrees,
                1,
                "--.-°"
            )
        );
    }
}