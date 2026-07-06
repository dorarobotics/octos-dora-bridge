from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


def _maybe_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


@dataclass(frozen=True)
class SizeEstimate:
    width: float
    height: float


@dataclass(frozen=True)
class SizeRange:
    min_width: float | None = None
    max_width: float | None = None
    min_height: float | None = None
    max_height: float | None = None

    @classmethod
    def from_mapping(cls, value: dict | None) -> "SizeRange | None":
        if not value:
            return None
        return cls(
            min_width=_maybe_float(value.get("min_width")),
            max_width=_maybe_float(value.get("max_width")),
            min_height=_maybe_float(value.get("min_height")),
            max_height=_maybe_float(value.get("max_height")),
        )

    def contains(self, size: SizeEstimate) -> bool:
        return all(
            (
                self.min_width is None or size.width >= self.min_width,
                self.max_width is None or size.width <= self.max_width,
                self.min_height is None or size.height >= self.min_height,
                self.max_height is None or size.height <= self.max_height,
            )
        )


@dataclass(frozen=True)
class TargetSpec:
    category: str | None = "cube"
    color: str | None = None
    size_range_m: SizeRange | None = None
    min_depth_m: float = 0.05
    max_depth_m: float = 2.0
    min_valid_ratio: float = 0.2

    @classmethod
    def from_mapping(cls, value: dict | None) -> "TargetSpec":
        value = value or {}
        return cls(
            category=value.get("category", "cube"),
            color=value.get("color"),
            size_range_m=SizeRange.from_mapping(value.get("size_range_m")),
            min_depth_m=float(value.get("min_depth_m", 0.05)),
            max_depth_m=float(value.get("max_depth_m", 2.0)),
            min_valid_ratio=float(value.get("min_valid_ratio", 0.2)),
        )


@dataclass(frozen=True)
class Detection2D:
    category: str
    color: str | None
    bbox: tuple[int, int, int, int]
    confidence: float = 1.0
    mask: np.ndarray | None = None

    @property
    def center(self) -> tuple[float, float]:
        x, y, w, h = self.bbox
        return x + w / 2.0, y + h / 2.0


@dataclass(frozen=True)
class Object3D:
    category: str
    color: str | None
    bbox: tuple[int, int, int, int]
    confidence: float
    distance_m: float
    point_camera: tuple[float, float, float]
    estimated_size_m: SizeEstimate
    depth_valid_ratio: float
    geometry_source: str

    def to_dict(self) -> dict:
        data = asdict(self)
        data["bbox"] = list(self.bbox)
        data["point_camera"] = list(self.point_camera)
        return data
