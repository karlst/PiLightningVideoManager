from dataclasses import dataclass

from flask import Flask
from flask import jsonify
from flask import render_template
from flask import send_from_directory

from buffer_manager import BufferManager
from cam_capture import CamCapture
from cam_config import CamConfig
from event_log import EventLog
from previewServer import PreviewServer
from display_preview import DisplayPreview


@dataclass
class WebServices:
    config: CamConfig
    capture: CamCapture
    preview_server: PreviewServer
    buffer_manager: BufferManager
    display_preview: DisplayPreview
    event_log: EventLog


def register_routes(
    app: Flask,
    services: WebServices
) -> None:

    @app.route("/")
    def index() -> str:
        return render_template(
            "index.html"
        )

    @app.route(
        "/capture_once",
        methods=["POST"]
    )
    def capture_once():
        services.event_log.add(
            "Capture once requested"
        )

        return_code = (
            services.capture.capture_once()
        )

        success = (
            return_code == 0
        )

        if success:
            services.event_log.add(
                "Capture once completed"
            )
        else:
            services.event_log.add(
                f"Capture once failed: return_code={return_code}",
                "error"
            )

        return jsonify(
            {
                "return_code": return_code,
                "success": success
            }
        )

    
    
    @app.route(
        "/preview_start",
        methods=["POST"]
    )
    def preview_start():
        success, message = (
            services.preview_server.start()
        )

        services.event_log.add(
            message
        )

        return jsonify(
            {
                "success": success,
                "message": message
            }
        )

    @app.route(
        "/preview_stop",
        methods=["POST"]
    )
    def preview_stop():
        success, message = (
            services.preview_server.stop()
        )

        services.event_log.add(
            message
        )

        return jsonify(
            {
                "success": success,
                "message": message
            }
        )

    @app.route(
        "/preview_status"
    )
    def preview_status():
        running = (
            services.preview_server.is_running()
        )

        return jsonify(
            {
                "running": running
            }
        )

    @app.route(
        "/event_log"
    )
    def event_log():
        return jsonify(
            {
                "entries":
                    services.event_log.snapshot()
            }
        )

    @app.route(
        "/event_log_clear",
        methods=["POST"]
    )
    def event_log_clear():
        services.event_log.clear()

        services.event_log.add(
            "Event log cleared"
        )

        return jsonify(
            {
                "success": True,
                "message": "Event log cleared"
            }
        )

    @app.route(
        "/buffer_start",
        methods=["POST"]
    )
    def buffer_start():
        success, message = (
            services.buffer_manager.start()
        )

        return jsonify(
            {
                "success": success,
                "implemented": True,
                "running":
                    services.buffer_manager.is_running(),
                "message": message
            }
        )

    @app.route(
        "/buffer_stop",
        methods=["POST"]
    )
    def buffer_stop():
        success, message = (
            services.buffer_manager.stop()
        )

        return jsonify(
            {
                "success": success,
                "implemented": True,
                "running":
                    services.buffer_manager.is_running(),
                "message": message
            }
        )

    @app.route(
        "/buffer_capture",
        methods=["POST"]
    )
    def buffer_capture():
        success, message = (
            services.buffer_manager.capture()
        )

        return jsonify(
            {
                "success": success,
                "implemented": False,
                "message": message
            }
        )

    @app.route(
        "/buffer_status"
    )
    def buffer_status():
        status = (
            services.buffer_manager.get_status()
        )

        return jsonify(
            status
        )

    @app.route(
        "/buffer_clear",
        methods=["POST"]
    )
    def buffer_clear():
        success, message = (
            services.buffer_manager.clear()
        )

        return jsonify(
            {
                "success": success,
                "implemented": True,
                "message": message
            }
        )

    
    @app.route(
        "/display_preview_start",
        methods=["POST"]  
    )

    def display_preview_start():
        success, message = (
            services.display_preview.start()
        )

        services.event_log.add(
            message
        )

        return jsonify(
            {
                "success": success,
                "message": message
            }
        )


    @app.route(
        "/display_preview_stop",
        methods=["POST"]
    )
    def display_preview_stop():
        success, message = (
            services.display_preview.stop()
        )

        services.event_log.add(
            message
        )

        return jsonify(
            {
                "success": success,
                "message": message
            }
        )
    
    @app.route(
        "/hls/<path:filename>"
    )
    def hls_file(
        filename: str
    ):
        return send_from_directory(
            services.config.hls_directory,
            filename
        )