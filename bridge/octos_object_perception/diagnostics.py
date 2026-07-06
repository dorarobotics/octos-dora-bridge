from __future__ import annotations

from dataclasses import asdict

from .depth_geometry import CameraIntrinsics, enrich_detection_with_depth
from .detectors.color_size_detector import HSV_RANGES, ColorSizeDetector
from .types import Object3D, TargetSpec


def _target_summary(target: TargetSpec) -> dict:
    return {
        "category": target.category,
        "color": target.color,
    }


def _size_range_reason(obj: Object3D, target: TargetSpec) -> str | None:
    if target.size_range_m is None:
        return None
    if target.size_range_m.contains(obj.estimated_size_m):
        return None
    return "size_range"


def diagnose_color_size_frame(
    *,
    color_bgr,
    depth_m,
    intrinsics: CameraIntrinsics,
    target: TargetSpec,
    min_area_px: int = 120,
) -> dict:
    detector = ColorSizeDetector(min_area_px=min_area_px)
    all_target = TargetSpec(category=target.category, color=None)
    report = diagnose_detector_frame(
        detector=detector,
        color_bgr=color_bgr,
        depth_m=depth_m,
        intrinsics=intrinsics,
        target=target,
        detection_target=all_target,
    )
    report["summary"] = {
        color: report["summary"].get(color, {"detections_2d": 0, "matches": 0, "rejected": 0})
        for color in HSV_RANGES
    }
    return report


def diagnose_detector_frame(
    *,
    detector,
    color_bgr,
    depth_m,
    intrinsics: CameraIntrinsics,
    target: TargetSpec,
    detection_target: TargetSpec | None = None,
) -> dict:
    detection_target = detection_target or target
    detections = detector.detect(color_bgr, detection_target)
    summary = {}
    matches = []
    rejected = []

    for detection in detections:
        key = detection.color or detection.category or "unknown"
        if key not in summary:
            summary[key] = {"detections_2d": 0, "matches": 0, "rejected": 0}
        summary[key]["detections_2d"] += 1

        if target.color and detection.color != target.color:
            continue

        try:
            obj = enrich_detection_with_depth(detection, depth_m, intrinsics, target)
        except ValueError as exc:
            summary[key]["rejected"] += 1
            rejected.append({
                "color": detection.color,
                "category": detection.category,
                "bbox": list(detection.bbox),
                "reason": "depth",
                "detail": str(exc),
            })
            continue

        reason = _size_range_reason(obj, target)
        if reason:
            summary[key]["rejected"] += 1
            data = obj.to_dict()
            data["reason"] = reason
            rejected.append(data)
            continue

        summary[key]["matches"] += 1
        matches.append(obj.to_dict())

    return {
        "target": _target_summary(target),
        "size_range_m": asdict(target.size_range_m) if target.size_range_m else None,
        "summary": summary,
        "matches": sorted(matches, key=lambda item: (item["confidence"], item["depth_valid_ratio"]), reverse=True),
        "rejected": rejected,
    }
