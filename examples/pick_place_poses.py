"""Pure pose math for the UR5e pick-and-place sequence (unit-tested).

Kept separate from the HTTP driver so the geometry is testable without a bridge.
All poses are SPEC poses: {"position":[x,y,z], "orientation":[qx,qy,qz,qw]}.
Top-down grasp = 180° about world X = quaternion [1,0,0,0] (gripper points -Z).
"""
from __future__ import annotations

from typing import Any

# 180° about X (xyzw): gripper approach axis points straight down.
TOP_DOWN = [1.0, 0.0, 0.0, 0.0]


def top_down_pose(x: float, y: float, z: float) -> dict[str, Any]:
    return {"position": [round(x, 5), round(y, 5), round(z, 5)], "orientation": list(TOP_DOWN)}


def build_pick_place(
    *,
    ball_xy: tuple[float, float],
    place_xy: tuple[float, float],
    approach_z: float,
    grasp_z: float,
    place_z: float | None = None,
) -> list[dict[str, Any]]:
    """Return the ordered pick-and-place steps.

    Each step is {"label", "verb", "args"} ready to POST to the bridge. The
    sequence: home → open → above-ball → at-ball → close → lift → above-place →
    at-place → open → lift → home. grasp/approach use top-down orientation.
    """
    bx, by = ball_xy
    px, py = place_xy
    place_z = grasp_z if place_z is None else place_z
    G = "vendor.moveit.arm.gripper.set"
    P = "vendor.moveit.arm.move_to_pose"
    cs = {"control_source": "pickplace"}

    def pose_step(label: str, x: float, y: float, z: float) -> dict[str, Any]:
        return {"label": label, "verb": P, "args": {"pose": top_down_pose(x, y, z), **cs}}

    def grip(label: str, width: float) -> dict[str, Any]:
        return {"label": label, "verb": G, "args": {"width": width}}

    return [
        {"label": "home", "verb": "vendor.moveit.arm.move_to_named", "args": {"name": "home", **cs}},
        grip("open gripper", 0.085),
        pose_step("above ball", bx, by, approach_z),
        pose_step("descend to ball", bx, by, grasp_z),
        grip("close on ball", 0.0),
        pose_step("lift", bx, by, approach_z),
        pose_step("above place", px, py, approach_z),
        pose_step("descend to place", px, py, place_z),
        grip("release", 0.085),
        pose_step("retract", px, py, approach_z),
        {"label": "home", "verb": "vendor.moveit.arm.move_to_named", "args": {"name": "home", **cs}},
    ]
