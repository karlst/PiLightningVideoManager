"use strict";

import
{
    getJson
}
from "./httpClient.js";


export class MetricsGraphPanel
{
    constructor()
    {
        this._iGraphWindowHours = 1;
        this._aMetricHistory = [];
        this._mode = "live";
        this._aCaptureMetrics = [];
        this._captureName = "";
        this._captureCursorFrameIndex = null;
        this._piTriggerFrameIndex = null;
        this._replayTriggerFrameIndex = null;
    }

    initialize()
    {
        document.querySelectorAll(".graphButton").forEach(
            (button) =>
            {
                button.addEventListener(
                    "click",
                    () =>
                    {
                        this.setGraphWindow(
                            Number(button.dataset.window)
                        );
                    }
                );
            }
        );

        this.setGraphWindow(1);

        window.addEventListener(
            "resize",
            () => this.drawAllGraphs()
        );

        this.updateMetricHistory();
    }

    

    async updateMetricHistory()
    {
        try
        {
            const result = await getJson("/metrics_history");

            if (result.success)
            {
                this._aMetricHistory = result.metrics;

                if (this._mode === "live")
                {
                    this.drawAllGraphs();
                }
            }
        }
        catch (error)
        {
            console.error(error);
        }
    }

    // ## Replace long-term live graphs with frame-by-frame capture graphs.
    showCaptureMetrics(captureFile)
    {
        const analysis =
            captureFile?.analysis || {};

        this._mode =
            "capture";

        this._aCaptureMetrics =
            analysis.frame_records || [];

        this._captureName =
            captureFile?.capture_time_display ||
            captureFile?.display_name ||
            captureFile?.name ||
            "Capture";

        this._piTriggerFrameIndex =
            this._getInitialCaptureCursorFrameIndex(
                analysis
            );

        this._captureCursorFrameIndex =
            this._piTriggerFrameIndex;

        this._replayTriggerFrameIndex =
            null;

        this._setGraphButtonsVisible(
            false
        );

        this.drawAllGraphs();
    }

    // ## Return graph stack to long-term live metrics mode.
    showLiveMetrics()
    {
        this._mode =
            "live";

        this._aCaptureMetrics =
            [];

        this._captureName =
            "";

        this._captureCursorFrameIndex =
            null;

        this._piTriggerFrameIndex =
            null;

        this._replayTriggerFrameIndex =
            null;

        this._setGraphButtonsVisible(
            true
        );

        this.drawAllGraphs();
    }

    // ## Move the capture graph cursor to match the current playback frame.
    setCaptureCursorFrameIndex(frameIndex)
    {
        if (this._mode === "capture")
        {
            this._captureCursorFrameIndex =
                this._clampCaptureFrameIndex(
                    frameIndex
                );

            this.drawAllGraphs();
        }
    }

    // ## Set the CandidateFinder replay trigger marker on capture graphs.
    setCaptureReplayTriggerFrameIndex(frameIndex)
    {
        if (this._mode === "capture")
        {
            this._replayTriggerFrameIndex =
                this._clampCaptureFrameIndex(
                    frameIndex
                );

            this.drawAllGraphs();
        }
    }


    setGraphWindow(iHours)
    {
        this._iGraphWindowHours = iHours;

        document.querySelectorAll(".graphButton").forEach(
            (button) =>
            {
                button.classList.toggle(
                    "graphButtonActive",
                    Number(button.dataset.window) === iHours
                );
            }
        );

        this.drawAllGraphs();
    }

    drawAllGraphs()
    {
        if (this._mode === "capture")
        {
            this._drawCaptureGraphs();
            return;
        }

        const metrics =
            this._getVisibleMetrics();

        this._drawTwoSeriesGraph(
            "brightness-graph",
            metrics,
            "mean_brightness",
            "moving_average_brightness",
            "Brightness",
            "Moving average"
        );

        this._drawOneSeriesGraph(
            "brightness-delta-graph",
            metrics,
            "brightness_delta",
            "Delta brightness"
        );
    }

    // ## Draw frame-by-frame metrics for the currently selected capture.
    _drawCaptureGraphs()
    {
        const records =
            this._aCaptureMetrics;

        this._drawCaptureOneSeriesGraph(
            "brightness-graph",
            records,
            "mean_brightness",
            "Brightness"
        );

        this._drawCaptureOneSeriesGraph(
            "brightness-delta-graph",
            records,
            "brightness_delta_adjacent",
            "Delta brightness"
        );
    }
    

    // ## Hide graph time-window buttons during capture playback.
    _setGraphButtonsVisible(visible)
    {
        const buttonBar =
            document.querySelector(
                ".graphButtonBar"
            );

        if (buttonBar !== null)
        {
            buttonBar.style.display =
                visible ? "" : "none";
        }
    }

    

    

    _getNewestMetricTime()
    {
        let newestTime = 0.0;

        if (this._aMetricHistory.length > 0)
        {
            const newestMetric =
                this._aMetricHistory[
                    this._aMetricHistory.length - 1
                ];

            newestTime =
                Number(newestMetric.timestamp_monotonic ?? 0.0);
        }

        return newestTime;
    }

    _getVisibleMetrics()
    {
        let visibleMetrics = [];

        if (this._aMetricHistory.length > 0)
        {
            const newestTime = this._getNewestMetricTime();

            const minimumTime =
                newestTime - this._getWindowSeconds();

            visibleMetrics =
                this._aMetricHistory.filter(
                    (metric) =>
                    {
                        return (
                            Number(metric.timestamp_monotonic ?? 0.0) >=
                            minimumTime
                        );
                    }
                );
        }

        return visibleMetrics;
    }

    

    _getWindowSeconds()
    {
        return (
            this._iGraphWindowHours *
            60.0 *
            60.0
        );
    }

    _resizeCanvas(canvas)
    {
        const rect = canvas.getBoundingClientRect();

        canvas.width =
            Math.max(
                1,
                Math.floor(rect.width)
            );

        canvas.height =
            Math.max(
                1,
                Math.floor(rect.height)
            );
    }

    _drawAxes(
        context,
        width,
        height,
        minValue,
        maxValue
    )
    {
        const plot =
        {
            left: 46,
            right: width - 8,
            top: 8,
            bottom: height - 38
        };

        context.clearRect(0, 0, width, height);

        context.strokeStyle = "#d0d0d0";
        context.lineWidth = 1;

        for (let iGrid = 0; iGrid <= 4; iGrid += 1)
        {
            const y =
                plot.top +
                (
                    (plot.bottom - plot.top) *
                    iGrid /
                    4
                );

            context.beginPath();
            context.moveTo(plot.left, y);
            context.lineTo(plot.right, y);
            context.stroke();
        }

        context.strokeStyle = "#888888";

        context.beginPath();
        context.moveTo(plot.left, plot.top);
        context.lineTo(plot.left, plot.bottom);
        context.lineTo(plot.right, plot.bottom);
        context.stroke();

        this._drawXAxis(
            context,
            plot
        );

        context.fillStyle = "#333333";
        context.font = "10px Arial";
        context.textAlign = "left";

        context.fillText(
            maxValue.toFixed(1),
            4,
            plot.top + 8
        );

        context.fillText(
            minValue.toFixed(1),
            4,
            plot.bottom
        );

        return plot;
    }

    _drawXAxis(
        context,
        plot
    )
    {
        context.fillStyle = "#333333";
        context.font = "10px Arial";
        context.textAlign = "center";

        const tickCount = 4;

        for (let iTick = 0; iTick <= tickCount; iTick += 1)
        {
            const fraction =
                iTick / tickCount;

            const x =
                plot.left +
                (
                    (plot.right - plot.left) *
                    fraction
                );

            const ageSeconds =
                -this._getWindowSeconds() *
                (1.0 - fraction);

            context.beginPath();
            context.moveTo(x, plot.bottom);
            context.lineTo(x, plot.bottom + 4);
            context.stroke();

            context.fillText(
                this._formatXAxisLabel(ageSeconds),
                x,
                plot.bottom + 22
            );
        }
    }

    _formatXAxisLabel(ageSeconds)
    {
        let label = "now";

        const ageMagnitude =
            Math.abs(ageSeconds);

        if (ageMagnitude >= 24.0 * 60.0 * 60.0)
        {
            label =
                `-${(ageMagnitude / (24.0 * 60.0 * 60.0)).toFixed(0)}d`;
        }
        else if (ageMagnitude >= 60.0 * 60.0)
        {
            label =
                `-${(ageMagnitude / (60.0 * 60.0)).toFixed(1)}h`;
        }
        else if (ageMagnitude >= 60.0)
        {
            label =
                `-${(ageMagnitude / 60.0).toFixed(0)}m`;
        }
        else
        {
            label =
                `-${ageMagnitude.toFixed(0)}s`;
        }

        return label;
    }

    _drawLine(
        context,
        plot,
        samples,
        valueKey,
        minValue,
        maxValue,
        newestTimeSeconds,
        strokeStyle
    )
    {
        if (samples.length >= 2)
        {
            const valueRange =
                Math.max(
                    0.000001,
                    maxValue - minValue
                );

            context.strokeStyle = strokeStyle;
            context.lineWidth = 1.5;

            context.beginPath();

            samples.forEach(
                (sample, index) =>
                {
                    const sampleTimeSeconds =
                        this._getSampleTimeSeconds(sample);

                    const ageSeconds =
                        sampleTimeSeconds - newestTimeSeconds;

                    const x =
                        this._xAgeSecondsToPixel(
                            plot,
                            ageSeconds
                        );

                    const value =
                        Number(sample[valueKey] ?? 0.0);

                    const y =
                        plot.bottom -
                        (
                            (value - minValue) *
                            (plot.bottom - plot.top) /
                            valueRange
                        );

                    if (index === 0)
                    {
                        context.moveTo(x, y);
                    }
                    else
                    {
                        context.lineTo(x, y);
                    }
                }
            );

            context.stroke();
        }
    }

    _drawTwoSeriesGraph(
        canvasId,
        metrics,
        keyA,
        keyB,
        labelA,
        labelB
    )
    {
        const canvas =
            document.getElementById(canvasId);

        if (canvas !== null)
        {
            this._resizeCanvas(canvas);

            const context =
                canvas.getContext("2d");

            const valuesA =
                metrics.map(
                    (metric) =>
                    {
                        return Number(metric[keyA] ?? 0.0);
                    }
                );

            const valuesB =
                metrics.map(
                    (metric) =>
                    {
                        return Number(metric[keyB] ?? 0.0);
                    }
                );

            const limits =
                this._getValueLimits(
                    valuesA.concat(valuesB)
                );

            const plot =
                this._drawAxes(
                    context,
                    canvas.width,
                    canvas.height,
                    limits.minValue,
                    limits.maxValue
                );

            const newestTimeSeconds =
                this._getNewestMetricTime();

            this._drawLine(
                context,
                plot,
                metrics,
                keyA,
                limits.minValue,
                limits.maxValue,
                newestTimeSeconds,
                "#2f80ed"
            );

            this._drawLine(
                context,
                plot,
                metrics,
                keyB,
                limits.minValue,
                limits.maxValue,
                newestTimeSeconds,
                "#d35400"
            );

            context.fillStyle = "#2f80ed";
            context.textAlign = "left";

            context.fillText(
                labelA,
                plot.left + 4,
                plot.top + 12
            );

            context.fillStyle = "#d35400";

            context.fillText(
                labelB,
                plot.left + 110,
                plot.top + 12
            );
        }
    }

    _drawOneSeriesGraph(
        canvasId,
        metrics,
        key,
        label
    )
    {
        const canvas =
            document.getElementById(canvasId);

        if (canvas !== null)
        {
            this._resizeCanvas(canvas);

            const context =
                canvas.getContext("2d");

            const values =
                metrics.map(
                    (metric) =>
                    {
                        return Number(metric[key] ?? 0.0);
                    }
                );

            const limits =
                this._getValueLimits(values);

            const plot =
                this._drawAxes(
                    context,
                    canvas.width,
                    canvas.height,
                    limits.minValue,
                    limits.maxValue
                );

            const newestTimeSeconds =
                this._getNewestMetricTime();

            this._drawLine(
                context,
                plot,
                metrics,
                key,
                limits.minValue,
                limits.maxValue,
                newestTimeSeconds,
                "#2f80ed"
            );

            context.fillStyle = "#2f80ed";
            context.textAlign = "left";

            context.fillText(
                label,
                plot.left + 4,
                plot.top + 12
            );
        }
    }

    

    // ## Draw one capture-local metric using offset_ms as the x-axis.
    _drawCaptureOneSeriesGraph(
        canvasId,
        records,
        key,
        label
    )
    {
        const canvas =
            document.getElementById(canvasId);

        if (canvas !== null)
        {
            this._resizeCanvas(canvas);

            const context =
                canvas.getContext("2d");

            const values =
                records.map(
                    (record) =>
                    {
                        return Number(record[key] ?? 0.0);
                    }
                );

            const limits =
                this._getValueLimits(values);

            const plot =
                this._drawCaptureAxes(
                    context,
                    canvas.width,
                    canvas.height,
                    limits.minValue,
                    limits.maxValue,
                    records
                );

            this._drawCaptureLine(
                context,
                plot,
                records,
                key,
                limits.minValue,
                limits.maxValue,
                "#2f80ed"
            );

            this._drawCaptureTriggerMarker(
                context,
                plot,
                records,
                this._piTriggerFrameIndex,
                "#7a3db8",
                "Pi"
            );

            this._drawCaptureTriggerMarker(
                context,
                plot,
                records,
                this._replayTriggerFrameIndex,
                "#d47a00",
                "Replay"
            );

            this._drawCaptureCursor(
                context,
                plot,
                records
            );

            context.fillStyle = "#2f80ed";
            context.textAlign = "left";

            context.fillText(
                label,
                plot.left + 4,
                plot.top + 12
            );
        }
    }

    // ## Draw capture graph axes using capture-relative milliseconds.
    _drawCaptureAxes(
        context,
        width,
        height,
        minValue,
        maxValue,
        records
    )
    {
        const plot =
        {
            left: 46,
            right: width - 8,
            top: 8,
            bottom: height - 38
        };

        context.clearRect(0, 0, width, height);

        context.strokeStyle = "#d0d0d0";
        context.lineWidth = 1;

        for (let iGrid = 0; iGrid <= 4; iGrid += 1)
        {
            const y =
                plot.top +
                (
                    (plot.bottom - plot.top) *
                    iGrid /
                    4
                );

            context.beginPath();
            context.moveTo(plot.left, y);
            context.lineTo(plot.right, y);
            context.stroke();
        }

        context.strokeStyle = "#888888";

        context.beginPath();
        context.moveTo(plot.left, plot.top);
        context.lineTo(plot.left, plot.bottom);
        context.lineTo(plot.right, plot.bottom);
        context.stroke();

        this._drawCaptureXAxis(
            context,
            plot,
            records
        );

        context.fillStyle = "#333333";
        context.font = "10px Arial";
        context.textAlign = "left";

        context.fillText(
            maxValue.toFixed(1),
            4,
            plot.top + 8
        );

        context.fillText(
            minValue.toFixed(1),
            4,
            plot.bottom
        );

        return plot;
    }

    // ## Draw capture-local x-axis labels from 0 to capture duration.
    _drawCaptureXAxis(
        context,
        plot,
        records
    )
    {
        context.fillStyle = "#333333";
        context.font = "10px Arial";
        context.textAlign = "center";

        const tickCount = 4;
        const durationMs =
            this._getCaptureDurationMs(
                records
            );

        for (let iTick = 0; iTick <= tickCount; iTick += 1)
        {
            const fraction =
                iTick / tickCount;

            const x =
                plot.left +
                (
                    (plot.right - plot.left) *
                    fraction
                );

            const offsetMs =
                durationMs * fraction;

            context.beginPath();
            context.moveTo(x, plot.bottom);
            context.lineTo(x, plot.bottom + 4);
            context.stroke();

            context.fillText(
                this._formatCaptureOffsetLabel(
                    offsetMs
                ),
                x,
                plot.bottom + 22
            );
        }
    }

    // ## Draw capture-local line using offset_ms for x position.
    _drawCaptureLine(
        context,
        plot,
        records,
        valueKey,
        minValue,
        maxValue,
        strokeStyle
    )
    {
        if (records.length >= 2)
        {
            const valueRange =
                Math.max(
                    0.000001,
                    maxValue - minValue
                );

            context.strokeStyle = strokeStyle;
            context.lineWidth = 1.5;

            context.beginPath();

            records.forEach(
                (record, index) =>
                {
                    const x =
                        this._xCaptureOffsetToPixel(
                            plot,
                            records,
                            Number(record.offset_ms ?? 0.0)
                        );

                    const value =
                        Number(record[valueKey] ?? 0.0);

                    const y =
                        plot.bottom -
                        (
                            (value - minValue) *
                            (plot.bottom - plot.top) /
                            valueRange
                        );

                    if (index === 0)
                    {
                        context.moveTo(x, y);
                    }
                    else
                    {
                        context.lineTo(x, y);
                    }
                }
            );

            context.stroke();
        }
    }

    // ## Convert capture offset to graph x pixel.
    _xCaptureOffsetToPixel(
        plot,
        records,
        offsetMs
    )
    {
        const durationMs =
            Math.max(
                0.001,
                this._getCaptureDurationMs(
                    records
                )
            );

        const fraction =
            Math.max(
                0.0,
                Math.min(
                    1.0,
                    offsetMs / durationMs
                )
            );

        return (
            plot.left +
            (
                (plot.right - plot.left) *
                fraction
            )
        );
    }

    // ## Draw a fixed Pi or replay trigger marker on a capture graph.
    _drawCaptureTriggerMarker(
        context,
        plot,
        records,
        requestedFrameIndex,
        strokeStyle,
        label
    )
    {
        const frameIndex =
            this._clampCaptureFrameIndex(
                requestedFrameIndex
            );

        if (
            frameIndex === null ||
            records.length === 0
        )
        {
            return;
        }

        const record =
            records[frameIndex];

        const x =
            this._xCaptureOffsetToPixel(
                plot,
                records,
                Number(
                    record.offset_ms ?? 0.0
                )
            );

        context.save();
        context.strokeStyle =
            strokeStyle;
        context.lineWidth =
            1.5;

        context.beginPath();
        context.moveTo(
            x,
            plot.top
        );
        context.lineTo(
            x,
            plot.bottom
        );
        context.stroke();

        context.fillStyle =
            strokeStyle;
        context.textAlign =
            "center";
        context.font =
            "10px Arial";

        context.fillText(
            label,
            x,
            plot.top + 11
        );

        context.restore();
    }


    // ## Draw a vertical cursor at the current playback frame.
    _drawCaptureCursor(
        context,
        plot,
        records
    )
    {
        const frameIndex =
            this._clampCaptureFrameIndex(
                this._captureCursorFrameIndex
            );

        if (frameIndex !== null && records.length > 0)
        {
            const record =
                records[frameIndex];

            const x =
                this._xCaptureOffsetToPixel(
                    plot,
                    records,
                    Number(record.offset_ms ?? 0.0)
                );

            context.save();
            context.strokeStyle = "#c00020";
            context.lineWidth = 2;
            context.beginPath();
            context.moveTo(
                x,
                plot.top
            );
            context.lineTo(
                x,
                plot.bottom
            );
            context.stroke();

            context.fillStyle = "#c00020";
            context.textAlign = "center";
            context.font = "10px Arial";
            context.fillText(
                `F${frameIndex + 1}`,
                x,
                plot.bottom + 34
            );
            context.restore();
        }
    }

    // ## Pick the original Pi trigger frame as the first playback cursor.
    _getInitialCaptureCursorFrameIndex(analysis)
    {
        let frameIndex =
            null;

        const candidate =
            analysis?.candidate || {};

        if (
            candidate.trigger_frame_index !== null &&
            candidate.trigger_frame_index !== undefined
        )
        {
            frameIndex =
                Number(
                    candidate.trigger_frame_index
                );
        }
        else if (
            analysis?.trigger_frame_index !== null &&
            analysis?.trigger_frame_index !== undefined
        )
        {
            frameIndex =
                Number(
                    analysis.trigger_frame_index
                );
        }
        else if (
            candidate.trigger_frame_number !== null &&
            candidate.trigger_frame_number !== undefined
        )
        {
            frameIndex =
                Number(
                    candidate.trigger_frame_number
                ) -
                1;
        }
        else if (
            analysis?.trigger_frame_number !== null &&
            analysis?.trigger_frame_number !== undefined
        )
        {
            frameIndex =
                Number(
                    analysis.trigger_frame_number
                ) -
                1;
        }

        return this._clampCaptureFrameIndex(
            frameIndex
        );
    }

    // ## Keep requested frame index inside the current capture frame range.
    _clampCaptureFrameIndex(frameIndex)
    {
        let clampedIndex =
            null;

        if (frameIndex !== null && frameIndex !== undefined && this._aCaptureMetrics.length > 0)
        {
            clampedIndex =
                Math.min(
                    this._aCaptureMetrics.length - 1,
                    Math.max(
                        0,
                        Math.round(
                            Number(frameIndex)
                        )
                    )
                );

            if (Number.isNaN(clampedIndex))
            {
                clampedIndex =
                    null;
            }
        }

        return clampedIndex;
    }

    // ## Return the capture-local graph duration in milliseconds.
    _getCaptureDurationMs(records)
    {
        let durationMs = 0.0;

        if (records.length > 0)
        {
            durationMs = Number(
                records[records.length - 1].offset_ms ?? 0.0
            );
        }

        return durationMs;
    }

    // ## Format capture-local x-axis offsets.
    _formatCaptureOffsetLabel(offsetMs)
    {
        let label =
            `${offsetMs.toFixed(0)}ms`;

        if (offsetMs >= 1000.0)
        {
            label =
                `${(offsetMs / 1000.0).toFixed(2)}s`;
        }

        return label;
    }

    _getSampleTimeSeconds(sample)
    {
        let sampleTimeSeconds =
            Number(sample.timestamp_monotonic ?? 0.0);

        if (sample.timestamp !== undefined)
        {
            sampleTimeSeconds =
                Number(sample.timestamp ?? 0) / 1000.0;
        }

        return sampleTimeSeconds;
    }

    _xAgeSecondsToPixel(
        plot,
        ageSeconds
    )
    {
        const windowSeconds =
            this._getWindowSeconds();

        const fraction =
            (ageSeconds + windowSeconds) /
            windowSeconds;

        const clippedFraction =
            Math.max(
                0.0,
                Math.min(
                    1.0,
                    fraction
                )
            );

        return (
            plot.left +
            (
                (plot.right - plot.left) *
                clippedFraction
            )
        );
    }

    _getValueLimits(values)
    {
        let minValue = 0.0;
        let maxValue = 1.0;

        if (values.length > 0)
        {
            minValue = Math.min(...values);
            maxValue = Math.max(...values);

            if (minValue === maxValue)
            {
                minValue -= 1.0;
                maxValue += 1.0;
            }
        }

        return {
            minValue,
            maxValue
        };
    }
}