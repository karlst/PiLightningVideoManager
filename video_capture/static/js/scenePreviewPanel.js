"use strict";


// Low-rate dashboard still preview.  This is intentionally independent of the
// modeless live PreviewPanel so it cannot change live-preview behavior.
const SCENE_PREVIEW_REFRESH_MS = 120 * 1000;


export class ScenePreviewPanel
{
    constructor()
    {
        this._timerId = null;
    }


    initialize()
    {
        this._refresh();

        this._timerId =
            window.setInterval(
                () => this._refresh(),
                SCENE_PREVIEW_REFRESH_MS
            );
    }


    _refresh()
    {
        const image =
            document.getElementById(
                "scene-preview-image"
            );

        const placeholder =
            document.getElementById(
                "scene-preview-placeholder"
            );

        if (image === null)
        {
            return;
        }

        image.onload =
            () =>
            {
                image.classList.remove(
                    "scenePreviewImageHidden"
                );

                if (placeholder !== null)
                {
                    placeholder.style.display = "none";
                }
            };

        image.onerror =
            () =>
            {
                image.classList.add(
                    "scenePreviewImageHidden"
                );

                if (placeholder !== null)
                {
                    placeholder.textContent =
                        "No camera scene";
                    placeholder.style.display = "flex";
                }
            };

        image.src =
            "/preview.jpg?scene=" +
            Date.now();
    }
}
