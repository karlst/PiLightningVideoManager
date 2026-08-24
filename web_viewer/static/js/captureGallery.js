"use strict";

import "./captureViewer.js?v=26";


class CaptureGallery
{
    constructor()
    {
        this._captures = [];
        this._siteFilter = "";
        this._galleryView = null;
        this._viewerView = null;
        this._tableBody = null;
        this._message = null;
        this._captureCount = null;
        this._siteSelect = null;
        this._captureViewer = null;
    }


    async initialize()
    {
        this._galleryView =
            document.getElementById(
                "gallery-view"
            );

        this._viewerView =
            document.getElementById(
                "viewer-view"
            );

        this._tableBody =
            document.getElementById(
                "capture-table-body"
            );

        this._message =
            document.getElementById(
                "gallery-message"
            );

        this._captureCount =
            document.getElementById(
                "capture-count"
            );

        this._siteSelect =
            document.getElementById(
                "site-filter"
            );

        this._captureViewer =
            document.getElementById(
                "capture-viewer"
            );

        document.getElementById(
            "back-to-captures-button"
        )?.addEventListener(
            "click",
            () => this._showGallery()
        );

        this._siteSelect?.addEventListener(
            "change",
            () =>
            {
                this._siteFilter =
                    this._siteSelect.value;

                this._renderCaptureList();
            }
        );

        await this._loadCaptureIndex();
    }


    async _loadCaptureIndex()
    {
        this._setMessage(
            "Loading captures..."
        );

        try
        {
            const response =
                await fetch(
                    "captures.json",
                    {
                        cache: "no-store"
                    }
                );

            if (!response.ok)
            {
                throw new Error(
                    `captures.json returned HTTP ${response.status}`
                );
            }

            const documentData =
                await response.json();

            this._captures =
                Array.isArray(
                    documentData.captures
                )
                    ? documentData.captures
                    : [];

            this._populateSiteFilter();
            this._renderCaptureList();
        }
        catch (error)
        {
            console.error(
                error
            );

            this._captures =
                [];

            this._renderCaptureList();

            this._setMessage(
                "Unable to load captures.json."
            );
        }
    }


    _populateSiteFilter()
    {
        if (this._siteSelect === null)
        {
            return;
        }

        const sites =
            [
                ...new Set(
                    this._captures
                        .map(
                            (capture) =>
                                String(
                                    capture.site_name || ""
                                ).trim()
                        )
                        .filter(
                            (siteName) =>
                                siteName !== ""
                        )
                )
            ].sort();

        this._siteSelect.replaceChildren();

        const allOption =
            document.createElement(
                "option"
            );

        allOption.value =
            "";

        allOption.textContent =
            "All sites";

        this._siteSelect.appendChild(
            allOption
        );

        sites.forEach(
            (siteName) =>
            {
                const option =
                    document.createElement(
                        "option"
                    );

                option.value =
                    siteName;

                option.textContent =
                    siteName;

                this._siteSelect.appendChild(
                    option
                );
            }
        );
    }


    _renderCaptureList()
    {
        if (this._tableBody === null)
        {
            return;
        }

        const captures =
            this._captures
                .filter(
                    (capture) =>
                    {
                        return (
                            this._siteFilter === "" ||
                            capture.site_name === this._siteFilter
                        );
                    }
                );

        this._tableBody.replaceChildren();

        captures.forEach(
            (capture) =>
            {
                const row =
                    document.createElement(
                        "tr"
                    );

                row.tabIndex =
                    0;

                row.className =
                    "captureRow";

                row.appendChild(
                    this._cell(
                        capture.video_name || "--"
                    )
                );

                row.appendChild(
                    this._cell(
                        capture.site_name || "--"
                    )
                );

                row.addEventListener(
                    "click",
                    () => this._openCapture(
                        capture
                    )
                );

                row.addEventListener(
                    "keydown",
                    (event) =>
                    {
                        if (
                            event.key === "Enter" ||
                            event.key === " "
                        )
                        {
                            event.preventDefault();

                            this._openCapture(
                                capture
                            );
                        }
                    }
                );

                this._tableBody.appendChild(
                    row
                );
            }
        );

        if (this._captureCount !== null)
        {
            this._captureCount.textContent =
                captures.length === 1
                    ? "1 capture"
                    : `${captures.length} captures`;
        }

        if (captures.length === 0)
        {
            this._setMessage(
                this._captures.length === 0
                    ? "No published captures."
                    : "No captures match this site."
            );
        }
        else
        {
            this._setMessage(
                ""
            );
        }
    }


    async _openCapture(capture)
    {
        if (this._captureViewer === null)
        {
            return;
        }

        const videoUrl =
            capture.video_url;

        const sidecarUrl =
            capture.sidecar_url;

        if (!videoUrl || !sidecarUrl)
        {
            this._setMessage(
                "Capture entry is missing video_url or sidecar_url."
            );

            return;
        }

        this._galleryView?.classList.add(
            "hidden"
        );

        this._viewerView?.classList.remove(
            "hidden"
        );

        try
        {
            await this._captureViewer.loadCapture(
                {
                    videoUrl,
                    sidecarUrl,
                    name:
                        capture.video_name ||
                        this._filenameFromUrl(
                            videoUrl
                        )
                }
            );
        }
        catch (error)
        {
            console.error(
                error
            );

            this._showGallery();

            this._setMessage(
                "Unable to load selected capture."
            );
        }
    }


    _showGallery()
    {
        this._captureViewer?.clearCapture();

        this._viewerView?.classList.add(
            "hidden"
        );

        this._galleryView?.classList.remove(
            "hidden"
        );
    }


    _cell(text)
    {
        const cell =
            document.createElement(
                "td"
            );

        cell.textContent =
            text;

        return cell;
    }


    _setMessage(text)
    {
        if (this._message === null)
        {
            return;
        }

        this._message.textContent =
            text;

        this._message.classList.toggle(
            "hidden",
            text === ""
        );
    }


    _filenameFromUrl(url)
    {
        try
        {
            return decodeURIComponent(
                new URL(
                    url,
                    window.location.href
                ).pathname
                    .split("/")
                    .pop()
            );
        }
        catch
        {
            return String(
                url
            );
        }
    }
}


document.addEventListener(
    "DOMContentLoaded",
    async () =>
    {
        const gallery =
            new CaptureGallery();

        await gallery.initialize();
    }
);
