from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from .types import Detection2D, Object3D, SizeEstimate, SizeRange, TargetSpec


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class DepthSample:
    depth_m: float
    valid_count: int
    total_count: int

    @property
    def valid_ratio(self) -> float:
        if self.total_count <= 0:
            return 0.0
        return self.valid_count / self.total_count


def depth_mask_centroid_camera(
    depth_m: np.ndarray,
    mask: np.ndarray,
    intrinsics: CameraIntrinsics,
    *,
    min_depth_m: float = 0.05,
    max_depth_m: float = 2.0,
) -> tuple[tuple[float, float, float], int, int]:
    if depth_m.ndim != 2:
        raise ValueError("depth_m must be a 2D array of meters")
    if mask.shape[:2] != depth_m.shape:
        raise ValueError("mask shape must match depth_m shape")

    object_pixels = mask.astype(bool)
    total_count = int(np.count_nonzero(object_pixels))
    if total_count == 0:
        raise ValueError("object mask is empty")

    valid = object_pixels & np.isfinite(depth_m) & (depth_m >= min_depth_m) & (depth_m <= max_depth_m)
    valid_count = int(np.count_nonzero(valid))
    if valid_count == 0:
        raise ValueError("no valid depth samples inside object mask")
    valid = _top_surface_valid_mask(depth_m, valid)
    valid_count = int(np.count_nonzero(valid))

    vv, uu = np.nonzero(valid)
    zz = depth_m[valid].astype(float)
    xx = (uu.astype(float) - intrinsics.cx) * zz / intrinsics.fx
    yy = (vv.astype(float) - intrinsics.cy) * zz / intrinsics.fy
    return (
        (round(float(np.mean(xx)), 6), round(float(np.mean(yy)), 6), round(float(np.mean(zz)), 6)),
        valid_count,
        total_count,
    )


def _top_surface_valid_mask(depth_m: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    depths = depth_m[valid_mask].astype(float)
    if depths.size < 16:
        return valid_mask
    near_depth = float(np.percentile(depths, 35))
    band_m = max(0.006, float(np.std(depths)) * 0.75)
    top_mask = valid_mask & (depth_m.astype(float) <= near_depth + band_m)
    if np.count_nonzero(top_mask) < max(8, int(depths.size * 0.15)):
        return valid_mask
    return top_mask


def robust_depth_m(
    depth_m: np.ndarray,
    bbox: Sequence[int],
    *,
    center_fraction: float = 0.5,
    min_depth_m: float = 0.05,
    max_depth_m: float = 2.0,
) -> DepthSample:
    if depth_m.ndim != 2:
        raise ValueError("depth_m must be a 2D array of meters")

    x, y, w, h = [int(v) for v in bbox]
    if w <= 0 or h <= 0:
        raise ValueError("bbox width and height must be positive")

    frac = min(max(float(center_fraction), 0.05), 1.0)
    crop_w = max(1, int(round(w * frac)))
    crop_h = max(1, int(round(h * frac)))
    x0 = x + (w - crop_w) // 2
    y0 = y + (h - crop_h) // 2
    x1 = x0 + crop_w
    y1 = y0 + crop_h
    x0 = max(0, min(depth_m.shape[1], x0))
    x1 = max(0, min(depth_m.shape[1], x1))
    y0 = max(0, min(depth_m.shape[0], y0))
    y1 = max(0, min(depth_m.shape[0], y1))

    patch = depth_m[y0:y1, x0:x1]
    total_count = int(patch.size)
    if total_count == 0:
        raise ValueError("bbox does not overlap depth image")

    valid = patch[np.isfinite(patch)]
    valid = valid[(valid >= min_depth_m) & (valid <= max_depth_m)]
    if valid.size == 0:
        raise ValueError("no valid depth samples inside detection bbox")

    return DepthSample(
        depth_m=round(float(np.median(valid)), 6),
        valid_count=int(valid.size),
        total_count=total_count,
    )


def project_pixel_to_camera(
    *,
    u: float,
    v: float,
    depth_m: float,
    intrinsics: CameraIntrinsics,
) -> tuple[float, float, float]:
    return (
        round((float(u) - intrinsics.cx) * float(depth_m) / intrinsics.fx, 6),
        round((float(v) - intrinsics.cy) * float(depth_m) / intrinsics.fy, 6),
        round(float(depth_m), 6),
    )


def estimate_metric_size(
    bbox: Sequence[int],
    depth_m: float,
    intrinsics: CameraIntrinsics,
) -> SizeEstimate:
    _, _, w, h = [float(v) for v in bbox]
    return SizeEstimate(
        width=round(w * float(depth_m) / intrinsics.fx, 6),
        height=round(h * float(depth_m) / intrinsics.fy, 6),
    )


def estimate_mask_metric_size(
    depth_m: np.ndarray,
    mask: np.ndarray,
    intrinsics: CameraIntrinsics,
    *,
    min_depth_m: float = 0.05,
    max_depth_m: float = 2.0,
) -> SizeEstimate:
    if depth_m.ndim != 2:
        raise ValueError("depth_m must be a 2D array of meters")
    if mask.shape[:2] != depth_m.shape:
        raise ValueError("mask shape must match depth_m shape")

    object_pixels = mask.astype(bool)
    valid = object_pixels & np.isfinite(depth_m) & (depth_m >= min_depth_m) & (depth_m <= max_depth_m)
    valid = _top_surface_valid_mask(depth_m, valid)
    if not np.any(valid):
        raise ValueError("no valid depth samples inside object mask")

    vv, uu = np.nonzero(valid)
    zz = depth_m[valid].astype(float)
    xx = (uu.astype(float) - intrinsics.cx) * zz / intrinsics.fx
    yy = (vv.astype(float) - intrinsics.cy) * zz / intrinsics.fy
    points = np.column_stack([xx, yy, zz])
    center = np.mean(points, axis=0)
    _, _, vh = np.linalg.svd(points - center, full_matrices=False)
    axes = vh[:2]
    coords = (points - center) @ axes.T
    pixel_size = float(np.median(zz)) / max(float(intrinsics.fx), float(intrinsics.fy))
    try:
        import cv2

        (_, _), (rect_w, rect_h), _ = cv2.minAreaRect(coords.astype(np.float32))
        extents = np.array([float(rect_w), float(rect_h)])
    except Exception:
        extents = np.ptp(coords, axis=0)
    extents = np.sort(extents + pixel_size)[::-1]
    return SizeEstimate(
        width=round(float(extents[0]), 6),
        height=round(float(extents[1]), 6),
    )


def enrich_detection_with_depth(
    detection: Detection2D,
    depth_m: np.ndarray,
    intrinsics: CameraIntrinsics,
    target: TargetSpec,
    *,
    min_valid_ratio: float | None = None,
) -> Object3D:
    min_valid_ratio = target.min_valid_ratio if min_valid_ratio is None else float(min_valid_ratio)
    geometry_source = "bbox_center_depth"
    point_camera: tuple[float, float, float] | None = None
    sample = robust_depth_m(
        depth_m,
        detection.bbox,
        min_depth_m=target.min_depth_m,
        max_depth_m=target.max_depth_m,
    )
    if detection.mask is not None:
        try:
            point_camera, valid_count, total_count = depth_mask_centroid_camera(
                depth_m,
                detection.mask,
                intrinsics,
                min_depth_m=target.min_depth_m,
                max_depth_m=target.max_depth_m,
            )
            sample = DepthSample(
                depth_m=point_camera[2],
                valid_count=valid_count,
                total_count=total_count,
            )
            geometry_source = "mask_point_cloud_centroid"
        except ValueError:
            point_camera = None
    estimated_size = estimate_metric_size(detection.bbox, sample.depth_m, intrinsics)
    if detection.mask is not None:
        try:
            estimated_size = estimate_mask_metric_size(
                depth_m,
                detection.mask,
                intrinsics,
                min_depth_m=target.min_depth_m,
                max_depth_m=target.max_depth_m,
            )
        except ValueError:
            pass

    if sample.valid_ratio < min_valid_ratio:
        raise ValueError(f"depth valid ratio {sample.valid_ratio:.2f} below threshold {min_valid_ratio:.2f}")

    if point_camera is None:
        u, v = detection.center
        point_camera = project_pixel_to_camera(
            u=u,
            v=v,
            depth_m=sample.depth_m,
            intrinsics=intrinsics,
        )

    return Object3D(
        category=detection.category,
        color=detection.color,
        bbox=detection.bbox,
        confidence=detection.confidence,
        distance_m=sample.depth_m,
        point_camera=point_camera,
        estimated_size_m=estimated_size,
        depth_valid_ratio=round(sample.valid_ratio, 6),
        geometry_source=geometry_source,
    )


def filter_detections(
    detections: Iterable[Detection2D],
    depth_m: np.ndarray,
    intrinsics: CameraIntrinsics,
    target: TargetSpec,
) -> list[Object3D]:
    matches: list[Object3D] = []
    for detection in detections:
        if target.category and detection.category != target.category:
            continue
        if target.color and detection.color != target.color:
            continue
        try:
            obj = enrich_detection_with_depth(detection, depth_m, intrinsics, target)
        except ValueError:
            continue
        if target.size_range_m and not target.size_range_m.contains(obj.estimated_size_m):
            continue
        matches.append(obj)
    return sorted(matches, key=lambda obj: (obj.confidence, obj.depth_valid_ratio), reverse=True)
