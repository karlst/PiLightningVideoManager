"use strict";

import "/web_viewer/static/js/captureViewer.js?v=1";

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
from "./previewPanel.js?v=40";

import
{
    BufferPanel
}
from "./bufferPanel.js?v=32";

import
{
    MetricsGraphPanel
}
from "./metricsGraphPanel.js?v=36";

import
{
    DialogPanel
}
from "./dialogPanel.js?v=32";

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