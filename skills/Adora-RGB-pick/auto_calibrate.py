#!/usr/bin/env python3
"""Fully automated camera-intrinsics + hand-eye calibration.

Supports both Orbbec Gemini 335 (pyorbbecsdk) and generic USB cameras (OpenCV).
Auto-detects which camera is available.
"""
import json, math, os, sys, time, urllib.request
from pathlib import Path

import numpy as np

BRIDGE = os.environ.get("ARM_BRIDGE_URL", "http://127.0.0.1:8768")
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "calibration"))

CAMERA_DEVICE = os.environ.get("CAMERA_DEVICE", "/dev/video4")
ORBBEC_SN = os.environ.get("ORBBEC_SN", "CP1E542000CJ")

PATTERN_COLS, PATTERN_ROWS = 9, 6
SQUARE_SIZE = 0.025  # 25mm

# Pre-defined hand-eye poses (degrees) — angular diversity
POSES_DEG = [
    ("pose1_home",    [-6.2, -55.0, 30.3, 79.4, -47.1]),
    ("pose2_fwd",     [-6.2, -40.0, 40.0, 70.0, -47.1]),
    ("pose3_low",     [-6.2, -60.0, 20.0, 85.0, -47.1]),
    ("pose4_left",    [-20.0, -50.0, 30.0, 75.0, -35.0]),
    ("pose5_right",   [10.0, -50.0, 30.0, 75.0, -60.0]),
    ("pose6_tilt",    [-6.2, -45.0, 35.0, 65.0, -47.1]),
]


# ── Bridge helpers ──────────────────────────────────────────────
def _bridge(method, path, args=None, timeout=120):
    data = json.dumps({"args": args or {}}).encode()
    req = urllib.request.Request(
        f"{BRIDGE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _move_joints_deg(deg_list):
    rad = [d * math.pi / 180.0 for d in deg_list]
    return _bridge("POST", "/tools/vendor.moveit.arm.move_to_joint_state",
                   {"joints": rad})


def _move_named(name="home"):
    return _bridge("POST", "/tools/vendor.moveit.arm.move_to_named",
                   {"name": name})


def _get_joints_rad():
    resp = _bridge("POST", "/tools/get_state")
    return [float(v) for v in resp["data"]["stream"]["joint_positions"]]


# ── Camera detection ────────────────────────────────────────────
def _detect_camera_type():
    """Return 'orbbec' if Orbbec SDK available and device found, else 'usb'."""
    try:
        import pyorbbecsdk as obsdk
        ctx = obsdk.Context()
        dev_list = ctx.query_devices()
        if dev_list.get_count() > 0:
            return "orbbec"
    except Exception:
        pass
    return "usb"


# ── USB camera helpers ──────────────────────────────────────────
def _usb_open():
    from vision.camera import Camera
    cam = Camera(device=CAMERA_DEVICE)
    return cam


def _usb_grab(cam):
    return cam.read()


def _usb_detect_chessboard(bgr):
    from calibration.calib_tools import detect_chessboard
    return detect_chessboard(bgr, SQUARE_SIZE * 1000)  # expects mm


# ── Orbbec camera helpers ───────────────────────────────────────
def _orbbec_open():
    # Lazy import — only if orbbec is actually installed
    import pyorbbecsdk as obsdk
    ctx = obsdk.Context()
    dev_list = ctx.query_devices()
    if dev_list.get_count() == 0:
        raise RuntimeError("No Orbbec device found")
    device = dev_list.get_device_by_serial_number(ORBBEC_SN)
    if device is None:
        # Fall back to first device
        device = dev_list[0]
    pipeline = obsdk.Pipeline(device)
    config = obsdk.Config()
    config.enable_color_stream(640, 480, obsdk.OBFormat.RGB, 30)
    profile = pipeline.start(config)
    # Get intrinsics from stream profile
    color_profile = profile.get_color_stream_profile()
    intr = color_profile.get_intrinsics()
    camera_matrix = np.array([[intr.fx, 0, intr.cx],
                               [0, intr.fy, intr.cy],
                               [0, 0, 1]], dtype=np.float32)
    dist_coeffs = np.array(intr.coeffs[:5], dtype=np.float32) if intr.coeffs else np.zeros(5)
    return pipeline, camera_matrix, dist_coeffs


def _orbbec_grab(pipeline):
    import cv2
    import pyorbbecsdk as obsdk
    frames = pipeline.wait_for_frames(3000)
    if frames is None:
        return None
    color_frame = frames.get_color_frame()
    if color_frame is None:
        return None
    data = np.frombuffer(color_frame.get_data(), dtype=np.uint8)
    h, w = color_frame.get_height(), color_frame.get_width()
    rgb = data.reshape(h, w, 3)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _orbbec_detect_chessboard(bgr, camera_matrix, dist_coeffs):
    import cv2
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    ret, corners = cv2.findChessboardCorners(gray, (PATTERN_COLS, PATTERN_ROWS), None)
    if not ret:
        return None
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
    w, h = PATTERN_COLS, PATTERN_ROWS
    objp = np.zeros((w * h, 3), np.float32)
    objp[:, :2] = np.mgrid[0:w, 0:h].T.reshape(-1, 2) * SQUARE_SIZE
    retval, rvec, tvec = cv2.solvePnP(objp, corners, camera_matrix, dist_coeffs)
    if not retval:
        return None
    R_ct, _ = cv2.Rodrigues(rvec)
    return R_ct, tvec.flatten()


# ── Main calibration flow ───────────────────────────────────────
def main():
    camera_type = _detect_camera_type()
    print(f"{'='*60}")
    print(f"Auto Calibration — camera: {camera_type.upper()}")
    print(f"{'='*60}")

    if camera_type == "orbbec":
        _run_orbbec()
    else:
        _run_usb()


def _run_usb():
    import cv2, glob
    from calibration.calib_tools import (
        capture_chessboard_image, calibrate_camera_intrinsics,
        collect_hand_eye_pose, solve_hand_eye, IMAGES_DIR,
    )
    import calibration.calib_tools as ct

    # ── 1. Auto camera intrinsics: move arm, capture chessboard ──
    print("\n[1] Auto camera intrinsics calibration (USB)")
    print(f"    Chessboard stays fixed. Arm moves camera to {len(POSES_DEG)} poses.")

    # Clear old images
    for old in glob.glob(os.path.join(IMAGES_DIR, "img_*.png")):
        os.remove(old)

    cam = _usb_open()
    count = 0
    try:
        for idx, (name, joints_deg) in enumerate(POSES_DEG):
            print(f"\n  --- Pose {idx+1}/{len(POSES_DEG)}: {name} ---")
            _move_joints_deg(joints_deg)
            time.sleep(4)

            detected = False
            for attempt in range(15):
                time.sleep(0.3)
                frame = _usb_grab(cam)
                result = capture_chessboard_image(frame, SQUARE_SIZE * 1000)
                if result:
                    count = result["total_images"]
                    print(f"    ✓ Saved (#{result['index']}), total={count}")
                    detected = True
                    break
            if not detected:
                print(f"    ✗ Chessboard not detected!")
    finally:
        cam.close()

    if count < 5:
        print(f"\nERROR: need at least 5 images, got {count}. Aborting.")
        sys.exit(1)

    print(f"\n    Calibrating with {count} images...")
    intrinsics = calibrate_camera_intrinsics(SQUARE_SIZE * 1000)
    print(f"    ✓ Reprojection error: {intrinsics['reprojection_error_px']} px")
    print(f"    ✓ Camera matrix:\n{np.array(intrinsics['camera_matrix'])}")

    # ── 2. Auto hand-eye collection (reuse same poses + joint reading) ──
    print(f"\n[2] Auto hand-eye pose collection (USB)")
    print(f"    Chessboard stays FIXED. Arm moves through {len(POSES_DEG)} poses.")

    # Clear old data
    HAND_EYE_DATA = os.path.join(SCRIPT_DIR, "calibration", "hand_eye_data.json")
    if os.path.exists(HAND_EYE_DATA):
        os.remove(HAND_EYE_DATA)

    cam = _usb_open()
    pairs = 0
    try:
        for idx, (name, joints_deg) in enumerate(POSES_DEG):
            print(f"\n  --- Pose {idx+1}/{len(POSES_DEG)}: {name} ---")
            print(f"    Target (deg): {[f'{d:.0f}' for d in joints_deg]}")
            _move_joints_deg(joints_deg)
            time.sleep(4)

            joints_rad = _get_joints_rad()
            keys = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]
            jd = {k: joints_rad[i] for i, k in enumerate(keys)}

            detected = False
            for attempt in range(15):
                time.sleep(0.3)
                frame = _usb_grab(cam)
                result = collect_hand_eye_pose(frame, jd, SQUARE_SIZE * 1000)
                if result:
                    pairs = result["total_poses"]
                    print(f"    ✓ Saved, total={pairs}")
                    detected = True
                    break
            if not detected:
                print(f"    ✗ Chessboard not detected!")
    finally:
        cam.close()

    if pairs < 3:
        print(f"\nERROR: need at least 3 hand-eye poses, got {pairs}. Aborting.")
        sys.exit(1)

    # ── 3. Solve ──
    print(f"\n[3] Solving hand-eye with {pairs} poses...")
    result, verification = solve_hand_eye(method="park")
    print(f"    ✓ T_cam_in_wrist RPY: {result['T_cam_in_wrist']['rpy']}")
    print(f"    ✓ T_cam_in_wrist translation: {result['T_cam_in_wrist']['translation']}")
    print(f"    ✓ Z_table: {result['Z_table']}")
    print(f"    ✓ Max deviation: {verification['max_deviation_mm']} mm")

    _move_named("home")
    print("\nDone! Calibration saved to calibration/hand_eye.json")


def _run_orbbec():
    import cv2
    from calibration.calib_tools import solve_hand_eye
    from arm_skills import forward_kinematics

    # ── 1. Open camera ──
    print("\n[1] Opening Orbbec color stream...")
    pipeline, camera_matrix, dist_coeffs = _orbbec_open()
    print(f"    ✓ Camera matrix:\n{camera_matrix}")

    # ── 2. Camera intrinsics (from Orbbec SDK) ──
    print("\n[2] Using Orbbec built-in intrinsics...")
    intrinsics = {
        "camera_matrix": camera_matrix.tolist(),
        "dist_coeffs": dist_coeffs.tolist(),
        "image_size": [640, 480],
        "reprojection_error_px": 0.0,
        "num_images_used": 0,
        "square_size_mm": 25,
        "chessboard": [9, 6],
    }
    # Save intrinsics so solve_hand_eye can find them
    from calibration.calib_tools import INTRINSICS_FILE
    with open(INTRINSICS_FILE, "w") as f:
        json.dump(intrinsics, f, indent=2)
    print("    ✓ Saved to camera_intrinsics.json")

    # ── 3. Hand-eye collection ──
    print(f"\n[3] Hand-eye pose collection (Orbbec)")
    print(f"    Place chessboard FIXED. Arm will move to {len(POSES_DEG)} poses.")

    HAND_EYE_DATA = os.path.join(SCRIPT_DIR, "calibration", "hand_eye_data.json")
    pairs = []
    for idx, (name, joints_deg) in enumerate(POSES_DEG):
        print(f"\n  --- Pose {idx+1}/{len(POSES_DEG)}: {name} ---")
        _move_joints_deg(joints_deg)
        time.sleep(4)

        joints_rad = _get_joints_rad()
        keys = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]
        jd = {k: joints_rad[i] for i, k in enumerate(keys)}

        detected = False
        for attempt in range(15):
            time.sleep(0.3)
            bgr = _orbbec_grab(pipeline)
            if bgr is None:
                continue
            result = _orbbec_detect_chessboard(bgr, camera_matrix, dist_coeffs)
            if result is not None:
                R_ct, t_ct = result
                pairs.append({
                    "joints": {k: round(float(v), 2) for k, v in jd.items()},
                    "R_target2cam": R_ct.tolist(),
                    "t_target2cam": t_ct.tolist(),
                })
                print(f"    ✓ Saved ({len(pairs)}/{len(POSES_DEG)})")
                detected = True
                break
        if not detected:
            print(f"    ✗ Chessboard not detected!")

    pipeline.stop()

    if len(pairs) < 3:
        print(f"\nERROR: need at least 3 poses, got {len(pairs)}. Aborting.")
        sys.exit(1)

    # Save hand_eye_data for solve_hand_eye
    with open(HAND_EYE_DATA, "w") as f:
        json.dump(pairs, f, indent=2)

    # ── 4. Solve ──
    print(f"\n[4] Solving hand-eye with {len(pairs)} poses...")
    result, verification = solve_hand_eye(method="park")
    print(f"    ✓ T_cam_in_wrist RPY: {result['T_cam_in_wrist']['rpy']}")
    print(f"    ✓ T_cam_in_wrist translation: {result['T_cam_in_wrist']['translation']}")
    print(f"    ✓ Z_table: {result['Z_table']}")
    print(f"    ✓ Max deviation: {verification['max_deviation_mm']} mm")

    _move_named("home")
    print("\nDone! Calibration saved.")


if __name__ == "__main__":
    main()
