"""Shared RGB-D object perception helpers for Octos robot skills."""

from .depth_geometry import (
    CameraIntrinsics,
    DepthSample,
    Detection2D,
    Object3D,
    SizeEstimate,
    SizeRange,
    enrich_detection_with_depth,
    filter_detections,
    project_pixel_to_camera,
    robust_depth_m,
)

__all__ = [
    "CameraIntrinsics",
    "DepthSample",
    "Detection2D",
    "Object3D",
    "SizeEstimate",
    "SizeRange",
    "enrich_detection_with_depth",
    "filter_detections",
    "project_pixel_to_camera",
    "robust_depth_m",
]
