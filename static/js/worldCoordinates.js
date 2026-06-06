"use strict";

const SVG_NS =
    "http://www.w3.org/2000/svg";


function svgCreate(strTagName)
{
    return document.createElementNS(
        SVG_NS,
        strTagName
    );
}


function svgSetAttrs(element, attrs)
{
    if (!attrs)
    {
        return element;
    }

    for (const [strName, value] of Object.entries(attrs))
    {
        const strSvgName =
            strName === "strokeWidth"
                ? "stroke-width"
                : strName;

        element.setAttribute(
            strSvgName,
            value
        );
    }

    return element;
}


function svgGroup(parentElement)
{
    const groupElement =
        svgCreate(
            "g"
        );

    parentElement.appendChild(
        groupElement
    );

    return groupElement;
}


function svgClear(element)
{
    element.replaceChildren();
}


function svgPath(parentElement, strPath, attrs)
{
    const pathElement =
        svgCreate(
            "path"
        );

    pathElement.setAttribute(
        "d",
        strPath
    );

    svgSetAttrs(
        pathElement,
        attrs
    );

    parentElement.appendChild(
        pathElement
    );

    return pathElement;
}


function svgText(parentElement, xPix, yPix, strText, attrs)
{
    const textElement =
        svgCreate(
            "text"
        );

    textElement.setAttribute(
        "x",
        xPix
    );

    textElement.setAttribute(
        "y",
        yPix
    );

    textElement.textContent =
        strText;

    svgSetAttrs(
        textElement,
        attrs
    );

    parentElement.appendChild(
        textElement
    );

    return textElement;
}


function mergeAttrs(defaultAttrs, userAttrs)
{
    return {
        ...defaultAttrs,
        ...userAttrs,

        axes:
        {
            ...defaultAttrs.axes,
            ...(userAttrs.axes || {})
        },

        axisLabels:
        {
            ...defaultAttrs.axisLabels,
            ...(userAttrs.axisLabels || {})
        },

        tickAttrs:
        {
            ...defaultAttrs.tickAttrs,
            ...(userAttrs.tickAttrs || {})
        },

        fcnCallback:
        {
            ...defaultAttrs.fcnCallback,
            ...(userAttrs.fcnCallback || {})
        }
    };
}


export class WorldCoordinates
{
    constructor(wcgElement, wcAttrs)
    {
        const defaultAttrs =
        {
            leftPadding: 0,
            bottomPadding: 0,
            xMin: -10,
            xMax: 10,
            yMin: -10,
            yMax: 10,
            xOrigin: "auto",
            yOrigin: "auto",
            grid: false,
            labelFontSize: 12,
            scaleFontSize: 12,

            axes:
            {
                x: true,
                y: false
            },

            axisLabels:
            {
                x: "x",
                y: "y"
            },

            axisStroke: "#333",
            axisStrokeWidth: 1,
            gridStroke: "#ccc",
            gridStrokeWidth: 1,
            showCommas: false,
            labelStroke: "#333",
            tickLength: 6,

            tickAttrs:
            {
                stroke: "#333",
                strokeWidth: "1",
                fill: "none"
            },

            dpixBaseline: 4,
            precision: 0.0001,
            arrowEnd: "classic-wide-long",

            fcnCallback:
            {
                displayXValue: null,
                displayYValue: null
            }
        };

        this._wcAttrs =
            mergeAttrs(
                defaultAttrs,
                wcAttrs || {}
            );

        this._cpixAxisTail =
            20;

        this._dxOriginLabel =
            10;

        this._gridGroup =
            svgGroup(
                wcgElement
            );

        this._axes =
        {
            xGroup:
                svgGroup(
                    wcgElement
                ),

            yGroup:
                svgGroup(
                    wcgElement
                )
        };

        this._csWidth =
            0;

        this._csHeight =
            0;

        this.showElements();
    }


    xLogToPix(x)
    {
        const wcAttrs =
            this._wcAttrs;

        return (
            wcAttrs.leftPadding +
            this._csWidth /
                (wcAttrs.xMax - wcAttrs.xMin) *
                (x - wcAttrs.xMin)
        );
    }


    yLogToPix(y)
    {
        const wcAttrs =
            this._wcAttrs;

        return (
            this._csHeight /
            (wcAttrs.yMax - wcAttrs.yMin) *
            (wcAttrs.yMax - y)
        );
    }


    xPixToLog(xpix)
    {
        const wcAttrs =
            this._wcAttrs;

        return (
            wcAttrs.xMin +
            (wcAttrs.xMax - wcAttrs.xMin) *
            (xpix - wcAttrs.leftPadding) /
            this._csWidth
        );
    }


    yPixToLog(ypix)
    {
        const wcAttrs =
            this._wcAttrs;

        return -(
            (
                (wcAttrs.yMax - wcAttrs.yMin) *
                ypix /
                this._csHeight
            ) -
            wcAttrs.yMax
        );
    }


    dxLogToPix(dx)
    {
        const wcAttrs =
            this._wcAttrs;

        return (
            this._csWidth /
            (wcAttrs.xMax - wcAttrs.xMin) *
            dx
        );
    }


    dyLogToPix(dy)
    {
        const wcAttrs =
            this._wcAttrs;

        return (
            this._csHeight /
            (wcAttrs.yMax - wcAttrs.yMin) *
            dy
        );
    }


    dxPixToLog(dx)
    {
        const wcAttrs =
            this._wcAttrs;

        return (
            (wcAttrs.xMax - wcAttrs.xMin) *
            dx /
            this._csWidth
        );
    }


    isPointInWindow(pt)
    {
        const wcAttrs =
            this._wcAttrs;

        return (
            pt.x !== null &&
            pt.y !== null &&
            wcAttrs.xMin <= pt.x &&
            pt.x <= wcAttrs.xMax &&
            wcAttrs.yMin <= pt.y &&
            pt.y <= wcAttrs.yMax
        );
    }


    drawGrid()
    {
        const wcAttrs =
            this._wcAttrs;

        const gridAttrs =
        {
            stroke: wcAttrs.gridStroke,
            strokeWidth: wcAttrs.gridStrokeWidth
        };

        svgClear(
            this._gridGroup
        );

        for (
            let xGridLine =
                wcAttrs.dxGrid *
                Math.round(
                    wcAttrs.xMin / wcAttrs.dxGrid
                );
            xGridLine <= wcAttrs.xMax;
            xGridLine += wcAttrs.dxGrid
        )
        {
            svgPath(
                this._gridGroup,
                (
                    "M " +
                    this.xLogToPix(xGridLine) +
                    " 0 l 0 " +
                    this._csHeight
                ),
                gridAttrs
            );
        }

        for (
            let yGridLine =
                wcAttrs.dyGrid *
                Math.round(
                    wcAttrs.yMin / wcAttrs.dyGrid
                );
            yGridLine <= wcAttrs.yMax;
            yGridLine += wcAttrs.dyGrid
        )
        {
            svgPath(
                this._gridGroup,
                (
                    "M " +
                    wcAttrs.leftPadding +
                    " " +
                    this.yLogToPix(yGridLine) +
                    " l " +
                    this._csWidth +
                    " 0"
                ),
                gridAttrs
            );
        }
    }


    drawAxes()
    {
        const wcAttrs =
            this._wcAttrs;

        const xyRoundVal =
            Math.round(
                1 / wcAttrs.precision
            );

        const varFontAttrs =
        {
            "font-style": "italic",
            "font-size": wcAttrs.labelFontSize + "px",
            "font-family": "Georgia, Serif",
            fill: wcAttrs.labelStroke
        };

        const axesAttrs =
        {
            stroke: wcAttrs.axisStroke,
            strokeWidth: wcAttrs.axisStrokeWidth
        };

        const xScaleAttrs =
        {
            "font-family": "Arial",
            "font-size": wcAttrs.labelFontSize + "px",
            fill: wcAttrs.labelStroke,
            "text-anchor": "middle"
        };

        const yScaleAttrs =
        {
            "font-family": "Arial",
            "font-size": wcAttrs.labelFontSize + "px",
            fill: wcAttrs.labelStroke,
            "text-anchor": "start"
        };

        svgClear(
            this._axes.xGroup
        );

        svgClear(
            this._axes.yGroup
        );

        const cxEnDash =
            parseInt(
                wcAttrs.scaleFontSize / 2,
                10
            );

        const yOriginValue =
            wcAttrs.yOrigin === "auto"
                ? (
                    wcAttrs.yMin > 0
                        ? wcAttrs.yMin
                        : 0
                )
                : wcAttrs.yOrigin;

        const xOriginValue =
            wcAttrs.xOrigin === "auto"
                ? (
                    wcAttrs.xMin > 0
                        ? wcAttrs.xMin
                        : 0
                )
                : wcAttrs.xOrigin;

        const xAxisExtra =
            wcAttrs.xMin >= 0
                ? this._cpixAxisTail
                : 0;

        const yAxisExtra =
            wcAttrs.yMin >= 0
                ? this._cpixAxisTail
                : 0;

        const xScale =
            wcAttrs.xScale === undefined
                ? this.xLogToPix(xOriginValue) -
                    wcAttrs.scaleFontSize * 1.25
                : wcAttrs.xScale;

        const yScale =
            wcAttrs.yScale === undefined
                ? this.yLogToPix(yOriginValue) +
                    wcAttrs.scaleFontSize * 1.25
                : wcAttrs.yScale;

        const xpixOrigin =
            this.xLogToPix(
                xOriginValue
            );

        const ypixOrigin =
            this.yLogToPix(
                yOriginValue
            );

        const dpixTick =
            parseInt(
                wcAttrs.tickLength / 2,
                10
            );

        if (wcAttrs.axes.x)
        {
            const xAxisPath =
                (
                    "M " +
                    wcAttrs.width +
                    " " +
                    ypixOrigin +
                    " l " +
                    (-this._csWidth - xAxisExtra) +
                    " 0 z"
                );

            svgPath(
                this._axes.xGroup,
                xAxisPath,
                axesAttrs
            );

            svgText(
                this._axes.xGroup,
                (
                    wcAttrs.width -
                    wcAttrs.axisLabels.x.length *
                    wcAttrs.labelFontSize
                ),
                (
                    this.yLogToPix(yOriginValue) -
                    wcAttrs.labelFontSize
                ),
                wcAttrs.axisLabels.x,
                varFontAttrs
            );

            const xStart =
                wcAttrs.dxGrid *
                2 *
                Math.round(
                    wcAttrs.xMin /
                    (wcAttrs.dxGrid * 2)
                );

            let xTickPath =
                "";

            for (
                let xScaleLabel = xStart;
                xScaleLabel <= wcAttrs.xMax;
                xScaleLabel += 2 * wcAttrs.dxGrid
            )
            {
                const xpix =
                    this.xLogToPix(
                        xScaleLabel
                    );

                if (
                    xpix <
                        wcAttrs.leftPadding +
                        wcAttrs.scaleFontSize ||
                    xpix >=
                        wcAttrs.leftPadding +
                        this._csWidth -
                        wcAttrs.scaleFontSize
                )
                {
                    continue;
                }

                let dxAdjust =
                    0;

                let signChar =
                    "";

                let xDisplayValue;

                if (wcAttrs.fcnCallback.displayXValue !== null)
                {
                    xDisplayValue =
                        wcAttrs.fcnCallback.displayXValue(
                            xScaleLabel
                        );
                }
                else
                {
                    xDisplayValue =
                        Math.round(
                            xScaleLabel *
                            xyRoundVal
                        ) / xyRoundVal;

                    if (xScaleLabel < 0)
                    {
                        dxAdjust =
                            cxEnDash / 2;

                        signChar =
                            String.fromCharCode(
                                8211
                            );

                        xDisplayValue =
                            -xScaleLabel;
                    }

                    if (
                        wcAttrs.showCommas &&
                        xDisplayValue >= 1000
                    )
                    {
                        xDisplayValue =
                            String(
                                xDisplayValue
                            );

                        xDisplayValue =
                            (
                                xDisplayValue.substring(
                                    0,
                                    xDisplayValue.length - 3
                                ) +
                                "," +
                                xDisplayValue.substring(
                                    xDisplayValue.length - 3,
                                    xDisplayValue.length
                                )
                            );
                    }
                }

                xTickPath +=
                    (
                        "M " +
                        xpix +
                        " " +
                        (ypixOrigin - dpixTick) +
                        " l 0 " +
                        wcAttrs.tickLength
                    );

                if (xScaleLabel !== 0)
                {
                    svgText(
                        this._axes.xGroup,
                        xpix - dxAdjust,
                        yScale,
                        signChar + xDisplayValue,
                        xScaleAttrs
                    );
                }
                else if (!wcAttrs.axes.y)
                {
                    svgText(
                        this._axes.xGroup,
                        xpix - dxAdjust,
                        yScale,
                        signChar + xDisplayValue,
                        xScaleAttrs
                    );
                }
                else
                {
                    svgText(
                        this._axes.xGroup,
                        xpix - dxAdjust - this._dxOriginLabel,
                        yScale,
                        signChar + xDisplayValue,
                        xScaleAttrs
                    );
                }
            }

            svgPath(
                this._axes.xGroup,
                xTickPath,
                wcAttrs.tickAttrs
            );
        }

        if (wcAttrs.axes.y)
        {
            const yAxisPath =
                (
                    "M " +
                    xpixOrigin +
                    " 0 l 0 " +
                    (this._csHeight + yAxisExtra) +
                    " z"
                );

            svgPath(
                this._axes.yGroup,
                yAxisPath,
                axesAttrs
            );

            svgText(
                this._axes.yGroup,
                this.xLogToPix(xOriginValue) + wcAttrs.labelFontSize,
                wcAttrs.labelFontSize,
                wcAttrs.axisLabels.y,
                varFontAttrs
            );

            let yTickPath =
                "";

            const yStart =
                wcAttrs.dyGrid *
                2 *
                Math.round(
                    wcAttrs.yMin /
                    (wcAttrs.dyGrid * 2)
                );

            for (
                let yScaleLabel = yStart;
                yScaleLabel <= wcAttrs.yMax;
                yScaleLabel += 2 * wcAttrs.dyGrid
            )
            {
                const yScaleLabelRound =
                    Math.round(
                        yScaleLabel * 1000
                    ) / 1000;

                const ypix =
                    this.yLogToPix(
                        yScaleLabelRound
                    );

                if (
                    ypix < wcAttrs.scaleFontSize ||
                    ypix >= this._csHeight - wcAttrs.scaleFontSize
                )
                {
                    continue;
                }

                let yDisplayValue =
                    String(
                        yScaleLabel
                    );

                if (yScaleLabel < 0)
                {
                    yDisplayValue =
                        String.fromCharCode(
                            8211
                        ) +
                        (-yScaleLabel);
                }

                if (
                    wcAttrs.showCommas &&
                    Number(yDisplayValue) >= 1000
                )
                {
                    yDisplayValue =
                        (
                            yDisplayValue.substring(
                                0,
                                yDisplayValue.length - 3
                            ) +
                            "," +
                            yDisplayValue.substring(
                                yDisplayValue.length - 3,
                                yDisplayValue.length
                            )
                        );
                }

                const dxAdjust =
                    -cxEnDash *
                    (yDisplayValue.length - 1);

                yTickPath +=
                    (
                        " M " +
                        (xpixOrigin - dpixTick) +
                        " " +
                        ypix +
                        " l " +
                        wcAttrs.tickLength +
                        " 0 "
                    );

                if (yScaleLabel !== 0)
                {
                    svgText(
                        this._axes.yGroup,
                        xScale + dxAdjust,
                        ypix + wcAttrs.dpixBaseline,
                        yDisplayValue,
                        yScaleAttrs
                    );
                }
                else if (!wcAttrs.axes.x)
                {
                    svgText(
                        this._axes.yGroup,
                        xScale + dxAdjust,
                        ypix + wcAttrs.dpixBaseline,
                        yDisplayValue,
                        yScaleAttrs
                    );
                }
            }

            svgPath(
                this._axes.yGroup,
                yTickPath,
                wcAttrs.tickAttrs
            );
        }
    }


    showElements()
    {
        const wcAttrs =
            this._wcAttrs;

        function calcGridInterval(gridMin, gridMax)
        {
            let gridInterval =
                1;

            const range =
                gridMax - gridMin;

            if (gridMax <= gridMin)
            {
                throw new Error(
                    (
                        "min: " +
                        gridMin +
                        " max: " +
                        gridMax +
                        " Minimum must be less than maximum."
                    )
                );
            }

            if (range > 80)
            {
                gridInterval =
                    10 *
                    calcGridInterval(
                        gridMin / 10,
                        gridMax / 10
                    );
            }
            else if (range > 32)
            {
                gridInterval =
                    5;
            }
            else if (range > 16)
            {
                gridInterval =
                    2;
            }
            else if (range > 8)
            {
                gridInterval =
                    1;
            }
            else if (range <= 8)
            {
                gridInterval =
                    0.1 *
                    calcGridInterval(
                        10 * gridMin,
                        10 * gridMax
                    );
            }

            return gridInterval;
        }

        if (wcAttrs.dxGrid === undefined)
        {
            wcAttrs.dxGrid =
                calcGridInterval(
                    wcAttrs.xMin,
                    wcAttrs.xMax
                );
        }

        if (wcAttrs.dyGrid === undefined)
        {
            wcAttrs.dyGrid =
                calcGridInterval(
                    wcAttrs.yMin,
                    wcAttrs.yMax
                );
        }

        this._csWidth =
            wcAttrs.width -
            wcAttrs.leftPadding;

        this._csHeight =
            wcAttrs.height -
            wcAttrs.bottomPadding;

        if (wcAttrs.grid)
        {
            this.drawGrid();
        }

        this.drawAxes();
    }


    attr(newAttrs)
    {
        if (newAttrs === undefined)
        {
            return this._wcAttrs;
        }

        this._wcAttrs =
            mergeAttrs(
                this._wcAttrs,
                newAttrs
            );

        this.showElements();

        return this;
    }
}


export function createSvgGroup(parentElement)
{
    return svgGroup(
        parentElement
    );
}


export function clearSvgElement(element)
{
    svgClear(
        element
    );
}


export function appendSvgPath(parentElement, strPath, attrs)
{
    return svgPath(
        parentElement,
        strPath,
        attrs
    );
}