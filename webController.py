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

from datetime import datetime
from datetime import timezone
import os
import psutil


@dataclass
class WebServices:
    config: CamConfig
    capture: CamCapture
    preview_server: PreviewServer
    buffer_manager: BufferManager
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

        services.event_log.add(
            message
        )

        status = (
            services.buffer_manager.get_status()
        )

        return jsonify(
            {
                "success": success,
                "implemented": True,
                "message": message,
                "status": status
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

        services.event_log.add(
            message
        )

        status = (
            services.buffer_manager.get_status()
        )

        return jsonify(
            {
                "success": success,
                "implemented": True,
                "message": message,
                "status": status
            }
        )

    @app.route(
        "/buffer_capture",
        methods=["POST"]
    )
    def buffer_capture():
        success, message, capture_status = (
            services.buffer_manager.capture()
        )

        if success:
            services.event_log.add(
                (
                    f"Capture saved: "
                    f"{capture_status['frames_written']} frames, "
                    f"{capture_status['duration_seconds']:.2f} sec, "
                    f"seq {capture_status['first_sequence_number']}-"
                    f"{capture_status['last_sequence_number']}, "
                    f"{capture_status['first_timestamp_utc']} to "
                    f"{capture_status['last_timestamp_utc']}, "
                    f"{capture_status.get('output_file', '')}"
                )
            )
        else:
            services.event_log.add(
                message,
                "error"
            )

        return jsonify(
            {
                "success": success,
                "implemented": True,
                "message": message,
                "capture_status": capture_status
            }
        )
    @app.route(
        "/buffer_clear",
        methods=["POST"]
    )
    def buffer_clear():
        success, message = (
            services.buffer_manager.clear()
        )

        services.event_log.add(
            message
        )

        return jsonify(
            {
                "success": success,
                "implemented": True,
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
            {
                "success": True,
                "implemented": True,
                "message": "Buffer status updated",
                **status
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

    @app.route(
        "/system_status"
    )
    def system_status():
        process = psutil.Process(
            os.getpid()
        )

        memory_mb = (
            process.memory_info().rss /
            (1024 * 1024)
        )

        buffer_status = (
            services.buffer_manager.get_status()
        )

        return jsonify(
            {
                "success": True,

                "server_time_utc": datetime.now(
                    timezone.utc
                ).strftime(
                    "%H:%M:%S"
                ),

                "preview_running":
                    services.preview_server.is_running(),

                "buffer_running":
                    buffer_status["running"],

                "trigger_enabled":
                    buffer_status["running"],

                "camera_name":
                    services.config.camera_name,

                "camera_format":
                    services.config.input_format.upper(),

                "camera_frame_width_pixels":
                    services.config.frame_width_pixels,

                "camera_frame_height_pixels":
                    services.config.frame_height_pixels,

                "camera_target_fps":
                    services.config.frame_rate_fps,

                "camera_geometry":
                {
                    "latitude_degrees":
                        services.config.camera_latitude_degrees,

                    "longitude_degrees":
                        services.config.camera_longitude_degrees,

                    "bearing_degrees":
                        services.config.camera_bearing_degrees,

                    "hfov_degrees":
                        services.config.camera_hfov_degrees,

                    "vfov_degrees":
                        services.config.camera_vfov_degrees
                },

                "camera_fps":
                    buffer_status["estimated_fps"],

                "camera_frames":
                    buffer_status["frame_count"],

                "buffer_count":
                    buffer_status["buffer_count"],

                "buffer_capacity":
                    buffer_status["buffer_capacity"],

                "buffer_full":
                    buffer_status["buffer_full"],

                "failed_read_count":
                    buffer_status["failed_read_count"],

                "memory_mb":
                    memory_mb,

                "last_error":
                    buffer_status["last_error"]
            }
        )     

    @app.route(
        "/metrics_history"
    )
    def metrics_history():
        metrics = (
            services.buffer_manager.get_metrics_history()
        )

        return jsonify(
            {
                "success": True,
                "count": len(
                    metrics
                ),
                "metrics": metrics
            }
        )    
    
    def hls_file(
        filename: str
    ):
        return send_from_directory(
            services.config.hls_directory,
            filename
        )