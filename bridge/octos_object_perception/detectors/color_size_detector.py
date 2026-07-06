from __future__ import annotations

from octos_object_perception.types import Detection2D, TargetSpec


HSV_RANGES = {
    "orange": [((5, 70, 70), (22, 255, 255))],
    "yellow": [((18, 70, 70), (38, 255, 255))],
    "green": [((38, 50, 40), (90, 255, 255))],
    "blue": [((90, 50, 40), (130, 255, 255))],
    "red": [((0, 70, 50), (10, 255, 255)), ((170, 70, 50), (180, 255, 255))],
    "black": [((0, 0, 0), (180, 255, 80))],
}


class ColorSizeDetector:
    def __init__(self, *, min_area_px: int = 120) -> None:
        self.min_area_px = int(min_area_px)

    def detect(self, frame_bgr, target: TargetSpec) -> list[Detection2D]:
        import cv2
        import numpy as np

        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        requested = [target.color] if target.color else list(HSV_RANGES)
        detections: list[Detection2D] = []

        for color in requested:
            if color is None:
                continue
            ranges = HSV_RANGES.get(color)
            if not ranges:
                continue
            mask = None
            for lower, upper in ranges:
                part = cv2.inRange(
                    hsv,
                    np.array(lower, dtype=np.uint8),
                    np.array(upper, dtype=np.uint8),
                )
                mask = part if mask is None else cv2.bitwise_or(mask, part)

            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < self.min_area_px:
                    continue
                x, y, w, h = cv2.boundingRect(contour)
                object_mask = np.zeros(mask.shape, dtype=np.uint8)
                cv2.drawContours(object_mask, [contour], contourIdx=-1, color=255, thickness=-1)
                detections.append(
                    Detection2D(
                        category=target.category or "object",
                        color=color,
                        bbox=(int(x), int(y), int(w), int(h)),
                        confidence=min(1.0, float(area) / max(float(w * h), 1.0)),
                        mask=object_mask,
                    )
                )

        return detections
