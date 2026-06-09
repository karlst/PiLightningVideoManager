"use strict";

import
{
    StatusPanel
}
from "./statusPanel.js?v=32";

import
{
    CameraPanel
}
from "./cameraPanel.js?v=33";

import
{
    EventLogPanel
}
from "./eventLogPanel.js?v=32";

import
{
    PreviewPanel
}
from "./previewPanel.js?v=32";

import
{
    BufferPanel
}
from "./bufferPanel.js?v=32";

import
{
    MetricsGraphPanel
}
from "./metricsGraphPanel.js?v=32";


function initializePage()
{
    const statusPanel =
        new StatusPanel();

    const eventLogPanel =
        new EventLogPanel(
            statusPanel
        );

    const previewPanel =
        new PreviewPanel(
            statusPanel,
            eventLogPanel
        );

    const bufferPanel =
        new BufferPanel(
            statusPanel,
            eventLogPanel
        );

    const metricsGraphPanel =
        new MetricsGraphPanel();

    const cameraPanel =
        new CameraPanel();

    statusPanel.setSystemSampleHandler(
        (result) => metricsGraphPanel.addSystemSample(
            result
        )
    );

    statusPanel.setSystemStatusHandler(
        (result) => cameraPanel.updateFromSystemStatus(
            result
        )
    );

    statusPanel.setStatus(
        "Ready"
    );

    eventLogPanel.initialize();
    previewPanel.initialize();
    bufferPanel.initialize();
    metricsGraphPanel.initialize();

    statusPanel.updateSystemStatus();

    setInterval(
        () => eventLogPanel.refresh(),
        1000
    );

    setInterval(
        () => statusPanel.updateSystemStatus(),
        1000
    );

    setInterval(
        () => metricsGraphPanel.updateMetricHistory(),
        1000
    );
}


document.addEventListener(
    "DOMContentLoaded",
    initializePage
);