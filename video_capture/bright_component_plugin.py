"""
Frame analyzer plugin for OpenCV bright/local-contrast components.
"""

from bright_component_analyzer import BrightComponentAnalyzer
from video_capture.cam_config import CamConfig
from video_capture.camera_reader import CameraFrame


# ## Adds connected-component geometry metrics to frame analysis.
class BrightComponentPlugin:

    # ## Create the shared component analyzer.
    def __init__(
        self,
        config: CamConfig
    ) -> None:
        self._analyzer = BrightComponentAnalyzer(
            config
        )

    # ## Analyze one camera frame and return component metrics.
    def analyze(
        self,
        camera_frame: CameraFrame
    ) -> dict:
        result = self._analyzer.analyze_camera_frame(
            camera_frame
        )

        return result
