from __future__ import annotations

from dataclasses import replace

from octos_object_perception.types import Detection2D, TargetSpec


DEFAULT_PROP_ALIASES = {
    "cup": {"cup", "mouse", "toilet"},
    "box": {"box", "suitcase", "tv", "book"},
    "cube": {"cube", "box", "sports ball"},
    "apple": {"apple", "orange", "sports ball"},
    "pear": {"pear", "apple", "orange"},
}


class PropDetector:
    """Normalize generic detector classes into local tabletop prop classes."""

    def __init__(
        self,
        *,
        base_detector,
        aliases: dict[str, set[str]] | None = None,
        max_bbox_area_ratio: float = 0.8,
    ) -> None:
        self.base_detector = base_detector
        self.aliases = aliases or DEFAULT_PROP_ALIASES
        self.max_bbox_area_ratio = float(max_bbox_area_ratio)

    def _mapped_category(self, category: str, requested: str | None) -> str | None:
        if not requested:
            return category
        allowed = self.aliases.get(requested, {requested})
        if category in allowed:
            return requested
        return None

    def detect(self, frame_bgr, target: TargetSpec) -> list[Detection2D]:
        scan_target = replace(target, category=None)
        detections = self.base_detector.detect(frame_bgr, scan_target)
        mapped: list[Detection2D] = []
        frame_area = max(1, int(frame_bgr.shape[0]) * int(frame_bgr.shape[1]))

        for detection in detections:
            _, _, width, height = detection.bbox
            area_ratio = float(width * height) / float(frame_area)
            if area_ratio > self.max_bbox_area_ratio:
                continue
            category = self._mapped_category(detection.category, target.category)
            if category is None:
                continue
            mapped.append(replace(detection, category=category, color=target.color))

        return mapped
