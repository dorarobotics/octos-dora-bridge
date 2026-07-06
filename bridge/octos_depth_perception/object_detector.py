from __future__ import annotations

from .color_detector import detect_colored_objects
from .depth_geometry import CameraIntrinsics, Object3D, SizeRange, filter_detections


def detect_objects_rgbd(
    color_bgr,
    depth_m,
    intrinsics: CameraIntrinsics,
    *,
    category: str | None = "cube",
    color: str | None = None,
    size_range: SizeRange | None = None,
    min_depth_m: float = 0.05,
    max_depth_m: float = 2.0,
) -> list[Object3D]:
    colors = [color] if color else None
    detections = detect_colored_objects(
        color_bgr,
        colors=colors,
        category=category or "object",
    )
    return filter_detections(
        detections,
        depth_m,
        intrinsics,
        category=category,
        color=color,
        size_range=size_range,
        min_depth_m=min_depth_m,
        max_depth_m=max_depth_m,
    )
