#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "bridge"))

from octos_camera.orbbec_gemini335 import Gemini335Camera
from octos_object_perception.detectors.color_size_detector import HSV_RANGES


def mask_for_color(hsv: np.ndarray, color: str) -> np.ndarray:
    mask = None
    for lower, upper in HSV_RANGES[color]:
        part = cv2.inRange(
            hsv,
            np.array(lower, dtype=np.uint8),
            np.array(upper, dtype=np.uint8),
        )
        mask = part if mask is None else cv2.bitwise_or(mask, part)
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)


def summarize_mask(mask: np.ndarray) -> dict:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 40:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        boxes.append({"bbox": [int(x), int(y), int(w), int(h)], "area_px": round(area, 1)})
    boxes.sort(key=lambda item: item["area_px"], reverse=True)
    return {
        "pixel_count": int(np.count_nonzero(mask)),
        "components": boxes[:10],
    }


def main() -> None:
    out_dir = Path(os.environ.get("OCTOS_DIAG_DIR", "/tmp/octos_gemini335_diag"))
    out_dir.mkdir(parents=True, exist_ok=True)

    cam = Gemini335Camera(serial_number=os.environ.get("ORBBEC_SN"))
    try:
        frame = cam.read(timeout_ms=5000)
    finally:
        cam.close()

    hsv = cv2.cvtColor(frame.color_bgr, cv2.COLOR_BGR2HSV)
    cv2.imwrite(str(out_dir / "color_bgr.png"), frame.color_bgr)

    valid_depth = frame.depth_m[np.isfinite(frame.depth_m) & (frame.depth_m > 0)]
    report = {
        "color_shape": list(frame.color_bgr.shape),
        "depth_shape": list(frame.depth_m.shape),
        "intrinsics": {
            "fx": frame.intrinsics.fx,
            "fy": frame.intrinsics.fy,
            "cx": frame.intrinsics.cx,
            "cy": frame.intrinsics.cy,
            "width": frame.intrinsics.width,
            "height": frame.intrinsics.height,
        },
        "depth_m": {
            "valid_count": int(valid_depth.size),
            "min": round(float(np.min(valid_depth)), 6) if valid_depth.size else None,
            "median": round(float(np.median(valid_depth)), 6) if valid_depth.size else None,
            "max": round(float(np.max(valid_depth)), 6) if valid_depth.size else None,
        },
        "colors": {},
    }

    for color in HSV_RANGES:
        mask = mask_for_color(hsv, color)
        cv2.imwrite(str(out_dir / f"mask_{color}.png"), mask)
        report["colors"][color] = summarize_mask(mask)

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path), "image": str(out_dir / "color_bgr.png")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
