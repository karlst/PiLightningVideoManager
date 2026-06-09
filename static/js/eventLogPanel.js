"use strict";

import
{
    postJson,
    getJson
}
from "./httpClient.js";


export class EventLogPanel
{
    constructor(statusPanel)
    {
        this._statusPanel =
            statusPanel;
    }


    initialize()
    {
        this._bindClick(
            "event-log-clear-button",
            () => this.clear()
        );

        this.refresh();
    }


    async refresh()
    {
        try
        {
            const result =
                await getJson(
                    "/event_log"
                );

            const eventLog =
                document.getElementById(
                    "event-log"
                );

            if (eventLog !== null)
            {
                eventLog.innerHTML =
                    "";

                result.entries.forEach(
                    (entry) =>
                    {
                        const row =
                            document.createElement(
                                "div"
                            );

                        row.className =
                            "eventLogRow";

                        row.textContent =
                            `[${entry.timestamp}] ${entry.level}: ${entry.message}`;

                        eventLog.appendChild(
                            row
                        );
                    }
                );

                eventLog.scrollTop =
                    eventLog.scrollHeight;
            }
        }
        catch (error)
        {
            console.error(
                error
            );
        }
    }


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

            this.refresh();
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
