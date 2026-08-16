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


    // ## Show the user-facing CandidateFinder sensitivity setting.
    async showTriggerSettings()
    {
        this._setTitle(
            "Trigger Settings"
        );

        this._clearBody();

        this._body.textContent =
            "Loading candidate settings...";

        this._dialog.showModal();

        try
        {
            const result =
                await getJson(
                    "/candidate_settings"
                );

            if (!result.success)
            {
                this._body.textContent =
                    "Unable to load candidate settings.";

                return;
            }

            this._clearBody();

            const container =
                document.createElement(
                    "div"
                );

            container.className =
                "triggerSensitivityPanel";

            const heading =
                document.createElement(
                    "div"
                );

            heading.className =
                "triggerSensitivityHeading";

            heading.textContent =
                "Sensitivity";

            container.appendChild(
                heading
            );

            const helpText =
                document.createElement(
                    "div"
                );

            helpText.className =
                "triggerSensitivityHelp";

            helpText.textContent =
                "Higher sensitivity retains more marginal events and may produce more false positives.";

            container.appendChild(
                helpText
            );

            const choices =
                document.createElement(
                    "div"
                );

            choices.className =
                "triggerSensitivityChoices";

            container.appendChild(
                choices
            );

            const radios =
                new Map();

            const addSensitivityChoice =
                (
                    value,
                    labelText
                ) =>
                {
                    const label =
                        document.createElement(
                            "label"
                        );

                    label.className =
                        "triggerSensitivityChoice";

                    const input =
                        document.createElement(
                            "input"
                        );

                    input.type =
                        "radio";

                    input.name =
                        "candidate-sensitivity";

                    input.value =
                        value;

                    const text =
                        document.createElement(
                            "span"
                        );

                    text.textContent =
                        labelText;

                    label.appendChild(
                        input
                    );

                    label.appendChild(
                        text
                    );

                    choices.appendChild(
                        label
                    );

                    radios.set(
                        value,
                        input
                    );
                };

            addSensitivityChoice(
                "high",
                "High"
            );

            addSensitivityChoice(
                "medium",
                "Medium"
            );

            addSensitivityChoice(
                "low",
                "Low"
            );

            const setSensitivity =
                (config) =>
                {
                    const sensitivity =
                        String(
                            config?.sensitivity || "medium"
                        ).toLowerCase();

                    const radio =
                        radios.get(
                            sensitivity
                        );

                    if (radio !== undefined)
                    {
                        radio.checked =
                            true;
                    }
                };

            setSensitivity(
                result.active
            );

            const systemSettings =
                await getJson(
                    "/system_settings"
                );

            const saveFalsePositiveLabel =
                document.createElement(
                    "label"
                );

            saveFalsePositiveLabel.className =
                "triggerSaveFalsePositives";

            const saveFalsePositiveInput =
                document.createElement(
                    "input"
                );

            saveFalsePositiveInput.type =
                "checkbox";

            saveFalsePositiveInput.checked =
                Boolean(
                    systemSettings.
                        save_filtered_false_positives
                );

            const saveFalsePositiveText =
                document.createElement(
                    "span"
                );

            saveFalsePositiveText.textContent =
                "Save filtered false positive candidates";

            saveFalsePositiveLabel.appendChild(
                saveFalsePositiveInput
            );

            saveFalsePositiveLabel.appendChild(
                saveFalsePositiveText
            );

            container.appendChild(
                saveFalsePositiveLabel
            );

            const buttonRow =
                document.createElement(
                    "div"
                );

            buttonRow.className =
                "triggerSensitivityButtons";

            const applyButton =
                document.createElement(
                    "button"
                );

            applyButton.type =
                "button";

            applyButton.className =
                "ccButton";

            applyButton.textContent =
                "Apply";

            const resetButton =
                document.createElement(
                    "button"
                );

            resetButton.type =
                "button";

            resetButton.className =
                "ccButton ccButtonSecondary";

            resetButton.textContent =
                "Reset Defaults";

            buttonRow.appendChild(
                applyButton
            );

            buttonRow.appendChild(
                resetButton
            );

            container.appendChild(
                buttonRow
            );

            const message =
                document.createElement(
                    "div"
                );

            message.className =
                "triggerSensitivityMessage";

            container.appendChild(
                message
            );

            this._body.appendChild(
                container
            );

            applyButton.addEventListener(
                "click",
                async () =>
                {
                    const selected =
                        choices.querySelector(
                            'input[name="candidate-sensitivity"]:checked'
                        );

                    if (selected === null)
                    {
                        message.textContent =
                            "Select a sensitivity level.";

                        return;
                    }

                    try
                    {
                        const response =
                            await fetch(
                                "/candidate_settings",
                                {
                                    method: "POST",

                                    headers:
                                    {
                                        "Content-Type":
                                            "application/json"
                                    },

                                    body:
                                        JSON.stringify(
                                            {
                                                sensitivity:
                                                    selected.value
                                            }
                                        )
                                }
                            );

                        const saveResult =
                            await response.json();

                        message.textContent =
                            saveResult.message;

                        if (saveResult.success)
                        {
                            setSensitivity(
                                saveResult.active
                            );

                            const systemResponse =
                                await fetch(
                                    "/system_settings",
                                    {
                                        method: "POST",

                                        headers:
                                        {
                                            "Content-Type":
                                                "application/json"
                                        },

                                        body:
                                            JSON.stringify(
                                                {
                                                    save_filtered_false_positives:
                                                        saveFalsePositiveInput.checked
                                                }
                                            )
                                    }
                                );

                            const systemResult =
                                await systemResponse.json();

                            if (!systemResult.success)
                            {
                                message.textContent =
                                    systemResult.message;
                            }
                        }
                    }
                    catch (error)
                    {
                        message.textContent =
                            "Candidate sensitivity update failed.";

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
                                    method:
                                        "POST"
                                }
                            );

                        const resetResult =
                            await response.json();

                        message.textContent =
                            resetResult.message;

                        if (resetResult.success)
                        {
                            setSensitivity(
                                resetResult.active
                            );

                            saveFalsePositiveInput.checked =
                                false;

                            const systemResponse =
                                await fetch(
                                    "/system_settings",
                                    {
                                        method: "POST",

                                        headers:
                                        {
                                            "Content-Type":
                                                "application/json"
                                        },

                                        body:
                                            JSON.stringify(
                                                {
                                                    save_filtered_false_positives:
                                                        false
                                                }
                                            )
                                    }
                                );

                            const systemResult =
                                await systemResponse.json();

                            if (!systemResult.success)
                            {
                                message.textContent =
                                    systemResult.message;
                            }
                        }
                    }
                    catch (error)
                    {
                        message.textContent =
                            "Candidate settings reset failed.";

                        console.error(
                            error
                        );
                    }
                }
            );
        }
        catch (error)
        {
            this._body.textContent =
                "Unable to load candidate settings.";

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
