from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraspCandidate:
    position_camera: tuple[float, float, float]
    rotation_camera: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]
    width_m: float
    score: float
    source: str
