"use strict";

import "/web_viewer/static/js/captureViewer.js?v=1";

import
{
    StatusPanel
}
from "./statusPanel.js?v=34";

import
{
    CameraPanel
}
from "./cameraPanel.js?v=33";

import
{
    EventLogPanel
}
from "./eventLogPanel.js?v=34";

import
{
    PreviewPanel
}
from "./previewPanel.js?v=42";

import
{
    BufferPanel
}
from "./bufferPanel.js?v=32";

import
{
    MetricsGraphPanel
}
from "./metricsGraphPanel.js?v=37";

import
{
    DialogPanel
}
from "./dialogPanel.js?v=33";

import
{
    TriggerManager
}
from "./triggerManager.js?v=34";


function initializePage()
{
    const statusPanel =
        new StatusPanel();

    const eventLogPanel =
        new EventLogPanel(
            statusPanel
        );

    const metricsGraphPanel =
        new MetricsGraphPanel();

    const previewPanel =
        new PreviewPanel(
            statusPanel,
            eventLogPanel,
            metricsGraphPanel
        );

    const dialogPanel =
        new DialogPanel(
            previewPanel
        );
    dialogPanel.initialize();

    const loadCaptureButton =
        document.getElementById(
            "load-capture-button"
        );

    if (loadCaptureButton !== null)
    {
        loadCaptureButton.addEventListener(
            "click",
            () => dialogPanel.showBrowseCaptures()
        );
    }

    const bufferPanel =
        new BufferPanel(
            statusPanel,
            eventLogPanel
        );

    const cameraPanel =
        new CameraPanel();

    const triggerManager =
        new TriggerManager();
        
            
    triggerManager.initialize();

    statusPanel.setSystemSampleHandler(
        (result) => metricsGraphPanel.addSystemSample(
            result
        )
    );

    statusPanel.setSystemStatusHandler(
        (result) =>
        {
            eventLogPanel.setRecentEntries(
                result.recent_events ?? []
            );

            metricsGraphPanel.updateTelemetry(
                result
            );

            previewPanel.updateConfiguration(
                result
            );
        }
    );

    statusPanel.setStatus(
        "Ready"
    );

    eventLogPanel.initialize();
    previewPanel.initialize();
    bufferPanel.initialize();
    metricsGraphPanel.initialize();

    // One completion-driven heartbeat replaces the former independent
    // event-log, system-status, and metric-history polling loops.
    async function pollSystemStatus()
    {
        await statusPanel.updateSystemStatus();

        window.setTimeout(
            pollSystemStatus,
            1000
        );
    }

    pollSystemStatus();
}


document.addEventListener(
    "DOMContentLoaded",
    initializePage
);
