#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


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


if __name__ == "__main__" and os.environ.get("OCTOS_DIAG_NO_REEXEC") != "1":
    python = preferred_python()
    if python is not None:
        env = os.environ.copy()
        env["OCTOS_DIAG_NO_REEXEC"] = "1"
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


def size_range_to_dict(size_range: SizeRange | None) -> dict[str, float | None] | None:
    if size_range is None:
        return None
    return {
        "min_width": size_range.min_width,
        "max_width": size_range.max_width,
        "min_height": size_range.min_height,
        "max_height": size_range.max_height,
    }


def depth_stats(depth_m: np.ndarray) -> dict[str, Any]:
    valid = depth_m[np.isfinite(depth_m) & (depth_m > 0)]
    return {
        "valid_count": int(valid.size),
        "min": round(float(np.min(valid)), 6) if valid.size else None,
        "median": round(float(np.median(valid)), 6) if valid.size else None,
        "max": round(float(np.max(valid)), 6) if valid.size else None,
    }


def build_report(
    *,
    objects,
    color_shape,
    depth_shape,
    detector_config: dict[str, Any],
    depth_stats: dict[str, Any],
) -> dict[str, Any]:
    return {
        "summary": {
            "geometry_source": "open3d_geometry",
            "object_count": len(objects),
        },
        "color_shape": list(color_shape),
        "depth_shape": list(depth_shape),
        "depth_m": depth_stats,
        "detector_config": detector_config,
        "objects": [obj.to_dict() for obj in objects],
    }


def draw_objects(color_bgr: np.ndarray, objects) -> np.ndarray:
    image = color_bgr.copy()
    for index, obj in enumerate(objects):
        x, y, w, h = obj.bbox
        cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
        label = f"{index}: {obj.distance_m:.3f}m {obj.estimated_size_m.width:.3f}x{obj.estimated_size_m.height:.3f}"
        cv2.putText(image, label, (x, max(15, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)
    return image


def save_depth_preview(depth_m: np.ndarray, path: Path) -> None:
    valid = depth_m[np.isfinite(depth_m) & (depth_m > 0)]
    if valid.size == 0:
        preview = np.zeros(depth_m.shape, dtype=np.uint8)
    else:
        lo = float(np.percentile(valid, 2))
        hi = float(np.percentile(valid, 98))
        if hi <= lo:
            hi = lo + 1e-6
        preview = np.clip((depth_m - lo) / (hi - lo), 0.0, 1.0)
        preview = (preview * 255).astype(np.uint8)
    cv2.imwrite(str(path), cv2.applyColorMap(preview, cv2.COLORMAP_TURBO))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnose Gemini 335 Open3D-style tabletop geometry perception.")
    parser.add_argument("--out-dir", default=os.environ.get("OCTOS_DIAG_DIR", "/tmp/octos_open3d_geometry_diag"))
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
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    workspace_bounds = parse_workspace_bounds(args.workspace_bounds_m)
    size_range = parse_size_range(args.size_range_m)
    detector_config = {
        "workspace_bounds_m": workspace_bounds,
        "target_color": args.color,
        "size_range_m": size_range_to_dict(size_range),
        "voxel_size_m": args.voxel_size_m,
        "table_threshold_m": args.table_threshold_m,
        "dbscan_eps_m": args.dbscan_eps_m,
        "dbscan_min_points": args.dbscan_min_points,
        "min_cluster_points": args.min_cluster_points,
    }

    cam = Gemini335Camera(serial_number=os.environ.get("ORBBEC_SN"))
    try:
        frame = cam.read(timeout_ms=args.timeout_ms)
    finally:
        cam.close()

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
    objects = detector.detect_3d(
        color_bgr=frame.color_bgr,
        depth_m=frame.depth_m,
        intrinsics=frame.intrinsics,
        target=target,
    )
    report = build_report(
        objects=objects,
        color_shape=frame.color_bgr.shape,
        depth_shape=frame.depth_m.shape,
        detector_config=detector_config,
        depth_stats=depth_stats(frame.depth_m),
    )

    color_path = out_dir / "color_bgr.png"
    depth_path = out_dir / "depth_preview.png"
    overlay_path = out_dir / "open3d_geometry_overlay.png"
    report_path = out_dir / "open3d_geometry_report.json"
    cv2.imwrite(str(color_path), frame.color_bgr)
    save_depth_preview(frame.depth_m, depth_path)
    cv2.imwrite(str(overlay_path), draw_objects(frame.color_bgr, objects))
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps({
        "report": str(report_path),
        "color": str(color_path),
        "depth": str(depth_path),
        "overlay": str(overlay_path),
        "object_count": len(objects),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
