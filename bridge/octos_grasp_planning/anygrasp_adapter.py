from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Sequence

import numpy as np

from octos_object_perception.depth_geometry import CameraIntrinsics
from octos_object_perception.types import Detection2D, TargetSpec

from .types import GraspCandidate


class AnyGraspUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class AnyGraspConfig:
    checkpoint_path: str | None = None
    max_gripper_width: float = 0.08
    gripper_height: float = 0.03
    top_down_grasp: bool = False
    debug: bool = False
    apply_object_mask: bool = True
    dense_grasp: bool = False
    collision_detection: bool = True
    bbox_margin_px: int = 8
    num_candidates: int = 20


def target_point_cloud(
    *,
    depth_m: np.ndarray,
    intrinsics: CameraIntrinsics,
    mask: np.ndarray | None = None,
    bbox: Sequence[int] | None = None,
    min_depth_m: float = 0.05,
    max_depth_m: float = 2.0,
    bbox_margin_px: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    if depth_m.ndim != 2:
        raise ValueError("depth_m must be a 2D array of meters")

    valid_mask = np.isfinite(depth_m) & (depth_m >= min_depth_m) & (depth_m <= max_depth_m)
    if mask is not None:
        if mask.shape[:2] != depth_m.shape:
            raise ValueError("mask shape must match depth_m shape")
        valid_mask &= mask.astype(bool)
    elif bbox is not None:
        x, y, w, h = [int(v) for v in bbox]
        if w <= 0 or h <= 0:
            raise ValueError("bbox width and height must be positive")
        margin = max(0, int(bbox_margin_px))
        x0 = max(0, x - margin)
        y0 = max(0, y - margin)
        x1 = min(depth_m.shape[1], x + w + margin)
        y1 = min(depth_m.shape[0], y + h + margin)
        crop_mask = np.zeros(depth_m.shape, dtype=bool)
        crop_mask[y0:y1, x0:x1] = True
        valid_mask &= crop_mask

    if not np.any(valid_mask):
        raise ValueError("no valid depth samples for AnyGrasp target")

    vv, uu = np.nonzero(valid_mask)
    zz = depth_m[valid_mask].astype(np.float32)
    xx = (uu.astype(np.float32) - float(intrinsics.cx)) * zz / float(intrinsics.fx)
    yy = (vv.astype(np.float32) - float(intrinsics.cy)) * zz / float(intrinsics.fy)
    points = np.stack([xx, yy, zz], axis=-1).astype(np.float32)
    return points, valid_mask


def _load_anygrasp_sdk():
    try:
        from gsnet import AnyGrasp
    except Exception as exc:
        raise AnyGraspUnavailableError(
            "AnyGrasp SDK is not installed or not on PYTHONPATH. Install "
            "https://github.com/graspnet/anygrasp_sdk with CUDA PyTorch, "
            "MinkowskiEngine, pointnet2, graspnetAPI/open3d, checkpoint, and license."
        ) from exc
    return AnyGrasp


def _build_anygrasp_backend(config: AnyGraspConfig):
    if not config.checkpoint_path:
        raise AnyGraspUnavailableError(
            "AnyGrasp checkpoint_path is required when grasp_planner='anygrasp'. "
            "Pass anygrasp_checkpoint_path or set ANYGRASP_CHECKPOINT_PATH."
        )
    AnyGrasp = _load_anygrasp_sdk()
    cfg = SimpleNamespace(
        checkpoint_path=config.checkpoint_path,
        max_gripper_width=max(0.0, min(0.1, float(config.max_gripper_width))),
        gripper_height=float(config.gripper_height),
        top_down_grasp=bool(config.top_down_grasp),
        debug=bool(config.debug),
    )
    backend = AnyGrasp(cfg)
    backend.load_net()
    return backend


def _workspace_limits(points: np.ndarray) -> list[float]:
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    pad = np.array([0.02, 0.02, 0.02], dtype=np.float32)
    lo = mins - pad
    hi = maxs + pad
    return [
        float(lo[0]),
        float(hi[0]),
        float(lo[1]),
        float(hi[1]),
        max(0.0, float(lo[2])),
        float(hi[2]),
    ]


def _candidate_attr(candidate: Any, *names: str):
    for name in names:
        if isinstance(candidate, dict) and name in candidate:
            return candidate[name]
        if hasattr(candidate, name):
            return getattr(candidate, name)
    raise ValueError(f"AnyGrasp candidate missing one of: {', '.join(names)}")


def _candidate_to_grasp(candidate: Any) -> GraspCandidate:
    position = np.asarray(_candidate_attr(candidate, "translation", "position"), dtype=float).reshape(3)
    rotation = np.asarray(_candidate_attr(candidate, "rotation_matrix", "rotation"), dtype=float).reshape(3, 3)
    width = float(_candidate_attr(candidate, "width", "grasp_width"))
    score = float(_candidate_attr(candidate, "score"))
    return GraspCandidate(
        position_camera=tuple(round(float(v), 6) for v in position),
        rotation_camera=tuple(tuple(round(float(v), 6) for v in row) for row in rotation),
        width_m=round(width, 6),
        score=round(score, 6),
        source="anygrasp",
    )


def _iter_candidates(raw_candidates: Any):
    if raw_candidates is None:
        return []
    if isinstance(raw_candidates, tuple):
        raw_candidates = raw_candidates[0]
    if hasattr(raw_candidates, "nms"):
        raw_candidates = raw_candidates.nms().sort_by_score()
    try:
        return list(raw_candidates)
    except TypeError:
        return [raw_candidates]


def _candidate_score(candidate: Any) -> float:
    try:
        return float(_candidate_attr(candidate, "score"))
    except ValueError:
        return 0.0


def plan_anygrasp(
    *,
    color_bgr: np.ndarray,
    depth_m: np.ndarray,
    intrinsics: CameraIntrinsics,
    detection: Detection2D,
    target: TargetSpec | None = None,
    config: AnyGraspConfig | None = None,
    backend: Any | None = None,
) -> GraspCandidate:
    config = config or AnyGraspConfig()
    target = target or TargetSpec()
    points, valid_mask = target_point_cloud(
        depth_m=depth_m,
        intrinsics=intrinsics,
        mask=detection.mask,
        bbox=detection.bbox,
        min_depth_m=target.min_depth_m,
        max_depth_m=target.max_depth_m,
        bbox_margin_px=config.bbox_margin_px,
    )
    colors = color_bgr[..., ::-1].astype(np.float32) / 255.0
    colors = colors[valid_mask].astype(np.float32)
    if colors.shape[0] != points.shape[0]:
        raise ValueError("color/depth target mask produced mismatched point count")

    backend = backend or _build_anygrasp_backend(config)
    lims = _workspace_limits(points)
    result = backend.get_grasp(
        points,
        colors,
        lims=lims,
        apply_object_mask=bool(config.apply_object_mask),
        dense_grasp=bool(config.dense_grasp),
        collision_detection=bool(config.collision_detection),
    )
    candidates = _iter_candidates(result)
    if not candidates:
        raise RuntimeError("AnyGrasp returned no grasp candidates for the selected target")

    candidates = sorted(candidates, key=_candidate_score, reverse=True)
    return _candidate_to_grasp(candidates[0])
