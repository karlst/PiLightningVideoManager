from flask import Flask

from buffer_manager import BufferManager
from cam_capture import CamCapture
from cam_config import CamConfig
from event_log import EventLog
from previewServer import PreviewServer
from webController import WebServices
from webController import register_routes


def create_app() -> Flask:
    config = CamConfig()

    event_log = EventLog(
        max_entries=200
    )

    capture = CamCapture(
        config
    )

    preview_server = PreviewServer(
        config
    )

    buffer_manager = BufferManager(
        config=config,
        event_log=event_log
    )

    services = WebServices(
        config=config,
        capture=capture,
        preview_server=preview_server,
        buffer_manager=buffer_manager,
        event_log=event_log
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

    return app