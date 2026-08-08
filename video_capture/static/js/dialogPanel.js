"use strict";

import
{
    getJson
}
from "./httpClient.js";


export class DialogPanel
{
    // ## Initialize dialog references and remember the preview panel.
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


    // ## Bind dialog buttons and initialize dialog DOM references.
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

    // ## Show the About dialog.
    showAbout()
    {
        this._showHtml(
            "About",
            `
            <div class="aboutBox">
                <h3>Pi Camera Capture</h3>

                <p>
                    Pi Camera Capture is a high-speed video capture and event
                    detection system for lightning strokes, weather events,
                    wildlife activity, and other short-duration events.
                </p>

                <p>
                    At the heart of the system is a continuous ring buffer architecture. 
                    Video frames are captured at high frame rates and stored in memory, 
                    allowing the system to retain several seconds of history before an event occurs. 
                    When a trigger condition is detected, the buffer contents are preserved and written to an MP4 video file, 
                    capturing both the event and the moments leading up to it.
                </p>

                <h4>Key Features</h4>

                <ul>
                    <li>Continuous high-speed ring buffer capture</li>
                    <li>Automatic triggering from brightness, brightness delta, and motion metrics</li>
                    <li>Manual trigger capture</li>
                    <li>Pre-trigger and post-trigger video recording</li>
                    <li>MP4 capture storage and browser playback</li>
                    <li>Live camera preview from buffered frames</li>
                    <li>Configurable camera, trigger, location, bearing, and field-of-view settings</li>
                    <li>Real-time graphs for brightness, trigger metrics, motion, and system status</li>
                    <li>Event logging and system diagnostics</li>
                    <li>Web control from desktop, tablet, or phone</li>
                    <li>Remote access through Tailscale without exposing the Pi to the public internet</li>
                </ul>

                <h4>Triggering System</h4>
                <p>
                The trigger engine continuously analyzes incoming video frames and computes metrics such as scene brightness, 
                brightness change, and motion activity. 
                Trigger thresholds are fully configurable and can be tuned for specific applications. 
                Automatic triggering allows the system to operate unattended while still 
                capturing short-duration events that would otherwise be missed.
                </p>

                <h4>Ring Buffer Architecture</h4>
                <p>
                The ring buffer maintains a fixed-size rolling history of recent frames. 
                As new frames arrive, the oldest frames are automatically overwritten. 
                When a trigger occurs, the buffer contents are preserved, providing a complete record of what happened before, 
                during, and after the event. This approach allows the system to capture unpredictable events 
                without continuously recording large video files.
                </p>

                <h4>Capture Management</h4>
                <p>
                Triggered events are stored as MP4 video files and may be reviewed directly through the web interface. 
                Automatic file management prevents storage exhaustion by removing older captures while preserving recent recordings.
                </p>

                <h4>System Monitoring</h4>
                <p>
                The application continuously tracks frame rate, memory usage, buffer utilization, 
                brightness metrics, motion metrics, and trigger activity. Historical graphs and event logs 
                provide insight into system performance and environmental conditions over time.
                </p>

                <p>
                    The goal is unattended operation: the Pi watches continuously,
                    captures rare events automatically, and lets the user review
                    saved clips through the web interface.
                </p>
            </div>
            `
        );
    }


    // ## Show editable CandidateFinder trigger settings.
    async showTriggerSettings()
    {
        this._setTitle(
            "Trigger Settings"
        );

        this._clearBody();

        const container =
            document.createElement(
                "div"
            );

        const status =
            document.createElement(
                "div"
            );

        status.textContent =
            "Loading...";

        container.appendChild(
            status
        );

        this._body.appendChild(
            container
        );

        this._dialog.showModal();

        try
        {
            const result =
                await getJson(
                    "/candidate_settings"
                );

            const activeThreshold =
                Number(
                    result.active?.candidate_brightness_delta_threshold
                );

            const defaultThreshold =
                Number(
                    result.default?.candidate_brightness_delta_threshold
                );

            container.replaceChildren();

            const label =
                document.createElement(
                    "label"
                );

            label.textContent =
                "Delta Brightness Threshold";

            const input =
                document.createElement(
                    "input"
                );

            input.type =
                "number";

            input.step =
                "0.1";

            input.min =
                "0";

            input.value =
                Number.isFinite(activeThreshold)
                    ? activeThreshold
                    : "";

            const defaultText =
                document.createElement(
                    "div"
                );

            defaultText.textContent =
                (
                    "Default: " +
                    (
                        Number.isFinite(defaultThreshold)
                            ? defaultThreshold
                            : "--"
                    )
                );

            const message =
                document.createElement(
                    "div"
                );

            const buttonBar =
                document.createElement(
                    "div"
                );

            const saveButton =
                document.createElement(
                    "button"
                );

            saveButton.type =
                "button";

            saveButton.textContent =
                "Save";

            const resetButton =
                document.createElement(
                    "button"
                );

            resetButton.type =
                "button";

            resetButton.textContent =
                "Reset Default";

            saveButton.addEventListener(
                "click",
                async () =>
                {
                    const threshold =
                        Number(
                            input.value
                        );

                    if (!Number.isFinite(threshold) || threshold < 0.0)
                    {
                        message.textContent =
                            "Enter a number greater than or equal to 0.";

                        return;
                    }

                    try
                    {
                        const response =
                            await fetch(
                                "/candidate_settings",
                                {
                                    method: "POST",
                                    headers: {
                                        "Content-Type": "application/json"
                                    },
                                    body: JSON.stringify(
                                        {
                                            candidate_brightness_delta_threshold:
                                                threshold
                                        }
                                    )
                                }
                            );

                        const result =
                            await response.json();

                        message.textContent =
                            result.message ||
                            (
                                response.ok
                                    ? "Saved"
                                    : "Save failed"
                            );

                        if (response.ok && result.success)
                        {
                            input.value =
                                result.active.candidate_brightness_delta_threshold;
                        }
                    }
                    catch (error)
                    {
                        message.textContent =
                            "Save failed.";

                        console.error(
                            error
                        );
                    }
                }
            );

            resetButton.addEventListener(
                "click",
                async () =>
                {
                    try
                    {
                        const response =
                            await fetch(
                                "/candidate_settings_reset",
                                {
                                    method: "POST"
                                }
                            );

                        const result =
                            await response.json();

                        message.textContent =
                            result.message ||
                            (
                                response.ok
                                    ? "Reset"
                                    : "Reset failed"
                            );

                        if (response.ok && result.success)
                        {
                            input.value =
                                result.active.candidate_brightness_delta_threshold;
                        }
                    }
                    catch (error)
                    {
                        message.textContent =
                            "Reset failed.";

                        console.error(
                            error
                        );
                    }
                }
            );

            buttonBar.appendChild(
                saveButton
            );

            buttonBar.appendChild(
                resetButton
            );

            container.appendChild(
                label
            );

            container.appendChild(
                document.createElement(
                    "br"
                )
            );

            container.appendChild(
                input
            );

            container.appendChild(
                defaultText
            );

            container.appendChild(
                buttonBar
            );

            container.appendChild(
                message
            );
        }
        catch (error)
        {
            status.textContent =
                "Failed to load trigger settings.";

            console.error(
                error
            );
        }
    }


    // ## Show placeholder camera settings dialog content.
    showCameraSettings()
    {
        this._showText(
            "Camera Settings",
            "TODO\n\nDevice\nFormat\nFrame size\nFPS\nLocation\nBearing\nFOV"
        );
    }


    // ## Show the capture browser with timing, trigger, and sidecar columns.
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
                const header =
                    document.createElement(
                        "div"
                    );

                header.className =
                    "captureListHeader";

                header.innerHTML =
                    "<span>Time UTC</span>" +
                    "<span>Trigger</span>" +
                    "<span>Duration</span>" +
                    "<span>Valid</span>";

                captureList.appendChild(
                    header
                );

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

                        button.appendChild(
                            this._createCaptureCell(
                                this._formatCaptureTime(
                                    captureFile
                                )
                            )
                        );

                        button.appendChild(
                            this._createCaptureCell(
                                this._formatTrigger(
                                    captureFile
                                )
                            )
                        );

                        button.appendChild(
                            this._createCaptureCell(
                                this._formatDuration(
                                    captureFile.capture_duration_ms
                                )
                            )
                        );

                        button.appendChild(
                            this._createCaptureCell(
                                this._formatCount(
                                    captureFile.valid_component_count
                                )
                            )
                        );

                        button.addEventListener(
                            "click",
                            () =>
                            {
                                this.close();

                                this._previewPanel.showPlaybackMode(
                                    captureFile.url,
                                    captureFile
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


    // ## Close the active dialog.
    close()
    {
        if (this._dialog !== null)
        {
            this._dialog.close();
        }
    }


    // ## Create one display cell for the capture browser row.
    _createCaptureCell(text)
    {
        const span =
            document.createElement(
                "span"
            );

        span.textContent =
            text;

        return span;
    }


    // ## Format the preferred capture time from trigger/capture sidecar data.
    _formatCaptureTime(captureFile)
    {
        const analysis =
            captureFile?.analysis || {};

        let text =
            captureFile?.capture_time_display ||
            analysis.candidate?.trigger_utc ||
            analysis.capture?.start_utc ||
            analysis.trigger_utc ||
            analysis.capture_start_utc ||
            "--";

        if (text !== "--" && !text.includes("UTC"))
        {
            text =
                this._formatUtcText(
                    text
                );
        }

        return text;
    }


    // ## Format the trigger condition for the capture browser.
    _formatTrigger(captureFile)
    {
        const analysis =
            captureFile?.analysis || {};

        const text =
            captureFile?.trigger_display ||
            analysis.candidate?.trigger_display ||
            analysis.trigger_display ||
            "--";

        return text;
    }


    // ## Format UTC ISO text as a compact readable UTC value.
    _formatUtcText(value)
    {
        let text =
            "--";

        if (value !== null && value !== undefined && value !== "")
        {
            text =
                String(value)
                    .replace("T", " ")
                    .replace("Z", "");

            if (text.includes("."))
            {
                const parts =
                    text.split(".");

                text =
                    parts[0] +
                    "." +
                    parts[1].slice(
                        0,
                        3
                    );
            }

            text +=
                " UTC";
        }

        return text;
    }


    // ## Format a millisecond duration for the capture browser.
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


    // ## Format a component count for the capture browser.
    _formatCount(value)
    {
        let text =
            "--";

        if (value !== null && value !== undefined)
        {
            text =
                String(
                    value
                );
        }

        return text;
    }


    // ## Show plain text content in the dialog.
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

    // ## Show trusted HTML content in the dialog.
    _showHtml(titleText, htmlText)
    {
        this._setTitle(
            titleText
        );

        this._clearBody();

        this._body.innerHTML =
            htmlText;

        this._dialog.showModal();
    }


    // ## Set the dialog title.
    _setTitle(titleText)
    {
        if (this._title !== null)
        {
            this._title.textContent =
                titleText;
        }
    }


    // ## Clear all existing dialog body content.
    _clearBody()
    {
        if (this._body !== null)
        {
            this._body.replaceChildren();
        }
    }


    // ## Bind a click handler when the target element exists.
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
