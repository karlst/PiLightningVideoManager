"""
@file webController.py

@brief Connects the Flask web server to the Pi Camera Capture application.

Flask serves web pages by mapping browser requests (URLs) to ordinary Python
functions called routes. register_routes() defines those mappings. A browser
request such as GET /system_status runs the matching Python function, which
reads application state from WebServices and returns HTML, JSON, an image, or
a capture file to the browser. POST routes work in the opposite direction:
they let buttons and controls on the web page ask the Python application to
perform actions such as enabling triggers, changing candidate settings, or
saving a capture.

WebServices is simply the collection of application objects that these route
functions need in order to talk to the rest of Pi Camera Capture.
"""


from dataclasses import dataclass

from flask import Flask
from flask import jsonify
from flask import make_response
from flask import render_template
from flask import send_from_directory
from flask import request

from video_capture.buffer_manager import BufferManager
from video_capture.cam_capture import CamCapture
from video_capture.cam_config import CamConfig
from video_capture.event_log import EventLog
from video_capture.previewServer import PreviewServer
from video_capture.trigger_manager import TriggerManager
from video_capture.capture_manager import CaptureManager

from datetime import datetime
from datetime import timezone
import os
import psutil

from pathlib import Path

from common.candidate_config import CANDIDATE_CONFIG
from common.system_config import load_system_settings
from common.system_config import set_save_filtered_false_positives


@dataclass
class WebServices:
    config: CamConfig
    capture: CamCapture
    preview_server: PreviewServer
    buffer_manager: BufferManager
    trigger_manager: TriggerManager
    capture_manager: CaptureManager
    event_log: EventLog

def get_chip_temperature_c() -> float | None:
    thermal_path = Path(
        "/sys/class/thermal/thermal_zone0/temp"
    )

    try:
        millidegrees_c = float(
            thermal_path.read_text(
                encoding="utf-8"
            ).strip()
        )

        return (
            millidegrees_c /
            1000.0
        )

    except Exception:
        return None

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
            "Capture once requested",
            event_type="capture",
            summary="Capture once requested"
        )

        return_code = (
            services.capture.capture_once()
        )

        success = (
            return_code == 0
        )

        if success:
            services.event_log.add(
                "Capture once completed",
                event_type="capture",
                summary="Capture once completed"
            )
        else:
            services.event_log.add(
                f"Capture once failed: return_code={return_code}",
                "error",
                event_type="error",
                summary="Capture once failed"
            )

        return jsonify(
            {
                "return_code": return_code,
                "success": success
            }
        )

    @app.route(
        "/preview.jpg"
    )
    def preview_jpg():
        jpeg_bytes, status = (
            services.buffer_manager.get_preview_jpeg()
        )

        if jpeg_bytes is None:
            return jsonify(
                status
            ), 404

        response = make_response(
            jpeg_bytes
        )

        response.headers.set(
            "Content-Type",
            "image/jpeg"
        )

        response.headers.set(
            "Cache-Control",
            "no-store, no-cache, must-revalidate, max-age=0"
        )

        response.headers.set(
            "Pragma",
            "no-cache"
        )

        response.headers.set(
            "X-Frame-Sequence",
            str(
                status["sequence_number"]
            )
        )

        response.headers.set(
            "X-Frame-Time-UTC",
            status["timestamp_utc"]
        )

        return response

    @app.route(
        "/preview_status"
    )
    def preview_status():
        buffer_status = (
            services.buffer_manager.get_status()
        )

        return jsonify(
            {
                "running": buffer_status["running"],
                "message": "Snapshot preview uses buffered frames"
            }
        )

    @app.route(
        "/trigger_enable",
        methods=["POST"]
    )
    def trigger_enable():
        success, message = (
            services.trigger_manager.enable()
        )

        services.event_log.add(
            message,
            event_type="trigger",
            summary=message
        )

        return jsonify(
            {
                "success": success,
                "message": message,
                "trigger_status":
                    services.trigger_manager.get_status()
            }
        )

    @app.route(
        "/trigger_disable",
        methods=["POST"]
    )
    def trigger_disable():
        success, message = (
            services.trigger_manager.disable()
        )

        services.event_log.add(
            message,
            event_type="trigger",
            summary=message
        )

        return jsonify(
            {
                "success": success,
                "message": message,
                "trigger_status":
                    services.trigger_manager.get_status()
            }
        )

    @app.route(
        "/trigger_status"
    )
    def trigger_status():
        return jsonify(
            {
                "success": True,
                **services.trigger_manager.get_status()
            }
        )

    @app.route(
        "/candidate_settings"
    )
    def candidate_settings():
        return jsonify(
            {
                "success": True,

                "default": {
                    "candidate_brightness_delta_threshold":
                        CANDIDATE_CONFIG.
                        candidate_brightness_delta_threshold,

                    "candidate_bright_pixel_delta_threshold":
                        CANDIDATE_CONFIG.
                        candidate_bright_pixel_delta_threshold,

                    "candidate_bright_pixel_fraction_threshold":
                        CANDIDATE_CONFIG.
                        candidate_bright_pixel_fraction_threshold
                },

                "active":
                    services.trigger_manager.
                    get_candidate_config_dict()
            }
        )


    @app.route(
        "/candidate_settings",
        methods=["POST"]
    )
    def update_candidate_settings():
        body = request.get_json(
            silent=True
        ) or {}

        # Simple user-facing path: High / Medium / Low sensitivity.
        if "sensitivity" in body:
            success, message = (
                services.trigger_manager.
                set_sensitivity(
                    str(
                        body[
                            "sensitivity"
                        ]
                    )
                )
            )

        else:
            # Preserve the existing advanced-threshold API.
            try:
                brightness_delta_threshold = float(
                    body[
                        "candidate_brightness_delta_threshold"
                    ]
                )

                bright_pixel_delta_threshold = float(
                    body[
                        "candidate_bright_pixel_delta_threshold"
                    ]
                )

                bright_pixel_fraction_threshold = float(
                    body[
                        "candidate_bright_pixel_fraction_threshold"
                    ]
                )

            except (
                KeyError,
                TypeError,
                ValueError
            ):
                return jsonify(
                    {
                        "success": False,
                        "message":
                            "Invalid candidate threshold value"
                    }
                ), 400

            success, message = (
                services.trigger_manager.
                set_candidate_thresholds(
                    brightness_delta_threshold,
                    bright_pixel_delta_threshold,
                    bright_pixel_fraction_threshold
                )
            )

        if success:
            services.event_log.add(
                message,
                event_type="config",
                summary="Candidate settings updated"
            )

        return jsonify(
            {
                "success": success,
                "message": message,
                "active":
                    services.trigger_manager.
                    get_candidate_config_dict()
            }
        ), (
            200
            if success
            else 400
        )


    @app.route(
        "/candidate_settings_reset",
        methods=["POST"]
    )
    def reset_candidate_settings():
        success, message = (
            services.trigger_manager.
            reset_candidate_config()
        )

        if success:
            services.event_log.add(
                message,
                event_type="config",
                summary=message
            )

        return jsonify(
            {
                "success": success,
                "message": message,
                "active":
                    services.trigger_manager.
                    get_candidate_config_dict()
            }
        )
    @app.route(
        "/system_settings"
    )
    def system_settings():
        try:
            settings = (
                load_system_settings()
            )
        except RuntimeError as error:
            return jsonify(
                {
                    "success": False,
                    "message": str(error)
                }
            ), 500

        return jsonify(
            {
                "success": True,
                "save_filtered_false_positives":
                    bool(
                        settings.get(
                            "save_filtered_false_positives",
                            False
                        )
                    )
            }
        )


    @app.route(
        "/system_settings",
        methods=["POST"]
    )
    def update_system_settings():
        body = request.get_json(
            silent=True
        ) or {}

        value = body.get(
            "save_filtered_false_positives"
        )

        if not isinstance(
            value,
            bool
        ):
            return jsonify(
                {
                    "success": False,
                    "message":
                        "save_filtered_false_positives must be true or false"
                }
            ), 400

        try:
            settings = (
                set_save_filtered_false_positives(
                    value
                )
            )
        except (
            OSError,
            RuntimeError
        ) as error:
            return jsonify(
                {
                    "success": False,
                    "message":
                        f"System settings update failed: {error}"
                }
            ), 500

        enabled = bool(
            settings[
                "save_filtered_false_positives"
            ]
        )

        message = (
            "Save filtered false positive candidates "
            + (
                "enabled"
                if enabled
                else "disabled"
            )
        )

        services.event_log.add(
            message,
            event_type="config",
            summary=message
        )

        return jsonify(
            {
                "success": True,
                "message": message,
                "save_filtered_false_positives":
                    enabled
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
            "Event log cleared",
            event_type="system",
            summary="Event log cleared"
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
            message,
            event_type="system",
            summary=message
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
            message,
            event_type="system",
            summary=message
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
                ),
                event_type="capture",
                summary=(
                    f"Capture saved, "
                    f"{capture_status['frames_written']} frames"
                )
            )
        else:
            services.event_log.add(
                message,
                "error",
                event_type="error",
                summary="Capture failed"
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
            message,
            event_type="system",
            summary=message
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

        trigger_status = (
            services.trigger_manager.get_status()
        )

        return jsonify(
            {
                "success": True,

                "app_version":
                    services.config.app_version,

                "application_start_utc":
                    services.config.application_start_utc,

                "server_time_utc": datetime.now(
                    timezone.utc
                ).strftime(
                    "%H:%M:%S"
                ),

                "preview_running":
                    buffer_status["running"],

                "buffer_running":
                    buffer_status["running"],

                "trigger_enabled":
                    trigger_status["enabled"],

                "trigger_status":
                    trigger_status,

                "camera_name":
                    services.config.camera_name,

                "camera_type":
                    services.config.camera_type,

                "camera_format":
                    services.config.input_format.upper(),

                "camera_frame_width_pixels":
                    services.config.frame_width_pixels,

                "camera_frame_height_pixels":
                    services.config.frame_height_pixels,

                "camera_target_fps":
                    services.config.frame_rate_fps,

                "camera_preview_refresh_seconds":
                    services.config.camera_preview_refresh_seconds,

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

                "chip_temperature_c":
                    get_chip_temperature_c(),

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
    
    @app.route("/captures")
    def captures():
        files = (
            services.capture_manager.list_captures()
        )

        return jsonify(
            {
                "success": True,
                "files": files
            }
        )

    @app.route("/capture_files/<path:filename>")
    def capture_file(filename: str):
        return send_from_directory(
            services.capture_manager.get_capture_directory(),
            filename
        )