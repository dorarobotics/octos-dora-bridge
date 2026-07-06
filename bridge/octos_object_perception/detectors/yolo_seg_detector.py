from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np

from octos_object_perception.types import Detection2D, TargetSpec


def _to_numpy(value) -> np.ndarray:
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        return np.asarray(value.numpy())
    return np.asarray(value)


def _class_name(names, cls_index: int) -> str:
    if isinstance(names, dict):
        return str(names.get(cls_index, cls_index))
    if isinstance(names, (list, tuple)) and 0 <= cls_index < len(names):
        return str(names[cls_index])
    return str(cls_index)


def _resize_mask(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    import cv2

    mask = (np.asarray(mask) > 0.5).astype(np.uint8) * 255
    height, width = shape
    if mask.shape[:2] != (height, width):
        mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)
    return mask


class YoloSegDetector:
    def __init__(
        self,
        *,
        model=None,
        model_path: str | Path | None = None,
        class_names: Iterable[str] | None = None,
        confidence: float = 0.25,
        device: str | None = None,
    ) -> None:
        self.model = model
        self.model_path = str(model_path) if model_path else None
        self.class_names = [str(name) for name in class_names] if class_names else None
        self.confidence = float(confidence)
        self.device = device

    def _model(self):
        if self.model is None:
            if not self.model_path:
                raise RuntimeError("YOLO model path is required for yolo_seg detector")
            from ultralytics import YOLO

            self.model = YOLO(self.model_path)
            if self.class_names and hasattr(self.model, "set_classes"):
                self.model.set_classes(self.class_names)
        return self.model

    def detect(self, frame_bgr, target: TargetSpec) -> list[Detection2D]:
        import cv2

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        kwargs = {"conf": self.confidence, "verbose": False}
        if self.device:
            kwargs["device"] = self.device
        results = self._model()(rgb, **kwargs)
        if not results:
            return []

        image_shape = frame_bgr.shape[:2]
        detections: list[Detection2D] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            masks = getattr(result, "masks", None)
            if boxes is None:
                continue
            xyxy = _to_numpy(boxes.xyxy)
            confs = _to_numpy(boxes.conf)
            classes = _to_numpy(boxes.cls).astype(int)
            mask_data = _to_numpy(masks.data) if masks is not None and getattr(masks, "data", None) is not None else None

            for index, box in enumerate(xyxy):
                category = _class_name(getattr(result, "names", {}), int(classes[index]))
                if target.category and category != target.category:
                    continue
                x1, y1, x2, y2 = [int(round(float(v))) for v in box]
                x = max(0, min(frame_bgr.shape[1] - 1, x1))
                y = max(0, min(frame_bgr.shape[0] - 1, y1))
                w = max(1, min(frame_bgr.shape[1], x2) - x)
                h = max(1, min(frame_bgr.shape[0], y2) - y)
                mask = None
                if mask_data is not None and index < len(mask_data):
                    mask = _resize_mask(mask_data[index], image_shape)
                detections.append(
                    Detection2D(
                        category=category,
                        color=target.color,
                        bbox=(x, y, w, h),
                        confidence=round(float(confs[index]), 6),
                        mask=mask,
                    )
                )
        return detections
