import pytest
import numpy as np

from octos_grasp_planning.anygrasp_adapter import (
    AnyGraspUnavailableError,
    _load_anygrasp_sdk,
    plan_anygrasp,
    target_point_cloud,
)
from octos_grasp_planning.filters import RobotGraspLimits, validate_grasp_candidate
from octos_grasp_planning.geometry_topdown import plan_topdown_grasp, table_safe_top_z
from octos_object_perception.depth_geometry import CameraIntrinsics
from octos_object_perception.types import Detection2D, Object3D, SizeEstimate


def make_object(width=0.04, height=0.04):
    return Object3D(
        category="cube",
        color="yellow",
        bbox=(40, 30, 40, 40),
        confidence=0.9,
        distance_m=0.3,
        point_camera=(0.10, -0.02, 0.30),
        estimated_size_m=SizeEstimate(width=width, height=height),
        depth_valid_ratio=0.95,
        geometry_source="mask_point_cloud_centroid",
    )


def test_plan_topdown_grasp_uses_upper_half_and_open_width_margin():
    candidate = plan_topdown_grasp(
        make_object(width=0.04, height=0.04),
        table_z_camera=0.26,
        table_clearance_m=0.015,
        width_margin_m=0.005,
    )

    assert candidate.position_camera == (0.10, -0.02, 0.294)
    assert candidate.width_m == 0.045
    assert candidate.source == "geometry_topdown"
    assert candidate.score == 0.8
    assert candidate.rotation_camera == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def test_validate_grasp_candidate_rejects_excessive_width():
    candidate = plan_topdown_grasp(make_object(width=0.08), width_margin_m=0.005)

    with pytest.raises(ValueError, match="gripper width"):
        validate_grasp_candidate(candidate, RobotGraspLimits(max_width_m=0.06))


def test_validate_grasp_candidate_rejects_below_table_clearance():
    candidate = plan_topdown_grasp(make_object(height=0.01), table_z_camera=None)

    with pytest.raises(ValueError, match="table clearance"):
        validate_grasp_candidate(
            candidate,
            RobotGraspLimits(max_width_m=0.06, min_table_clearance_m=0.02),
            table_z_camera=0.295,
        )


def test_table_safe_top_z_prefers_object_top_but_never_below_clearance():
    assert table_safe_top_z(-0.15, 0.08, table_clearance_m=0.04, top_bias_m=0.006) == -0.076
    assert table_safe_top_z(-0.15, 0.02, table_clearance_m=0.04, top_bias_m=0.006) == -0.11


def test_target_point_cloud_crops_to_detection_mask():
    depth_m = np.full((4, 4), 0.5, dtype=np.float32)
    mask = np.zeros((4, 4), dtype=np.uint8)
    mask[1:3, 1:3] = 255
    intrinsics = CameraIntrinsics(fx=100.0, fy=100.0, cx=1.0, cy=1.0, width=4, height=4)

    points, valid_mask = target_point_cloud(
        depth_m=depth_m,
        intrinsics=intrinsics,
        mask=mask,
        min_depth_m=0.1,
        max_depth_m=1.0,
    )

    assert points.shape == (4, 3)
    assert valid_mask.sum() == 4
    assert [round(v, 4) for v in points[0].tolist()] == [0.0, 0.0, 0.5]


def test_plan_anygrasp_uses_backend_best_candidate():
    class FakeBackend:
        def get_grasp(self, points, colors, lims, **kwargs):
            assert points.shape == (4, 3)
            assert colors.shape == (4, 3)
            assert kwargs["apply_object_mask"] is True
            return [
                {
                    "translation": [0.1, 0.2, 0.3],
                    "rotation_matrix": np.eye(3),
                    "width": 0.03,
                    "score": 0.4,
                },
                {
                    "translation": [0.2, 0.1, 0.4],
                    "rotation_matrix": np.eye(3) * 2,
                    "width": 0.04,
                    "score": 0.9,
                },
            ], object()

    color_bgr = np.zeros((4, 4, 3), dtype=np.uint8)
    depth_m = np.full((4, 4), 0.5, dtype=np.float32)
    mask = np.zeros((4, 4), dtype=np.uint8)
    mask[1:3, 1:3] = 255
    detection = Detection2D("cube", "yellow", (1, 1, 2, 2), mask=mask)
    intrinsics = CameraIntrinsics(fx=100.0, fy=100.0, cx=1.0, cy=1.0, width=4, height=4)

    candidate = plan_anygrasp(
        color_bgr=color_bgr,
        depth_m=depth_m,
        intrinsics=intrinsics,
        detection=detection,
        backend=FakeBackend(),
    )

    assert candidate.position_camera == (0.2, 0.1, 0.4)
    assert candidate.rotation_camera == ((2.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 2.0))
    assert candidate.width_m == 0.04
    assert candidate.score == 0.9
    assert candidate.source == "anygrasp"


def test_load_anygrasp_sdk_missing_dependency_message():
    with pytest.raises(AnyGraspUnavailableError, match="graspnet/anygrasp_sdk"):
        _load_anygrasp_sdk()
