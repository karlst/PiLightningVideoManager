"use strict";

import
{
    HistoryGraphPanel
}
from "./historyGraphPanel.js";


function assertTrue(strName, condition)
{
    if (!condition)
    {
        throw new Error(
            strName
        );
    }
}


function createTestHistoryData(iSampleCount = 10000)
{
    const graphData =
        [];

    for (let iSample = 0; iSample < iSampleCount; iSample++)
    {
        let value =
            50 +
            15 * Math.sin(iSample / 100) +
            5 * Math.sin(iSample / 11);

        if (iSample > 3000)
        {
            value +=
                25;
        }

        if (iSample > 7000)
        {
            value -=
                15;
        }

        graphData.push(
            value
        );
    }

    return graphData;
}


function getOrCreateContainer(containerId)
{
    let containerElement =
        null;

    if (containerId)
    {
        containerElement =
            document.getElementById(
                containerId
            );
    }

    if (!containerElement)
    {
        containerElement =
            document.createElement(
                "div"
            );

        containerElement.id =
            "unit-test-panel";

        containerElement.style.width =
            "800px";

        containerElement.style.height =
            "500px";

        containerElement.style.margin =
            "20px";

        containerElement.style.border =
            "1px solid #ccc";

        document.body.appendChild(
            containerElement
        );
    }

    return containerElement;
}


function testHistoryGraphPanel(containerId)
{
    const containerElement =
        getOrCreateContainer(
            containerId
        );

    const graphData =
        createTestHistoryData();

    const panel =
        new HistoryGraphPanel(
            containerElement,
            {
                graphData: graphData,
                yMax: 100,
                yLabel: "Brightness",
                initialViewportKey: "1 HR",
                stroke: "blue",
                strokeWidth: 1
            }
        );

    assertTrue(
        "HistoryGraphPanel should be created",
        panel !== null
    );

    assertTrue(
        "history graph svg should exist",
        containerElement.querySelector("svg.historyGraphSvg") !== null
    );

    assertTrue(
        "history graph controls should exist",
        containerElement.querySelectorAll(".historyGraphControl").length >= 7
    );

    assertTrue(
        "selected history graph control should exist",
        containerElement.querySelector(".historyGraphControl.selected") !== null
    );

    assertTrue(
        "history graph should create SVG paths",
        containerElement.querySelectorAll("path").length > 0
    );

    assertTrue(
        "history graph should create SVG text labels",
        containerElement.querySelectorAll("text").length > 0
    );

    console.log(
        "PASS testHistoryGraphPanel"
    );
}


export class UnitTests
{
    static createTestHistoryData(iSampleCount = 10000)
    {
        return createTestHistoryData(
            iSampleCount
        );
    }


    static testHistoryGraphPanel(containerId)
    {
        testHistoryGraphPanel(
            containerId
        );
    }


    static runAll(containerId)
    {
        testHistoryGraphPanel(
            containerId
        );

        console.log(
            "ALL UNIT TESTS PASSED"
        );
    }
}