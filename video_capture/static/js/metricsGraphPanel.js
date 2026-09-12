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
        this._captureTelemetry = null;
        this._mode = "live";
        this._aCaptureMetrics = [];
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
                    () => this.setGraphWindow(
                        Number(button.dataset.window)
                    )
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

    updateTelemetry(result)
    {
        this._captureTelemetry =
            result?.capture_telemetry || null;

        this.drawAllGraphs();
    }

    async updateMetricHistory()
    {
        try
        {
            const result =
                await getJson("/metrics_history");

            if (result.success)
            {
                this._aMetricHistory =
                    result.metrics || [];

                this.drawAllGraphs();
            }
        }
        catch (error)
        {
            console.error(error);
        }
    }

    showCaptureMetrics(captureFile)
    {
        const analysis =
            captureFile?.analysis || {};

        this._mode = "capture";
        this._aCaptureMetrics =
            analysis.frame_records || [];

        this._piTriggerFrameIndex =
            this._getInitialCaptureCursorFrameIndex(
                analysis
            );

        this._captureCursorFrameIndex =
            this._piTriggerFrameIndex;

        this._replayTriggerFrameIndex = null;

        this._setGraphButtonsVisible(false);
        this.drawAllGraphs();
    }

    showLiveMetrics()
    {
        this._mode = "live";
        this._aCaptureMetrics = [];
        this._captureCursorFrameIndex = null;
        this._piTriggerFrameIndex = null;
        this._replayTriggerFrameIndex = null;
        this._setGraphButtonsVisible(true);
        this.drawAllGraphs();
    }

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
            this._drawCaptureBrightness();
        }
        else
        {
            this._drawLiveBrightness();
        }

        this._drawCaptureActivity();
    }

    _drawLiveBrightness()
    {
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
    }

    _drawCaptureBrightness()
    {
        const records =
            this._aCaptureMetrics;

        const canvas =
            document.getElementById(
                "brightness-graph"
            );

        if (canvas === null)
        {
            return;
        }

        this._resizeCanvas(canvas);

        const context =
            canvas.getContext("2d");

        const values =
            records.map(
                (record) => Number(
                    record.mean_brightness ?? 0
                )
            );

        const limits =
            this._getValueLimits(values);

        const plot =
            this._drawAxes(
                context,
                canvas.width,
                canvas.height,
                limits.minValue,
                limits.maxValue,
                true
            );

        if (records.length >= 2)
        {
            const durationMs =
                Math.max(
                    1,
                    Number(
                        records[records.length - 1].offset_ms ?? 0
                    )
                );

            const valueRange =
                Math.max(
                    0.000001,
                    limits.maxValue - limits.minValue
                );

            context.strokeStyle = "#2f80ed";
            context.lineWidth = 1.5;
            context.beginPath();

            records.forEach(
                (record, index) =>
                {
                    const fraction =
                        Math.max(
                            0,
                            Math.min(
                                1,
                                Number(record.offset_ms ?? 0) /
                                durationMs
                            )
                        );

                    const x =
                        plot.left +
                        (plot.right - plot.left) * fraction;

                    const value =
                        Number(record.mean_brightness ?? 0);

                    const y =
                        plot.bottom -
                        (value - limits.minValue) *
                        (plot.bottom - plot.top) /
                        valueRange;

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

            this._drawCaptureMarker(
                context,
                plot,
                records,
                this._piTriggerFrameIndex,
                "#7a3db8",
                "Pi"
            );

            this._drawCaptureMarker(
                context,
                plot,
                records,
                this._replayTriggerFrameIndex,
                "#d47a00",
                "Replay"
            );

            this._drawCaptureMarker(
                context,
                plot,
                records,
                this._captureCursorFrameIndex,
                "#c00020",
                "Frame"
            );
        }
    }

    _drawCaptureActivity()
    {
        const canvas =
            document.getElementById(
                "capture-activity-graph"
            );

        if (canvas === null)
        {
            return;
        }

        this._resizeCanvas(canvas);

        const context =
            canvas.getContext("2d");

        const telemetry =
            this._captureTelemetry || {};

        // The backend keeps a dedicated ten-bucket, 30-second view for the
        // 5-minute graph. Longer graph windows continue to use the 5-minute
        // buckets maintained for the full 24-hour session.
        const useRecentTelemetry =
            this._getWindowSeconds() <= (5 * 60 + 1);

        const selectedTelemetry =
            useRecentTelemetry && telemetry.recent
                ? telemetry.recent
                : telemetry;

        const buckets =
            Array.isArray(selectedTelemetry.buckets)
                ? selectedTelemetry.buckets
                : [];

        const bucketSeconds =
            Number(selectedTelemetry.bucket_seconds ?? 300);

        const cutoffMs =
            Date.now() -
            this._getWindowSeconds() * 1000;

        const visible =
            buckets.filter(
                (bucket) =>
                {
                    const startMs =
                        Date.parse(bucket?.start_utc ?? "");

                    return (
                        Number.isFinite(startMs) &&
                        startMs + bucketSeconds * 1000 > cutoffMs
                    );
                }
            );

        let maxActivity = 1;

        visible.forEach(
            (bucket) =>
            {
                const candidates =
                    Math.max(
                        0,
                        Number(bucket.candidates ?? 0)
                    );

                const captures =
                    Math.max(
                        0,
                        Number(bucket.captures ?? 0)
                    );

                const automaticCaptures =
                    Math.min(
                        candidates,
                        Math.max(
                            0,
                            Number(bucket.automatic_captures ?? 0)
                        )
                    );

                const candidateOnly =
                    Math.max(
                        0,
                        candidates - automaticCaptures
                    );

                maxActivity =
                    Math.max(
                        maxActivity,
                        captures + candidateOnly
                    );
            }
        );

        const plot =
            this._drawAxes(
                context,
                canvas.width,
                canvas.height,
                0,
                maxActivity,
                false
            );

        if (visible.length > 0)
        {
            const newestStartMs =
                Math.max(
                    ...visible.map(
                        (bucket) =>
                            Date.parse(bucket.start_utc)
                    )
                );

            const newestEndMs =
                newestStartMs + bucketSeconds * 1000;

            const windowMs =
                this._getWindowSeconds() * 1000;

            const availableWidth =
                plot.right - plot.left;

            const nominalBarWidth =
                Math.max(
                    1,
                    availableWidth *
                    (bucketSeconds * 1000) /
                    windowMs
                );

            visible.forEach(
                (bucket) =>
                {
                    const bucketStartMs =
                        Date.parse(bucket.start_utc);

                    const ageMs =
                        bucketStartMs - newestEndMs;

                    const fraction =
                        (ageMs + windowMs) /
                        windowMs;

                    const x =
                        plot.left +
                        availableWidth * fraction;

                    const candidates =
                        Math.max(
                            0,
                            Number(bucket.candidates ?? 0)
                        );

                    const captures =
                        Math.max(
                            0,
                            Number(bucket.captures ?? 0)
                        );

                    const automaticCaptures =
                        Math.min(
                            candidates,
                            Math.max(
                                0,
                                Number(bucket.automatic_captures ?? 0)
                            )
                        );

                    const candidateOnly =
                        Math.max(
                            0,
                            candidates - automaticCaptures
                        );

                    const scale =
                        (plot.bottom - plot.top) /
                        maxActivity;

                    const capturedHeight =
                        captures * scale;

                    const candidateOnlyHeight =
                        candidateOnly * scale;

                    context.fillStyle = "#2f80ed";
                    context.fillRect(
                        x,
                        plot.bottom - capturedHeight,
                        Math.max(1, nominalBarWidth - 1),
                        capturedHeight
                    );

                    context.fillStyle = "#d6a348";
                    context.fillRect(
                        x,
                        plot.bottom - capturedHeight - candidateOnlyHeight,
                        Math.max(1, nominalBarWidth - 1),
                        candidateOnlyHeight
                    );
                }
            );
        }

        context.font = "10px Arial";
        context.textAlign = "left";
        context.fillStyle = "#2f80ed";
        context.fillText(
            "Captured",
            plot.left + 4,
            plot.top + 12
        );
        context.fillStyle = "#d6a348";
        context.fillText(
            "Candidate only",
            plot.left + 72,
            plot.top + 12
        );
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

        if (canvas === null)
        {
            return;
        }

        this._resizeCanvas(canvas);
        const context = canvas.getContext("2d");

        const values = [];
        metrics.forEach(
            (metric) =>
            {
                values.push(Number(metric[keyA] ?? 0));
                values.push(Number(metric[keyB] ?? 0));
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
                limits.maxValue,
                false
            );

        const newestTime =
            this._getNewestMetricTime();

        this._drawLine(
            context,
            plot,
            metrics,
            keyA,
            limits,
            newestTime,
            "#2f80ed"
        );

        this._drawLine(
            context,
            plot,
            metrics,
            keyB,
            limits,
            newestTime,
            "#d35400"
        );

        context.font = "10px Arial";
        context.textAlign = "left";
        context.fillStyle = "#2f80ed";
        context.fillText(labelA, plot.left + 4, plot.top + 12);
        context.fillStyle = "#d35400";
        context.fillText(labelB, plot.left + 90, plot.top + 12);
    }

    _drawLine(
        context,
        plot,
        samples,
        key,
        limits,
        newestTime,
        strokeStyle
    )
    {
        if (samples.length < 2)
        {
            return;
        }

        const valueRange =
            Math.max(
                0.000001,
                limits.maxValue - limits.minValue
            );

        context.strokeStyle = strokeStyle;
        context.lineWidth = 1.5;
        context.beginPath();

        samples.forEach(
            (sample, index) =>
            {
                const sampleTime =
                    Number(sample.timestamp_monotonic ?? 0);

                const ageSeconds =
                    sampleTime - newestTime;

                const fraction =
                    Math.max(
                        0,
                        Math.min(
                            1,
                            (ageSeconds + this._getWindowSeconds()) /
                            this._getWindowSeconds()
                        )
                    );

                const x =
                    plot.left +
                    (plot.right - plot.left) * fraction;

                const value =
                    Number(sample[key] ?? 0);

                const y =
                    plot.bottom -
                    (value - limits.minValue) *
                    (plot.bottom - plot.top) /
                    valueRange;

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

    _drawAxes(
        context,
        width,
        height,
        minValue,
        maxValue,
        captureMode
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

        for (let index = 0; index <= 4; index += 1)
        {
            const y =
                plot.top +
                (plot.bottom - plot.top) * index / 4;

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

        context.fillStyle = "#333333";
        context.font = "10px Arial";
        context.textAlign = "left";
        context.fillText(
            Number(maxValue).toFixed(
                Number.isInteger(maxValue) ? 0 : 1
            ),
            4,
            plot.top + 8
        );
        context.fillText(
            Number(minValue).toFixed(
                Number.isInteger(minValue) ? 0 : 1
            ),
            4,
            plot.bottom
        );

        if (!captureMode)
        {
            this._drawTimeAxis(
                context,
                plot
            );
        }

        return plot;
    }

    _drawTimeAxis(context, plot)
    {
        context.fillStyle = "#333333";
        context.font = "10px Arial";
        context.textAlign = "center";

        for (let index = 0; index <= 4; index += 1)
        {
            const fraction = index / 4;
            const x =
                plot.left +
                (plot.right - plot.left) * fraction;

            const ageSeconds =
                -this._getWindowSeconds() *
                (1 - fraction);

            context.beginPath();
            context.moveTo(x, plot.bottom);
            context.lineTo(x, plot.bottom + 4);
            context.stroke();

            context.fillText(
                this._formatAgeLabel(ageSeconds),
                x,
                plot.bottom + 22
            );
        }
    }

    _formatAgeLabel(ageSeconds)
    {
        const age = Math.abs(ageSeconds);

        if (age < 1)
        {
            return "now";
        }

        if (age >= 3600)
        {
            return `-${(age / 3600).toFixed(
                age >= 21600 ? 0 : 1
            )}h`;
        }

        return `-${(age / 60).toFixed(0)}m`;
    }

    _drawCaptureMarker(
        context,
        plot,
        records,
        frameIndex,
        strokeStyle,
        label
    )
    {
        const index =
            this._clampCaptureFrameIndex(frameIndex);

        if (index === null || records.length === 0)
        {
            return;
        }

        const durationMs =
            Math.max(
                1,
                Number(
                    records[records.length - 1].offset_ms ?? 0
                )
            );

        const fraction =
            Number(records[index].offset_ms ?? 0) /
            durationMs;

        const x =
            plot.left +
            (plot.right - plot.left) * fraction;

        context.save();
        context.strokeStyle = strokeStyle;
        context.lineWidth = label === "Frame" ? 2 : 1.5;
        context.beginPath();
        context.moveTo(x, plot.top);
        context.lineTo(x, plot.bottom);
        context.stroke();
        context.fillStyle = strokeStyle;
        context.font = "10px Arial";
        context.textAlign = "center";
        context.fillText(label, x, plot.top + 11);
        context.restore();
    }

    _getVisibleMetrics()
    {
        if (this._aMetricHistory.length === 0)
        {
            return [];
        }

        const newest =
            this._getNewestMetricTime();

        const minimum =
            newest - this._getWindowSeconds();

        return this._aMetricHistory.filter(
            (metric) =>
                Number(metric.timestamp_monotonic ?? 0) >= minimum
        );
    }

    _getNewestMetricTime()
    {
        if (this._aMetricHistory.length === 0)
        {
            return 0;
        }

        return Number(
            this._aMetricHistory[
                this._aMetricHistory.length - 1
            ].timestamp_monotonic ?? 0
        );
    }

    _getWindowSeconds()
    {
        return this._iGraphWindowHours * 3600;
    }

    _setGraphButtonsVisible(visible)
    {
        const bar =
            document.querySelector(
                ".graphButtonBar"
            );

        if (bar !== null)
        {
            bar.style.display =
                visible ? "" : "none";
        }
    }

    _resizeCanvas(canvas)
    {
        const rect =
            canvas.getBoundingClientRect();

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

    _getValueLimits(values)
    {
        let minValue = 0;
        let maxValue = 1;

        if (values.length > 0)
        {
            minValue = Math.min(...values);
            maxValue = Math.max(...values);

            if (minValue === maxValue)
            {
                minValue -= 1;
                maxValue += 1;
            }
        }

        return {
            minValue,
            maxValue
        };
    }

    _getInitialCaptureCursorFrameIndex(analysis)
    {
        const candidate =
            analysis?.candidate || {};

        let frameIndex =
            candidate.trigger_frame_index ??
            analysis?.trigger_frame_index ??
            null;

        if (frameIndex === null)
        {
            const frameNumber =
                candidate.trigger_frame_number ??
                analysis?.trigger_frame_number ??
                null;

            if (frameNumber !== null)
            {
                frameIndex = Number(frameNumber) - 1;
            }
        }

        return this._clampCaptureFrameIndex(
            frameIndex
        );
    }

    _clampCaptureFrameIndex(frameIndex)
    {
        if (
            frameIndex === null ||
            frameIndex === undefined ||
            this._aCaptureMetrics.length === 0
        )
        {
            return null;
        }

        const numericIndex =
            Number(frameIndex);

        if (!Number.isFinite(numericIndex))
        {
            return null;
        }

        return Math.min(
            this._aCaptureMetrics.length - 1,
            Math.max(
                0,
                Math.round(numericIndex)
            )
        );
    }
}
