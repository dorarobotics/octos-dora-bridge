from __future__ import annotations

from .depth_geometry import CameraIntrinsics, filter_detections
from .types import Object3D, TargetSpec


class ObjectPerceptionPipeline:
    def __init__(self, detector) -> None:
        self.detector = detector

    def detect(
        self,
        *,
        color_bgr,
        depth_m,
        intrinsics: CameraIntrinsics,
        target: TargetSpec,
    ) -> list[Object3D]:
        if hasattr(self.detector, "detect_3d"):
            return self.detector.detect_3d(
                color_bgr=color_bgr,
                depth_m=depth_m,
                intrinsics=intrinsics,
                target=target,
            )
        detections = self.detector.detect(color_bgr, target)
        return filter_detections(detections, depth_m, intrinsics, target)
