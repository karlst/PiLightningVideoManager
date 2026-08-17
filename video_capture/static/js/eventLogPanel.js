"use strict";

import
{
    postJson,
    getJson
}
from "./httpClient.js";


export class EventLogPanel
{
    // ## Initialize event-log UI state.
    constructor(statusPanel)
    {
        this._statusPanel =
            statusPanel;

        this._entries =
            [];
    }


    // ## Bind recent/full event log controls and load current events.
    initialize()
    {
        this._bindClick(
            "show-event-log-button",
            () => this.showFullEventLog()
        );

        this._bindClick(
            "show-event-log-button-bottom",
            () => this.showFullEventLog()
        );

        this.refresh();
    }


    // ## Refresh recent event display from the server.
    async refresh()
    {
        try
        {
            const result =
                await getJson(
                    "/event_log"
                );

            this._entries =
                result.entries ?? [];

            this._renderRecentEvents();
        }
        catch (error)
        {
            console.error(
                error
            );
        }
    }


    // ## Open the full event log dialog with clear-log controls.
    showFullEventLog()
    {
        const dialog =
            document.getElementById(
                "app-dialog"
            );

        const title =
            document.getElementById(
                "app-dialog-title"
            );

        const body =
            document.getElementById(
                "app-dialog-body"
            );

        if (
            dialog !== null &&
            title !== null &&
            body !== null
        )
        {
            title.textContent =
                "Event Log";

            body.replaceChildren();

            this._appendFullLogToolbar(
                body
            );

            this._appendFullLogRows(
                body
            );

            dialog.showModal();
        }
    }


    // ## Clear the event log and refresh recent/full displays.
    async clear()
    {
        try
        {
            const result =
                await postJson(
                    "/event_log_clear"
                );

            this._statusPanel.setStatus(
                result.message
            );

            await this.refresh();

            this.showFullEventLog();
        }
        catch (error)
        {
            this._statusPanel.setStatus(
                "Clear Event Log Failed"
            );

            console.error(
                error
            );
        }
    }


    // ## Render only the most recent summaries in the dashboard strip.
    _renderRecentEvents()
    {
        const eventLog =
            document.getElementById(
                "event-log"
            );

        if (eventLog !== null)
        {
            eventLog.replaceChildren();

            const recentEntries =
                this._entries.slice(
                    -5
                ).reverse();

            recentEntries.forEach(
                (entry) =>
                {
                    const row =
                        document.createElement(
                            "div"
                        );

                    row.className =
                        "eventLogRow";

                    row.textContent =
                        `${this._formatTime(entry.timestamp_utc)}  ` +
                        `${entry.summary ?? entry.message ?? ""}`;

                    eventLog.appendChild(
                        row
                    );
                }
            );

        }
    }


    // ## Add toolbar controls to the full event log dialog.
    _appendFullLogToolbar(body)
    {
        const toolbar =
            document.createElement(
                "div"
            );

        toolbar.className =
            "fullEventLogToolbar";

        const clearButton =
            document.createElement(
                "button"
            );

        clearButton.className =
            "ccButton ccButtonSecondary";

        clearButton.type =
            "button";

        clearButton.textContent =
            "Clear Event Log";

        clearButton.addEventListener(
            "click",
            () => this.clear()
        );

        toolbar.appendChild(
            clearButton
        );

        body.appendChild(
            toolbar
        );
    }


    // ## Add full event entries to the full event log dialog.
    _appendFullLogRows(body)
    {
        const log =
            document.createElement(
                "div"
            );

        log.className =
            "fullEventLog";

        [...this._entries].reverse().forEach(
            (entry) =>
            {
                const row =
                    document.createElement(
                        "div"
                    );

                row.className =
                    "fullEventLogRow";

                row.appendChild(
                    this._createCell(
                        entry.timestamp_utc ?? "--"
                    )
                );

                row.appendChild(
                    this._createCell(
                        entry.severity ?? "info"
                    )
                );

                row.appendChild(
                    this._createCell(
                        entry.event_type ?? "general"
                    )
                );

                row.appendChild(
                    this._createCell(
                        entry.message ?? ""
                    )
                );

                log.appendChild(
                    row
                );
            }
        );

        body.appendChild(
            log
        );
    }


    // ## Create one text cell for the full log grid.
    _createCell(text)
    {
        const cell =
            document.createElement(
                "div"
            );

        cell.textContent =
            text;

        return cell;
    }


    // ## Format event timestamps for the compact recent-event strip.
    _formatTime(timestampText)
    {
        let text =
            "--:--";

        if (timestampText)
        {
            text =
                String(timestampText).substring(
                    11,
                    16
                );
        }

        return text;
    }


    // ## Bind a click handler if the element exists.
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
