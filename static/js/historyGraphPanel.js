"use strict";

import
{
    DataGraph
}
from "./dataGraph.js";


export const historyViewportMap =
{
    "1 HR":
    {
        xMin: -60,
        minutes: 60,
        xGridInterval: 5,
        xUnits: "Minutes"
    },

    "5 HR":
    {
        xMin: -5,
        minutes: 300,
        xGridInterval: 0.5,
        xUnits: "Hours"
    },

    "12 HR":
    {
        xMin: -12,
        minutes: 720,
        xGridInterval: 1,
        xUnits: "Hours"
    },

    "1 D":
    {
        xMin: -24,
        minutes: 1440,
        xGridInterval: 2,
        xUnits: "Hours"
    },

    "5 D":
    {
        xMin: -5,
        minutes: 1440 * 5,
        xGridInterval: 0.5,
        xUnits: "Days"
    },

    "10 D":
    {
        xMin: -10,
        minutes: 1440 * 10,
        xGridInterval: 1,
        xUnits: "Days"
    },

    "30 D":
    {
        xMin: -30,
        minutes: 1440 * 30,
        xGridInterval: 2.5,
        xUnits: "Days"
    }
};


function createElement(strTagName, strClassName)
{
    const element =
        document.createElement(
            strTagName
        );

    if (strClassName)
    {
        element.className =
            strClassName;
    }

    return element;
}


function idFromKey(strKey)
{
    return (
        "hc" +
        strKey.replace(
            /\s/g,
            ""
        )
    );
}


export class HistoryGraphPanel
{
    constructor(
        containerElement,
        options
    )
    {
        this._containerElement =
            containerElement;

        this._graphData =
            options.graphData || [];

        this._yMax =
            options.yMax || 100;

        this._yLabel =
            options.yLabel || "Value";

        this._stroke =
            options.stroke || "blue";

        this._strokeWidth =
            options.strokeWidth || 1;

        this._viewportMap =
            options.viewportMap || historyViewportMap;

        this._currentViewportKey =
            options.initialViewportKey || "1 HR";

        this._svgId =
            options.svgId || "history-graph";

        this._averageElement =
            null;

        this._svgElement =
            null;

        this._buildDom();

        this.draw();
    }


    setData(graphData)
    {
        this._graphData =
            graphData || [];

        this.draw();
    }


    draw()
    {
        const viewPort =
            this._viewportMap[
                this._currentViewportKey
            ];

        const yAverage =
            DataGraph.drawHistoryGraph(
                this._graphData,
                "#" + this._svgId,
                viewPort,
                this._yMax,
                this._yLabel,
                {
                    stroke: this._stroke,
                    strokeWidth: this._strokeWidth
                }
            );

        this._averageElement.textContent =
            "μ = " +
            Math.round(
                yAverage
            );
    }


    _buildDom()
    {
        this._containerElement.replaceChildren();

        const panelElement =
            createElement(
                "div",
                "historyGraphPanel"
            );

        const controlsElement =
            createElement(
                "div",
                "historyGraphControls"
            );

        const titleElement =
            createElement(
                "div",
                "historyGraphTitle"
            );

        titleElement.textContent =
            this._yLabel;

        this._averageElement =
            createElement(
                "div",
                "historyGraphAverage"
            );

        this._averageElement.textContent =
            "μ = ";

        const buttonBarElement =
            createElement(
                "div",
                "historyGraphButtonBar"
            );

        controlsElement.appendChild(
            titleElement
        );

        controlsElement.appendChild(
            this._averageElement
        );

        controlsElement.appendChild(
            buttonBarElement
        );

        for (const strKey of Object.keys(this._viewportMap))
        {
            const controlElement =
                createElement(
                    "div",
                    "historyGraphControl"
                );

            controlElement.id =
                idFromKey(
                    strKey
                );

            controlElement.textContent =
                strKey;

            if (strKey === this._currentViewportKey)
            {
                controlElement.classList.add(
                    "selected"
                );
            }

            controlElement.addEventListener(
                "click",
                () =>
                {
                    this._selectViewport(
                        strKey
                    );
                }
            );

            buttonBarElement.appendChild(
                controlElement
            );
        }

        this._svgElement =
            document.createElementNS(
                "http://www.w3.org/2000/svg",
                "svg"
            );

        this._svgElement.id =
            this._svgId;

        this._svgElement.classList.add(
            "historyGraphSvg"
        );

        panelElement.appendChild(
            controlsElement
        );

        panelElement.appendChild(
            this._svgElement
        );

        this._containerElement.appendChild(
            panelElement
        );
    }


    _selectViewport(strKey)
    {
        this._currentViewportKey =
            strKey;

        const controlElements =
            this._containerElement.querySelectorAll(
                ".historyGraphControl"
            );

        for (const controlElement of controlElements)
        {
            controlElement.classList.remove(
                "selected"
            );
        }

        const selectedElement =
            this._containerElement.querySelector(
                "#" + idFromKey(strKey)
            );

        selectedElement.classList.add(
            "selected"
        );

        this.draw();
    }
}