#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]


def preferred_python() -> Path | None:
    candidates = [
        REPO_ROOT / ".adora-hw-run" / "venv-python",
        Path("/home/dora/so101-sim/venv/bin/python3"),
    ]
    current = Path(sys.executable).resolve()
    for candidate in candidates:
        if candidate.exists() and candidate.resolve() != current:
            return candidate
    return None


if __name__ == "__main__" and os.environ.get("OCTOS_LIVE_VIEW_NO_REEXEC") != "1":
    python = preferred_python()
    if python is not None:
        env = os.environ.copy()
        env["OCTOS_LIVE_VIEW_NO_REEXEC"] = "1"
        os.execve(str(python), [str(python), *sys.argv], env)

import cv2
import numpy as np

sys.path.insert(0, str(REPO_ROOT / "bridge"))

from octos_camera.orbbec_gemini335 import Gemini335Camera
from octos_object_perception.detectors.open3d_geometry_detector import Open3DGeometryDetector
from octos_object_perception.types import SizeRange, TargetSpec


def parse_workspace_bounds(value: str | None) -> dict[str, list[float]] | None:
    if not value:
        return None
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("workspace bounds must be a JSON object")
    parsed: dict[str, list[float]] = {}
    for axis in ("x", "y", "z"):
        if axis not in data:
            continue
        bounds = data[axis]
        if not isinstance(bounds, list | tuple) or len(bounds) != 2:
            raise ValueError(f"workspace bounds axis {axis!r} must contain exactly two numbers")
        parsed[axis] = [float(bounds[0]), float(bounds[1])]
    return parsed


def parse_size_range(value: str | None) -> SizeRange | None:
    if not value:
        return None
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("size range must be a JSON object")
    return SizeRange(
        min_width=float(data["min_width"]) if data.get("min_width") is not None else None,
        max_width=float(data["max_width"]) if data.get("max_width") is not None else None,
        min_height=float(data["min_height"]) if data.get("min_height") is not None else None,
        max_height=float(data["max_height"]) if data.get("max_height") is not None else None,
    )


def draw_live_overlay(color_bgr: np.ndarray, objects: Sequence, *, fps: float) -> np.ndarray:
    image = np.asarray(color_bgr).copy()
    cv2.putText(
        image,
        f"Open3D geometry live  objects={len(objects)}  fps={fps:.1f}  q/Esc quit",
        (12, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        2,
    )
    cv2.putText(
        image,
        f"Open3D geometry live  objects={len(objects)}  fps={fps:.1f}  q/Esc quit",
        (12, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 0, 0),
        1,
    )
    for index, obj in enumerate(objects):
        x, y, w, h = obj.bbox
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
        label = f"{index}: {obj.color or obj.category} {obj.distance_m:.3f}m {obj.estimated_size_m.width:.3f}x{obj.estimated_size_m.height:.3f}"
        label_y = max(44, y - 7)
        cv2.putText(image, label, (x, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
        cv2.putText(image, label, (x, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
    return image


def should_quit(key: int, *, visible: bool) -> bool:
    if not visible:
        return True
    normalized = key & 0xFF
    return normalized in (27, ord("q"), ord("Q"))


def window_visible(window_name: str) -> bool:
    try:
        return cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) >= 1
    except cv2.error:
        return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live OpenCV viewer for Gemini 335 Open3D-style perception.")
    parser.add_argument("--window-name", default="octos open3d geometry live")
    parser.add_argument("--out-dir", default=os.environ.get("OCTOS_LIVE_VIEW_DIR", "/tmp/octos_open3d_geometry_live"))
    parser.add_argument("--category", default="object")
    parser.add_argument("--color", default=os.environ.get("OPEN3D_TARGET_COLOR"))
    parser.add_argument("--size-range-m", default=os.environ.get("OPEN3D_SIZE_RANGE_M"))
    parser.add_argument("--workspace-bounds-m", default=os.environ.get("OPEN3D_WORKSPACE_BOUNDS_M"))
    parser.add_argument("--voxel-size-m", type=float, default=float(os.environ.get("OPEN3D_VOXEL_SIZE_M", 0.005)))
    parser.add_argument(
        "--table-threshold-m",
        type=float,
        default=float(os.environ.get("OPEN3D_TABLE_THRESHOLD_M", 0.01)),
    )
    parser.add_argument("--dbscan-eps-m", type=float, default=float(os.environ.get("OPEN3D_DBSCAN_EPS_M", 0.025)))
    parser.add_argument(
        "--dbscan-min-points",
        type=int,
        default=int(os.environ.get("OPEN3D_DBSCAN_MIN_POINTS", 30)),
    )
    parser.add_argument(
        "--min-cluster-points",
        type=int,
        default=int(os.environ.get("OPEN3D_MIN_CLUSTER_POINTS", 80)),
    )
    parser.add_argument("--min-depth-m", type=float, default=0.05)
    parser.add_argument("--max-depth-m", type=float, default=2.0)
    parser.add_argument("--timeout-ms", type=int, default=5000)
    parser.add_argument("--max-fps", type=float, default=12.0)
    parser.add_argument("--once", action="store_true", help="Process one frame and exit.")
    parser.add_argument("--no-window", action="store_true", help="Do not call cv2.imshow; useful for smoke tests.")
    parser.add_argument(
        "--save-last",
        default=os.environ.get("OPEN3D_LIVE_LAST_FRAME", "/tmp/octos_open3d_geometry_live/last_overlay.png"),
    )
    return parser


def run_live(args: argparse.Namespace) -> int:
    workspace_bounds = parse_workspace_bounds(args.workspace_bounds_m)
    size_range = parse_size_range(args.size_range_m)
    detector = Open3DGeometryDetector(
        workspace_bounds_m=workspace_bounds,
        voxel_size_m=args.voxel_size_m,
        table_distance_threshold_m=args.table_threshold_m,
        dbscan_eps_m=args.dbscan_eps_m,
        dbscan_min_points=args.dbscan_min_points,
        min_cluster_points=args.min_cluster_points,
    )
    target = TargetSpec(
        category=args.category,
        color=args.color,
        size_range_m=size_range,
        min_depth_m=args.min_depth_m,
        max_depth_m=args.max_depth_m,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    save_last = Path(args.save_last) if args.save_last else None
    if save_last is not None:
        save_last.parent.mkdir(parents=True, exist_ok=True)

    if not args.no_window:
        cv2.namedWindow(args.window_name, cv2.WINDOW_NORMAL)

    frame_interval = 1.0 / args.max_fps if args.max_fps > 0.0 else 0.0
    last_frame_at = 0.0
    fps = 0.0
    last_overlay = None

    cam = Gemini335Camera(serial_number=os.environ.get("ORBBEC_SN"))
    try:
        while True:
            started_at = time.monotonic()
            frame = cam.read(timeout_ms=args.timeout_ms)
            objects = detector.detect_3d(
                color_bgr=frame.color_bgr,
                depth_m=frame.depth_m,
                intrinsics=frame.intrinsics,
                target=target,
            )
            elapsed = max(time.monotonic() - started_at, 1e-6)
            instant_fps = 1.0 / elapsed
            fps = instant_fps if fps <= 0.0 else (0.8 * fps + 0.2 * instant_fps)
            last_overlay = draw_live_overlay(frame.color_bgr, objects, fps=fps)

            if save_last is not None:
                cv2.imwrite(str(save_last), last_overlay)

            if not args.no_window:
                cv2.imshow(args.window_name, last_overlay)
                key = cv2.waitKey(1)
                if should_quit(key, visible=window_visible(args.window_name)):
                    break

            print(
                json.dumps(
                    {
                        "objects": len(objects),
                        "fps": round(fps, 3),
                        "last_overlay": str(save_last) if save_last is not None else None,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

            if args.once:
                break
            if frame_interval > 0.0:
                spent = time.monotonic() - last_frame_at
                if spent < frame_interval:
                    time.sleep(frame_interval - spent)
                last_frame_at = time.monotonic()
    finally:
        cam.close()
        if save_last is not None and last_overlay is not None:
            cv2.imwrite(str(save_last), last_overlay)
        if not args.no_window:
            cv2.destroyWindow(args.window_name)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_live(args)


if __name__ == "__main__":
    raise SystemExit(main())
