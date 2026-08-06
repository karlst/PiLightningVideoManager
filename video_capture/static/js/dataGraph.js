"use strict";

import
{
    WorldCoordinates,
    createSvgGroup,
    clearSvgElement,
    appendSvgPath
}
from "./worldCoordinates.js";


function getSvgSize(svgElement)
{
    const width =
        svgElement.clientWidth ||
        svgElement.viewBox.baseVal.width ||
        Number(svgElement.getAttribute("width")) ||
        600;

    const height =
        svgElement.clientHeight ||
        svgElement.viewBox.baseVal.height ||
        Number(svgElement.getAttribute("height")) ||
        240;

    return {
        width,
        height
    };
}


function clipYValue(yValue, yMax)
{
    let yLimited =
        yValue;

    if (yLimited < 0)
    {
        yLimited =
            0;
    }

    if (yLimited >= yMax)
    {
        yLimited =
            yMax;
    }

    return yLimited;
}


function calcDt(viewPort)
{
    const minPerInterval =
        5;

    let dt =
        1;

    switch (viewPort.xUnits)
    {
        case "Minutes":
            dt =
                minPerInterval;
            break;

        case "Hours":
            dt =
                minPerInterval *
                (1 / 60);
            break;

        case "Days":
            dt =
                minPerInterval *
                (1 / (60 * 24));
            break;

        default:
            break;
    }

    return dt;
}


function formatXValue(viewPort, xValue)
{
    let retVal;
    let date;

    switch (viewPort.xUnits)
    {
        case "Days":
            date =
                new Date();

            date.setUTCDate(
                date.getUTCDate() + xValue
            );

            retVal =
                date.toLocaleDateString(
                    undefined,
                    {
                        day: "numeric",
                        month: "short"
                    }
                );
            break;

        case "Hours":
            date =
                new Date();

            date.setUTCHours(
                date.getUTCHours() + xValue
            );

            retVal =
                date.toLocaleTimeString(
                    undefined,
                    {
                        timeZone: "UTC",
                        hour12: false,
                        hour: "2-digit",
                        minute: "2-digit"
                    }
                );
            break;

        case "Minutes":
            date =
                new Date();

            date.setUTCMinutes(
                date.getUTCMinutes() + xValue
            );

            retVal =
                date.toLocaleTimeString(
                    undefined,
                    {
                        timeZone: "UTC",
                        hour12: false,
                        hour: "2-digit",
                        minute: "2-digit"
                    }
                );
            break;

        default:
            retVal =
                xValue;
            break;
    }

    return retVal;
}


export class DataGraph
{
    static drawHistoryGraph(
        graphData,
        containerId,
        viewPort,
        yMax,
        yLabel,
        graphAttrs
    )
    {
        const minPerInterval =
            5;

        const mapXUnitsToName =
        {
            Days: "Date",
            Hours: "UTC Time",
            Minutes: "UTC Time"
        };

        const svgElement =
            document.querySelector(
                containerId
            );

        if (!svgElement)
        {
            throw new Error(
                "SVG container not found: " + containerId
            );
        }

        const svgSize =
            getSvgSize(
                svgElement
            );

        svgElement.setAttribute(
            "viewBox",
            (
                "0 0 " +
                svgSize.width +
                " " +
                svgSize.height
            )
        );

        clearSvgElement(
            svgElement
        );

        const csAttrs =
        {
            leftPadding: 50,
            bottomPadding: 20,
            xMin: viewPort.xMin,
            xMax: 0.5,
            yMin: 0,
            yMax: yMax,
            xOrigin: viewPort.xMin,
            dxGrid: viewPort.xGridInterval,
            xRound: 0.5,
            yRound: 1.0,
            grid: true,

            axes:
            {
                x: true,
                y: true
            },

            axisLabels:
            {
                x: mapXUnitsToName[viewPort.xUnits],
                y: yLabel
            },

            labelFontSize: 9,
            scaleFontSize: 9,
            arrowEnd: "none",
            width: svgSize.width,
            height: svgSize.height,
            precision: 0.0001,

            fcnCallback:
            {
                displayXValue:
                    (xValue) =>
                        formatXValue(
                            viewPort,
                            xValue
                        ),

                displayYValue: null
            }
        };

        const axisGroup =
            createSvgGroup(
                svgElement
            );

        const graphGroup =
            createSvgGroup(
                svgElement
            );

        const wc =
            new WorldCoordinates(
                axisGroup,
                csAttrs
            );

        const dt =
            calcDt(
                viewPort
            );

        const intervalCount =
            viewPort.minutes /
            minPerInterval;

        let tVal =
            viewPort.xMin +
            dt;

        let graphDataIndex =
            graphData.length -
            intervalCount;

        let xpix =
            wc.xLogToPix(
                tVal
            );

        const xpixFirst =
            xpix;

        let firstRawYValue =
            0;

        if (graphDataIndex >= 0)
        {
            firstRawYValue =
                graphData[graphDataIndex];
        }

        let ySum =
            0;

        let xCount =
            0;

        let ypix =
            wc.yLogToPix(
                clipYValue(
                    firstRawYValue,
                    yMax
                )
            );

        let linePath =
            (
                "M " +
                xpix +
                " " +
                ypix
            );

        for (
            ;
            graphDataIndex < graphData.length;
            graphDataIndex++
        )
        {
            let rawYValue =
                0;

            if (graphDataIndex >= 0)
            {
                rawYValue =
                    graphData[graphDataIndex];
            }

            ySum +=
                rawYValue;

            xCount++;

            tVal +=
                dt;

            xpix =
                wc.xLogToPix(
                    tVal
                );

            ypix =
                wc.yLogToPix(
                    clipYValue(
                        rawYValue,
                        yMax
                    )
                );

            linePath +=
                (
                    " L " +
                    xpix +
                    " " +
                    ypix
                );
        }

        const stroke =
            graphAttrs?.stroke || "#2f80ed";

        const strokeWidth =
            graphAttrs?.strokeWidth || 2;

        appendSvgPath(
            graphGroup,
            linePath,
            {
                stroke,
                strokeWidth,
                fill: "none"
            }
        );

        const yAverage =
            xCount > 0
                ? ySum / xCount
                : 0;

        const ypixAverage =
            wc.yLogToPix(
                yAverage
            );

        const yAveragePath =
            (
                "M " +
                xpixFirst +
                " " +
                ypixAverage +
                " L " +
                xpix +
                " " +
                ypixAverage
            );

        appendSvgPath(
            graphGroup,
            yAveragePath,
            {
                stroke,
                strokeWidth,
                "stroke-dasharray": "5 5",
                fill: "none"
            }
        );

        return yAverage;
    }
}