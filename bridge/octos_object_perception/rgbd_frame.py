from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .depth_geometry import CameraIntrinsics


@dataclass(frozen=True)
class RgbdFrame:
    color_bgr: np.ndarray
    depth_m: np.ndarray
    intrinsics: CameraIntrinsics
