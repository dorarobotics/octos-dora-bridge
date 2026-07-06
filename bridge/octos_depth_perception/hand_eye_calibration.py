from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Mapping

import cv2
import numpy as np

from .depth_geometry import CameraIntrinsics


CHESSBOARD_INNER_CORNERS = (9, 6)
JOINT_KEYS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")


def intrinsics_document(
    intrinsics: CameraIntrinsics,
    *,
    square_size_mm: float,
) -> dict:
    return {
        "camera_matrix": [
            [float(intrinsics.fx), 0.0, float(intrinsics.cx)],
            [0.0, float(intrinsics.fy), float(intrinsics.cy)],
            [0.0, 0.0, 1.0],
        ],
        "dist_coeffs": [[0.0, 0.0, 0.0, 0.0, 0.0]],
        "image_size": [int(intrinsics.width or 0), int(intrinsics.height or 0)],
        "reprojection_error_px": 0.0,
        "num_images_used": 0,
        "square_size_mm": float(square_size_mm),
        "chessboard": list(CHESSBOARD_INNER_CORNERS),
    }


def append_hand_eye_pose(
    data_path: str | Path,
    joints: Mapping[str, float],
    rotation_target_to_cam: np.ndarray,
    translation_target_to_cam: np.ndarray,
    *,
    corners_count: int,
) -> dict:
    path = Path(data_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = []

    pose = {
        "joints": {key: round(float(value), 6) for key, value in joints.items()},
        "R_target2cam": np.asarray(rotation_target_to_cam, dtype=float).tolist(),
        "t_target2cam": np.asarray(translation_target_to_cam, dtype=float).reshape(3).tolist(),
        "corners_count": int(corners_count),
    }
    data.append(pose)
    path.write_text(json.dumps(data, indent=2))
    return {"pose_index": len(data) - 1, "total_poses": len(data)}


def _rotation_to_rpy(rotation: np.ndarray) -> list[float]:
    sy = float(np.sqrt(rotation[0, 0] ** 2 + rotation[1, 0] ** 2))
    if sy >= 1e-6:
        roll = np.arctan2(rotation[2, 1], rotation[2, 2])
        pitch = np.arctan2(-rotation[2, 0], sy)
        yaw = np.arctan2(rotation[1, 0], rotation[0, 0])
    else:
        roll = np.arctan2(-rotation[1, 2], rotation[1, 1])
        pitch = np.arctan2(-rotation[2, 0], sy)
        yaw = 0.0
    return [float(roll), float(pitch), float(yaw)]


def _load_camera_info(path: Path) -> dict:
    if not path.exists():
        return {"fx": 486.0, "fy": 468.0, "cx": 320.0, "cy": 288.0, "width": 640, "height": 480}
    data = json.loads(path.read_text())
    matrix = np.asarray(data["camera_matrix"], dtype=float)
    image_size = data.get("image_size", [640, 480])
    return {
        "fx": float(matrix[0, 0]),
        "fy": float(matrix[1, 1]),
        "cx": float(matrix[0, 2]),
        "cy": float(matrix[1, 2]),
        "width": int(image_size[0]),
        "height": int(image_size[1]),
    }


def _as_transform(value) -> np.ndarray:
    if isinstance(value, Mapping):
        value = value["transform"]
    transform = np.asarray(value, dtype=float)
    if transform.shape != (4, 4):
        raise ValueError(f"forward_kinematics must return a 4x4 transform, got {transform.shape}")
    return transform


def solve_hand_eye(
    data_path: str | Path,
    intrinsics_path: str | Path,
    output_path: str | Path,
    forward_kinematics: Callable[[list[float]], object],
    *,
    method: str = "park",
) -> tuple[dict, dict]:
    data_path = Path(data_path)
    intrinsics_path = Path(intrinsics_path)
    output_path = Path(output_path)
    data = json.loads(data_path.read_text())
    if len(data) < 6:
        raise ValueError(f"Need at least 6 hand-eye poses, have {len(data)}")

    rotations_gripper_to_base = []
    translations_gripper_to_base = []
    rotations_target_to_cam = []
    translations_target_to_cam = []
    for pose in data:
        joints = [float(pose["joints"][key]) for key in JOINT_KEYS]
        wrist_in_base = _as_transform(forward_kinematics(joints))
        rotations_gripper_to_base.append(wrist_in_base[:3, :3])
        translations_gripper_to_base.append(wrist_in_base[:3, 3].reshape(3, 1))
        rotations_target_to_cam.append(np.asarray(pose["R_target2cam"], dtype=float))
        translations_target_to_cam.append(np.asarray(pose["t_target2cam"], dtype=float).reshape(3, 1))

    methods = {
        "tsai": cv2.CALIB_HAND_EYE_TSAI,
        "park": cv2.CALIB_HAND_EYE_PARK,
        "horaud": cv2.CALIB_HAND_EYE_HORAUD,
        "andreff": cv2.CALIB_HAND_EYE_ANDREFF,
        "daniilidis": cv2.CALIB_HAND_EYE_DANIILIDIS,
    }
    if method not in methods:
        raise ValueError(f"Unknown method '{method}'. Available: {list(methods)}")

    rotation_cam_to_gripper, translation_cam_to_gripper = cv2.calibrateHandEye(
        rotations_gripper_to_base,
        translations_gripper_to_base,
        rotations_target_to_cam,
        translations_target_to_cam,
        method=methods[method],
    )

    cam_in_wrist = np.eye(4)
    cam_in_wrist[:3, :3] = rotation_cam_to_gripper
    cam_in_wrist[:3, 3] = np.asarray(translation_cam_to_gripper, dtype=float).reshape(3)

    target_positions = []
    for rotation_gripper, translation_gripper, rotation_target, translation_target in zip(
        rotations_gripper_to_base,
        translations_gripper_to_base,
        rotations_target_to_cam,
        translations_target_to_cam,
    ):
        wrist_in_base = np.eye(4)
        wrist_in_base[:3, :3] = rotation_gripper
        wrist_in_base[:3, 3] = translation_gripper.reshape(3)
        target_in_cam = np.eye(4)
        target_in_cam[:3, :3] = rotation_target
        target_in_cam[:3, 3] = translation_target.reshape(3)
        target_positions.append((wrist_in_base @ cam_in_wrist @ target_in_cam)[:3, 3])
    target_positions = np.asarray(target_positions, dtype=float)
    mean_position = target_positions.mean(axis=0)
    max_deviation = float(np.max(np.linalg.norm(target_positions - mean_position, axis=1)))

    result = {
        "T_cam_in_wrist": {
            "rpy": [round(value, 4) for value in _rotation_to_rpy(cam_in_wrist[:3, :3])],
            "translation": [round(float(value), 4) for value in cam_in_wrist[:3, 3]],
        },
        "camera": _load_camera_info(intrinsics_path),
        "Z_table": round(float(mean_position[2]), 4),
        "method": method,
        "num_poses": len(data),
    }
    verification = {
        "target_mean_xyz": [round(float(value), 4) for value in mean_position],
        "target_std_xyz": [round(float(value), 4) for value in target_positions.std(axis=0)],
        "max_deviation_m": round(max_deviation, 4),
        "max_deviation_mm": round(max_deviation * 1000.0, 2),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))
    return result, verification
