#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
import time
import urllib.request
from importlib.machinery import SourceFileLoader
from pathlib import Path

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bridge"))

from octos_depth_perception.camera_orbbec import Gemini335Camera  # noqa: E402
from octos_depth_perception.hand_eye_calibration import (  # noqa: E402
    append_hand_eye_pose,
    intrinsics_document,
    solve_hand_eye,
)


DEFAULT_SKILL_PACK = REPO_ROOT / "skills" / "so101-depth-pick"
DEFAULT_MOVEIT_SKILL_PACK = REPO_ROOT.parent / "moveit-arm-dora-node" / "skill_pack"
DEFAULT_REBOT_MANIFEST = REPO_ROOT.parent / "rebot-hw-dora-node" / "manifests" / "so101-hw.json"
DEFAULT_DORA_MOVEIT2 = Path(os.environ.get("DORA_MOVEIT2", "/home/dora/so101-sim/dora-moveit2"))
DEFAULT_SO101_MODEL = (
    DEFAULT_DORA_MOVEIT2
    / "examples"
    / "move_group_demo"
    / "models"
    / "so101_pickplace_hw_calibrated.xml"
)
JOINT_KEYS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]

POSES_DEG = [
    ("pose1_lean", [-6.2, -48.0, 22.0, 72.0, -50.0]),
    ("pose2_fwd", [-6.2, -40.0, 40.0, 70.0, -47.1]),
    ("pose3_low", [-6.2, -60.0, 20.0, 85.0, -47.1]),
    ("pose4_left", [-20.0, -50.0, 30.0, 75.0, -35.0]),
    ("pose5_right", [10.0, -50.0, 30.0, 75.0, -60.0]),
    ("pose6_tilt", [-6.2, -45.0, 35.0, 65.0, -47.1]),
]


def bridge_call(base_url: str, verb: str, args: dict | None = None, timeout_s: int = 90) -> dict:
    payload = json.dumps({"args": args or {}}).encode()
    req = urllib.request.Request(
        f"{base_url}/tools/{verb}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as response:
        return json.loads(response.read().decode())


def move_joints_deg(base_url: str, joints_deg: list[float]) -> dict:
    joints_rad = [math.radians(value) for value in joints_deg]
    return bridge_call(
        base_url,
        "vendor.moveit.arm.move_to_joint_state",
        {"joints": joints_rad, "control_source": "octos"},
        timeout_s=120,
    )


def current_joints(base_url: str) -> dict[str, float]:
    state = bridge_call(base_url, "get_state", {}, timeout_s=5)
    values = state.get("data", {}).get("stream", {}).get("joint_positions")
    if not isinstance(values, list) or len(values) < len(JOINT_KEYS):
        raise RuntimeError(f"Bridge state does not contain {len(JOINT_KEYS)} joint positions")
    return {key: float(values[index]) for index, key in enumerate(JOINT_KEYS)}


def detect_chessboard(frame_bgr: np.ndarray, camera_matrix: np.ndarray, square_size_m: float):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    found, corners = cv2.findChessboardCorners(gray, (9, 6), None)
    if not found:
        found, corners = cv2.findChessboardCornersSB(gray, (9, 6), None)
    if not found:
        return None

    if corners is None:
        return None
    if corners.dtype != np.float32:
        corners = corners.astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

    objp = np.zeros((9 * 6, 3), np.float32)
    objp[:, :2] = np.mgrid[0:9, 0:6].T.reshape(-1, 2) * float(square_size_m)
    ok, rvec, tvec = cv2.solvePnP(objp, corners, camera_matrix, np.zeros((1, 5), dtype=np.float32))
    if not ok:
        return None
    rotation, _ = cv2.Rodrigues(rvec)
    return rotation, tvec.reshape(3), corners


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate SO101 hand-eye with Orbbec Gemini 335.")
    parser.add_argument("--bridge-url", default=os.environ.get("ARM_BRIDGE_URL", "http://127.0.0.1:8768"))
    parser.add_argument("--skill-pack", type=Path, default=Path(os.environ.get("SO101_DEPTH_SKILL_PACK", DEFAULT_SKILL_PACK)))
    parser.add_argument("--square-size-mm", type=float, default=float(os.environ.get("CALIB_SQUARE_SIZE_MM", "25")))
    parser.add_argument("--min-poses", type=int, default=6)
    parser.add_argument("--settle-s", type=float, default=4.0)
    parser.add_argument("--attempts", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true", help="Only check current camera chessboard detection.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for key in ("NO_PROXY", "no_proxy"):
        os.environ[key] = "127.0.0.1,localhost"

    calib_dir = args.skill_pack / "calibration"
    data_path = calib_dir / "hand_eye_data.json"
    intrinsics_path = calib_dir / "camera_intrinsics.json"
    preview_dir = calib_dir / "gemini335_hand_eye_images"
    preview_dir.mkdir(parents=True, exist_ok=True)

    camera = Gemini335Camera(serial_number=os.environ.get("ORBBEC_SN"))
    try:
        first_frame = camera.read(8000)
        camera_matrix = np.array(
            intrinsics_document(first_frame.intrinsics, square_size_mm=args.square_size_mm)["camera_matrix"],
            dtype=np.float32,
        )
        intrinsics_path.write_text(json.dumps(
            intrinsics_document(first_frame.intrinsics, square_size_mm=args.square_size_mm),
            indent=2,
        ))
        check = detect_chessboard(first_frame.color_bgr, camera_matrix, args.square_size_mm / 1000.0)
        check_path = preview_dir / "current_check.png"
        cv2.imwrite(str(check_path), first_frame.color_bgr)
        print(json.dumps({
            "stage": "initial_check",
            "image": str(check_path),
            "chessboard_found": check is not None,
            "intrinsics": first_frame.intrinsics.__dict__,
        }, ensure_ascii=False))
        if args.dry_run:
            return 0 if check is not None else 2

        if data_path.exists():
            backup = data_path.with_suffix(f".json.bak-{int(time.time())}")
            data_path.rename(backup)
            print(json.dumps({"stage": "backup_old_data", "backup": str(backup)}, ensure_ascii=False))

        collected = 0
        for index, (name, joints_deg) in enumerate(POSES_DEG, start=1):
            print(json.dumps({"stage": "move", "pose": name, "index": index, "joints_deg": joints_deg}, ensure_ascii=False))
            move_joints_deg(args.bridge_url, joints_deg)
            time.sleep(args.settle_s)
            joints = current_joints(args.bridge_url)

            detected = None
            frame_bgr = None
            for attempt in range(1, args.attempts + 1):
                frame = camera.read(8000)
                frame_bgr = frame.color_bgr
                detected = detect_chessboard(frame_bgr, camera_matrix, args.square_size_mm / 1000.0)
                if detected is not None:
                    break
                time.sleep(0.25)

            image_path = preview_dir / f"{index:02d}_{name}.png"
            if frame_bgr is not None:
                cv2.imwrite(str(image_path), frame_bgr)

            if detected is None:
                print(json.dumps({
                    "stage": "pose_skipped",
                    "pose": name,
                    "reason": "chessboard_not_detected",
                    "image": str(image_path),
                }, ensure_ascii=False))
                continue

            rotation, translation, corners = detected
            result = append_hand_eye_pose(
                data_path,
                joints,
                rotation,
                translation,
                corners_count=len(corners),
            )
            collected = result["total_poses"]
            print(json.dumps({
                "stage": "pose_collected",
                "pose": name,
                "total_poses": collected,
                "target_translation_m": [round(float(v), 6) for v in translation],
                "image": str(image_path),
            }, ensure_ascii=False))
    finally:
        camera.close()

    if collected < args.min_poses:
        print(json.dumps({
            "stage": "failed",
            "reason": f"need at least {args.min_poses} poses, collected {collected}",
            "data": str(data_path),
        }, ensure_ascii=False))
        return 1

    os.environ["SKILL_PACK"] = os.environ.get("SO101_MOVEIT_SKILL_PACK", str(DEFAULT_MOVEIT_SKILL_PACK))
    os.environ.setdefault("OCTOS_ROBOT", "so101")
    os.environ.setdefault("ARM_BRIDGE_URL", args.bridge_url)
    os.environ.setdefault("MODEL_NAME", str(DEFAULT_SO101_MODEL))
    os.environ.setdefault("ROBOT_MANIFEST", str(DEFAULT_REBOT_MANIFEST))

    loader = SourceFileLoader("so101_depth_pick_main", str(DEFAULT_SKILL_PACK / "main"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load so101-depth-pick runtime")
    so101_depth_pick = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(so101_depth_pick)

    result, verification = solve_hand_eye(
        data_path,
        intrinsics_path,
        calib_dir / "hand_eye.json",
        so101_depth_pick.forward_kinematics,
        method="park",
    )
    print(json.dumps({
        "stage": "solved",
        "calibration": result,
        "verification": verification,
        "hand_eye": str(calib_dir / "hand_eye.json"),
    }, ensure_ascii=False))
    bridge_call(args.bridge_url, "vendor.moveit.arm.move_to_named", {"name": "home"}, timeout_s=120)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
