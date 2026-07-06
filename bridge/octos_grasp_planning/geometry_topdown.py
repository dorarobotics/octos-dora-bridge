from __future__ import annotations

from octos_object_perception.types import Object3D

from .types import GraspCandidate


IDENTITY_ROTATION = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def table_safe_top_z(
    table_z: float,
    object_height_m: float,
    *,
    table_clearance_m: float = 0.04,
    top_bias_m: float = 0.006,
) -> float:
    top_z = float(table_z) + max(0.0, float(object_height_m)) - float(top_bias_m)
    clearance_z = float(table_z) + float(table_clearance_m)
    return round(max(clearance_z, top_z), 6)


def plan_topdown_grasp(
    obj: Object3D,
    *,
    table_z_camera: float | None = None,
    table_clearance_m: float = 0.015,
    top_bias_m: float = 0.006,
    width_margin_m: float = 0.005,
) -> GraspCandidate:
    x, y, z = [float(v) for v in obj.point_camera]
    top_z = z - float(top_bias_m)
    if table_z_camera is not None:
        min_z = float(table_z_camera) + float(table_clearance_m)
        top_z = max(top_z, min_z)
    width_m = max(0.0, float(obj.estimated_size_m.width) + float(width_margin_m))
    return GraspCandidate(
        position_camera=(round(x, 6), round(y, 6), round(top_z, 6)),
        rotation_camera=IDENTITY_ROTATION,
        width_m=round(width_m, 6),
        score=0.8,
        source="geometry_topdown",
    )
