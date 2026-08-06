"use strict";

export class TriggerManager
{
    constructor()
    {
        this._enabled =
            true;
    }


    initialize()
    {
        this._bindClick(
            "trigger-disable-button",
            () => this.disableTrigger()
        );

        this._bindClick(
            "trigger-enable-button",
            () => this.enableTrigger()
        );

        this._updateUi();
    }


    enableTrigger()
    {
        this._enabled =
            true;

        this._updateUi();
    }


    disableTrigger()
    {
        this._enabled =
            false;

        this._updateUi();
    }


    isEnabled()
    {
        return this._enabled;
    }


    _updateUi()
    {
        const triggerStatus =
            document.getElementById(
                "trigger-enabled-text"
            );

        const enableButton =
            document.getElementById(
                "trigger-enable-button"
            );

        const disableButton =
            document.getElementById(
                "trigger-disable-button"
            );

        if (triggerStatus !== null)
        {
            triggerStatus.textContent =
                this._enabled
                    ? "Trigger: Enabled"
                    : "Trigger: Disabled";
        }

        if (enableButton !== null)
        {
            enableButton.classList.toggle(
                "cameraImageHidden",
                this._enabled
            );
        }

        if (disableButton !== null)
        {
            disableButton.classList.toggle(
                "cameraImageHidden",
                !this._enabled
            );
        }
    }


    _bindClick(elementId, handler)
    {
        const element =
            document.getElementById(
                elementId
            );

        if (element !== null)
        {
            element.addEventListener(
                "click",
                handler
            );
        }
    }
}