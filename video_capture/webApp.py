"""
@file webApp.py

@brief Creates and wires together the Flask web application and capture services.

This file is the startup/assembly point for the Pi Camera Capture web
application.

For a Python developer who has not previously served web pages, Flask is a
small Python web framework. A Flask application object receives HTTP requests
from a browser and dispatches each request to a Python function associated
with a URL such as "/", "/system_status", or "/captures". Those URL-to-function
mappings are registered in webController.py.

create_app() builds the application's non-web components first: configuration,
logging, capture management, camera capture, preview handling, triggering, and
the rolling camera buffer. It then creates the Flask object and passes it,
along with those service objects, to register_routes(). After that,
webController.py can answer browser requests by calling into the already
constructed camera/capture services.

In other words, this file does not contain most of the web-page behavior.
Its job is to assemble the application, start the camera pipeline, and connect
the Flask web server to the rest of the program.
"""


from flask import Flask
from pathlib import Path
from datetime import datetime
from datetime import timezone

from video_capture.trigger_manager import TriggerManager
from video_capture.cam_config import CamConfig
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

# ## Construct the complete Pi Camera Capture application and return the Flask server object.
def create_app() -> Flask:
    config = CamConfig()

    config.application_start_utc = (
        datetime.now(
            timezone.utc
        ).isoformat(
            timespec="milliseconds"
        ).replace(
            "+00:00",
            "Z"
        )
    )

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

    # Construct the service objects that contain the application's actual work.
    # Flask routes will later call these objects in response to browser requests.
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
        config
    )

    buffer_manager = BufferManager(
        config,
        trigger_manager,
        event_log,
        capture_manager
    )

    # Start the continuous camera-reader/buffering pipeline before the web UI
    # begins answering status and preview requests.
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

    # Bundle the service objects into one container. webController passes this
    # bundle to route handlers instead of relying on global variables.
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