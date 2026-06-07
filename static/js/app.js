(() =>
{
    let iGraphWindowHours = 1;


    function setStatus(statusText)
    {
        document.getElementById(
            "status-value"
        ).textContent = statusText;
    }


    async function postJson(url)
    {
        const response =
            await fetch(
                url,
                {
                    method: "POST"
                }
            );

        return await response.json();
    }


    async function getJson(url)
    {
        const response =
            await fetch(
                url
            );

        return await response.json();
    }


    async function captureOnce()
    {
        setStatus(
            "Capturing..."
        );

        try
        {
            const result =
                await postJson(
                    "/capture_once"
                );

            setStatus(
                result.success ? "Capture Complete" : "Capture Failed"
            );

            refreshEventLog();
        }
        catch (error)
        {
            setStatus(
                "Communication Error"
            );

            console.error(
                error
            );
        }
    }


    async function startPreview()
    {
        try
        {
            const result =
                await postJson(
                    "/preview_start"
                );

            setStatus(
                result.message
            );

            if (result.success) {
                showPreview();
            }

            refreshEventLog();
        }
        catch (error)
        {
            setStatus(
                "Preview Start Failed"
            );

            console.error(
                error
            );
        }
    }


    async function stopPreview()
    {
        try
        {
            const result =
                await postJson(
                    "/preview_stop"
                );

            setStatus(
                result.message
            );

            if (result.success) {
                hidePreview();
            }

            refreshEventLog();
        }
        catch (error)
        {
            setStatus(
                "Preview Stop Failed"
            );

            console.error(
                error
            );
        }
    }


    async function updatePreviewStatus()
    {
        try
        {
            const result =
                await getJson(
                    "/preview_status"
                );

            if (result.running)
            {
                setStatus(
                    "Preview Running"
                );
            }
        }
        catch (error)
        {
            console.error(
                error
            );
        }
    }


    async function bufferStart()
    {
        try
        {
            const result =
                await postJson(
                    "/buffer_start"
                );

            setStatus(
                result.message
            );

            refreshEventLog();
        }
        catch (error)
        {
            setStatus(
                "Buffer Start Failed"
            );

            console.error(
                error
            );
        }
    }


    async function bufferStop()
    {
        try
        {
            const result =
                await postJson(
                    "/buffer_stop"
                );

            setStatus(
                result.message
            );

            refreshEventLog();
        }
        catch (error)
        {
            setStatus(
                "Buffer Stop Failed"
            );

            console.error(
                error
            );
        }
    }


    async function bufferCapture()
    {
        try
        {
            const result =
                await postJson(
                    "/buffer_capture"
                );

            setStatus(
                result.message
            );

            refreshEventLog();
        }
        catch (error)
        {
            setStatus(
                "Buffer Capture Failed"
            );

            console.error(
                error
            );
        }
    }


    async function bufferStatus()
    {
        try
        {
            const result =
                await getJson(
                    "/buffer_status"
                );

            document.getElementById(
                "buffer-status-value"
            ).textContent =
                JSON.stringify(
                    result,
                    null,
                    2
                );

            setStatus(
                result.message
            );
        }
        catch (error)
        {
            setStatus(
                "Buffer Status Failed"
            );

            console.error(
                error
            );
        }
    }


    async function refreshEventLog()
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
        catch (error)
        {
            console.error(
                error
            );
        }
    }


    async function clearEventLog()
    {
        try
        {
            const result =
                await postJson(
                    "/event_log_clear"
                );

            setStatus(
                result.message
            );

            refreshEventLog();
        }
        catch (error)
        {
            setStatus(
                "Clear Event Log Failed"
            );

            console.error(
                error
            );
        }
    }

    async function displayPreviewStart()
    {
        try
        {
            const result =
                await postJson(
                    "/display_preview_start"
                );

            setStatus(
                result.message
            );

            refreshEventLog();
        }
        catch (error)
        {
            setStatus(
                "Display Preview Start Failed"
            );

            console.error(
                error
            );
        }
    }


    async function displayPreviewStop()
    {
        try
        {
            const result =
                await postJson(
                    "/display_preview_stop"
                );

            setStatus(
                result.message
            );

            refreshEventLog();
        }
        catch (error)
        {
            setStatus(
                "Display Preview Stop Failed"
            );

            console.error(
                error
            );
        }
    }

    async function updateSystemStatus()
    {
        try
        {
            const result =
                await getJson(
                    "/system_status"
                );

            const heartbeatValue =
                document.getElementById(
                    "heartbeat-value"
                );

            heartbeatValue.textContent =
                `| Server: ${result.server_time_utc} ` +
                `| Preview: ${result.preview_running ? "on" : "off"} ` +
                `| Buffer: ${result.buffer_running ? "on" : "off"} ` +
                `| FPS: ${result.camera_fps.toFixed(1)} ` +
                `| Frames: ${result.camera_frames} ` +
                `| Buffer: ${result.buffer_count}/${result.buffer_capacity} ` +
                `| RAM: ${result.memory_mb.toFixed(0)} MB`;
        }
        catch (error)
        {
            console.error(
                error
            );
        }
    }


    function createGraphData(iHours)
    {
        const values = [];
        const iPointCount = 120;

        for (let iPoint = 0; iPoint < iPointCount; iPoint += 1)
        {
            const dPhase =
                (iPoint / iPointCount) * Math.PI * 4.0;

            const dNoise =
                Math.sin(iPoint * 1.7) * 4.0;

            const dValue =
                50.0 +
                Math.sin(dPhase) * 20.0 +
                dNoise +
                (iHours * 0.35);

            values.push(
                dValue
            );
        }

        return values;
    }


    function drawHistoryGraph()
    {
        const canvas =
            document.getElementById(
                "history-graph"
            );

        const context =
            canvas.getContext(
                "2d"
            );

        const rect =
            canvas.getBoundingClientRect();

        canvas.width =
            Math.floor(
                rect.width
            );

        canvas.height =
            Math.floor(
                rect.height
            );

        const iWidth =
            canvas.width;

        const iHeight =
            canvas.height;

        const values =
            createGraphData(
                iGraphWindowHours
            );

        const dMean =
            values.reduce(
                (dTotal, dValue) => dTotal + dValue,
                0.0
            ) / values.length;

        document.getElementById(
            "graph-mean-value"
        ).textContent =
            `Mean: ${dMean.toFixed(1)}`;

        context.clearRect(
            0,
            0,
            iWidth,
            iHeight
        );

        context.strokeStyle =
            "#cccccc";

        context.lineWidth =
            1;

        for (let iGrid = 0; iGrid <= 4; iGrid += 1)
        {
            const y =
                (iHeight * iGrid) / 4;

            context.beginPath();
            context.moveTo(
                0,
                y
            );
            context.lineTo(
                iWidth,
                y
            );
            context.stroke();
        }

        context.strokeStyle =
            "#2f80ed";

        context.lineWidth =
            2;

        context.beginPath();

        values.forEach(
            (dValue, iIndex) =>
            {
                const x =
                    (iIndex / (values.length - 1)) * iWidth;

                const y =
                    iHeight - ((dValue / 100.0) * iHeight);

                if (iIndex === 0)
                {
                    context.moveTo(
                        x,
                        y
                    );
                }
                else
                {
                    context.lineTo(
                        x,
                        y
                    );
                }
            }
        );

        context.stroke();

        context.fillStyle =
            "#333333";

        context.font =
            "10px Arial";

        context.fillText(
            `Window: ${iGraphWindowHours} HR`,
            8,
            14
        );
    }


    function setGraphWindow(iHours)
    {
        iGraphWindowHours =
            iHours;

        document.querySelectorAll(
            ".graphButton"
        ).forEach(
            (button) =>
            {
                button.classList.toggle(
                    "graphButtonActive",
                    Number(button.dataset.window) === iHours
                );
            }
        );

        drawHistoryGraph();
    }


    function initializeGraph()
    {
        document.querySelectorAll(
            ".graphButton"
        ).forEach(
            (button) =>
            {
                button.addEventListener(
                    "click",
                    () =>
                    {
                        setGraphWindow(
                            Number(button.dataset.window)
                        );
                    }
                );
            }
        );

        setGraphWindow(
            1
        );

        window.addEventListener(
            "resize",
            drawHistoryGraph
        );
    }


    function showPreview()
    {
        const video =
            document.getElementById(
                "camera-video"
            );

        const placeholder =
            document.getElementById(
                "preview-placeholder"
            );

        placeholder.classList.add(
            "cameraImageHidden"
        );

        video.classList.remove(
            "cameraImageHidden"
        );

        video.src =
            "/hls/stream.m3u8";

        video.load();

        video.play().catch(
            (error) =>
            {
                console.error(
                    error
                );
            }
        );
    }


    function hidePreview()
    {
        const video =
            document.getElementById(
                "camera-video"
            );

        const placeholder =
            document.getElementById(
                "preview-placeholder"
            );

        video.pause();

        video.removeAttribute(
            "src"
        );

        video.load();

        video.classList.add(
            "cameraImageHidden"
        );

        placeholder.classList.remove(
            "cameraImageHidden"
        );
    }

    function initializePage()
    {
        document.getElementById("capture-button").addEventListener("click", captureOnce);
        document.getElementById("preview-start-button").addEventListener("click", startPreview);
        document.getElementById("preview-stop-button").addEventListener("click", stopPreview);
        document.getElementById("buffer-start-button").addEventListener("click", bufferStart);
        document.getElementById("buffer-stop-button").addEventListener("click", bufferStop);
        document.getElementById("buffer-capture-button").addEventListener("click", bufferCapture);
        document.getElementById("buffer-status-button").addEventListener("click", bufferStatus);
        document.getElementById("event-log-clear-button").addEventListener("click", clearEventLog);

        document
            .getElementById(
                "display-preview-start-button"
            )
            .addEventListener(
                "click",
                displayPreviewStart
            );

        document
            .getElementById(
                "display-preview-stop-button"
            )
            .addEventListener(
                "click",
                displayPreviewStop
            );

        setStatus(
            "Ready"
        );

        initializeGraph();
        updatePreviewStatus();
        refreshEventLog();

        setInterval(
            refreshEventLog,
            1000
        );

        updateSystemStatus();

        setInterval(
            updateSystemStatus,
            1000
        );
    }


    document.addEventListener(
        "DOMContentLoaded",
        initializePage
    );
})();