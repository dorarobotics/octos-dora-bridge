from __future__ import annotations

from dataclasses import dataclass

from .types import GraspCandidate


@dataclass(frozen=True)
class RobotGraspLimits:
    max_width_m: float
    min_table_clearance_m: float = 0.015


def validate_grasp_candidate(
    candidate: GraspCandidate,
    limits: RobotGraspLimits,
    *,
    table_z_camera: float | None = None,
) -> GraspCandidate:
    if candidate.width_m > limits.max_width_m:
        raise ValueError(
            f"gripper width {candidate.width_m:.3f} exceeds max {limits.max_width_m:.3f}"
        )
    if table_z_camera is not None:
        min_z = float(table_z_camera) + float(limits.min_table_clearance_m)
        if candidate.position_camera[2] < min_z:
            raise ValueError(
                f"grasp z {candidate.position_camera[2]:.3f} below table clearance {min_z:.3f}"
            )
    return candidate
