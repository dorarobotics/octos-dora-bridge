from __future__ import annotations

import json

import numpy as np

from octos_depth_perception.depth_geometry import CameraIntrinsics
from octos_depth_perception.hand_eye_calibration import (
    append_hand_eye_pose,
    intrinsics_document,
    solve_hand_eye,
)


def test_intrinsics_document_matches_existing_calibration_format():
    intr = CameraIntrinsics(fx=459.8, fy=459.7, cx=426.2, cy=237.7, width=848, height=480)

    doc = intrinsics_document(intr, square_size_mm=25.0)

    assert doc["camera_matrix"] == [[459.8, 0.0, 426.2], [0.0, 459.7, 237.7], [0.0, 0.0, 1.0]]
    assert doc["dist_coeffs"] == [[0.0, 0.0, 0.0, 0.0, 0.0]]
    assert doc["image_size"] == [848, 480]
    assert doc["square_size_mm"] == 25.0
    assert doc["chessboard"] == [9, 6]


def test_append_hand_eye_pose_writes_pose_list(tmp_path):
    data_path = tmp_path / "hand_eye_data.json"
    joints = {
        "shoulder_pan": 0.1,
        "shoulder_lift": -0.2,
        "elbow_flex": 0.3,
        "wrist_flex": 0.4,
        "wrist_roll": -0.5,
    }
    rotation = np.eye(3)
    translation = np.array([0.11, 0.22, 0.33])

    result = append_hand_eye_pose(data_path, joints, rotation, translation, corners_count=54)

    assert result == {"pose_index": 0, "total_poses": 1}
    saved = json.loads(data_path.read_text())
    assert saved == [
        {
            "joints": {
                "shoulder_pan": 0.1,
                "shoulder_lift": -0.2,
                "elbow_flex": 0.3,
                "wrist_flex": 0.4,
                "wrist_roll": -0.5,
            },
            "R_target2cam": rotation.tolist(),
            "t_target2cam": translation.tolist(),
            "corners_count": 54,
        }
    ]


def test_solve_hand_eye_requires_six_poses(tmp_path):
    data_path = tmp_path / "hand_eye_data.json"
    data_path.write_text("[]")

    try:
        solve_hand_eye(data_path, tmp_path / "intrinsics.json", tmp_path / "hand_eye.json", lambda joints: np.eye(4))
    except ValueError as exc:
        assert "Need at least 6 hand-eye poses" in str(exc)
    else:
        raise AssertionError("solve_hand_eye should reject fewer than 6 poses")


def test_solve_hand_eye_writes_finite_result(monkeypatch, tmp_path):
    data_path = tmp_path / "hand_eye_data.json"
    intrinsics_path = tmp_path / "camera_intrinsics.json"
    output_path = tmp_path / "hand_eye.json"
    pose = {
        "joints": {
            "shoulder_pan": 0.0,
            "shoulder_lift": -1.0,
            "elbow_flex": 1.0,
            "wrist_flex": 0.8,
            "wrist_roll": 0.0,
        },
        "R_target2cam": np.eye(3).tolist(),
        "t_target2cam": [0.1, 0.2, 0.5],
        "corners_count": 54,
    }
    data_path.write_text(json.dumps([pose] * 6))
    intrinsics_path.write_text(json.dumps(intrinsics_document(
        CameraIntrinsics(fx=459.8, fy=459.7, cx=426.2, cy=237.7, width=848, height=480),
        square_size_mm=25.0,
    )))

    def fake_calibrate_hand_eye(*args, **kwargs):
        return np.eye(3), np.array([[0.01], [0.02], [0.03]])

    monkeypatch.setattr("cv2.calibrateHandEye", fake_calibrate_hand_eye)

    result, verification = solve_hand_eye(data_path, intrinsics_path, output_path, lambda joints: np.eye(4))

    assert result["T_cam_in_wrist"]["translation"] == [0.01, 0.02, 0.03]
    assert result["camera"]["width"] == 848
    assert result["num_poses"] == 6
    assert verification["max_deviation_mm"] >= 0.0
    saved = json.loads(output_path.read_text())
    assert saved == result
