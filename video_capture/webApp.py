from flask import Flask
from pathlib import Path

from trigger_manager import TriggerManager
from common.candidate_config import CANDIDATE_CONFIG
from video_capture.buffer_manager import BufferManager
from video_capture.cam_capture import CamCapture
from video_capture.cam_config import CamConfig
from video_capture.event_log import EventLog
from video_capture.previewServer import PreviewServer
from video_capture.webController import WebServices
from video_capture.webController import register_routes
from video_capture.capture_manager import CaptureManager
import logging
import atexit


def create_app() -> Flask:
    config = CamConfig()

    log = logging.getLogger("werkzeug")

    log.setLevel(logging.ERROR)

    event_log = EventLog(
        config
    )
    event_log.add(
        "*************\nStarting video manager\n*************\n\n"
    )

    if Path(config.video_device).exists():
        event_log.add(
            f"Camera detected: {config.video_device}"
        )
    else:
        event_log.add(
            f"ERROR: Camera not detected: {config.video_device}",
            "error"
        )

    #TODO - This does not work yet because event manager writes in background.
    atexit.register(
        lambda: event_log.add(
            "*************\nVideo Manager Normal shutdown\n*************\n\n"
        )
    )

    capture_manager = CaptureManager(
        config,
        event_log
    )

    capture = CamCapture(
        config
    )

    preview_server = PreviewServer(
        config
    )

    trigger_manager = TriggerManager(
        CANDIDATE_CONFIG
    
    )

    buffer_manager = BufferManager(
        config,
        trigger_manager,
        event_log,
        capture_manager
    )

    success, message = (
        buffer_manager.start()
    )

    if success:
        event_log.add(
            "Buffer Manager started"
        )
    else:
        event_log.add(
            f"Buffer Manager start failed: {message}",
            "error"
        )

    services = WebServices(
        config=config,
        capture=capture,
        preview_server=preview_server,
        buffer_manager=buffer_manager,
        trigger_manager=trigger_manager,
        capture_manager=capture_manager,
        event_log=event_log
    )

    event_log.add(
        "Web services initialized"
    )

    app = Flask(
        __name__
    )

    register_routes(
        app,
        services
    )

    event_log.add(
        "Application started"
    )

    event_log.add(
        message
    )

    return app