from __future__ import annotations

import math
from types import SimpleNamespace

import cv2
import numpy as np

from octos_depth_perception.camera_orbbec import (
    _align_frames_to_color,
    _apply_enabled_depth_filters,
    _color_frame_to_bgr,
    _depth_frame_to_meters,
    _profile_intrinsics,
    _wait_for_complete_frames,
)
from octos_depth_perception.depth_geometry import (
    CameraIntrinsics,
    Detection2D,
    SizeEstimate,
    SizeRange,
    depth_mask_centroid_camera,
    enrich_detection_with_depth,
    filter_detections,
    project_pixel_to_camera,
    robust_depth_m,
)


class _FakeFrameSet:
    def __init__(self, has_color: bool, has_depth: bool) -> None:
        self._has_color = has_color
        self._has_depth = has_depth

    def get_color_frame(self):
        return object() if self._has_color else None

    def get_depth_frame(self):
        return object() if self._has_depth else None


class _FakePipeline:
    def __init__(self, frames):
        self.frames = list(frames)
        self.calls = 0

    def wait_for_frames(self, timeout_ms: int):
        self.calls += 1
        return self.frames.pop(0) if self.frames else None


class _FakeColorFrame:
    def __init__(self, data: bytes, width: int, height: int, fmt: str) -> None:
        self._data = data
        self._width = width
        self._height = height
        self._fmt = fmt

    def get_data(self):
        return self._data

    def get_width(self):
        return self._width

    def get_height(self):
        return self._height

    def get_format(self):
        return self._fmt


class _FakeDepthFrame:
    def __init__(self, depth: np.ndarray, scale: float = 1.0) -> None:
        self._depth = depth
        self._scale = scale

    def get_data(self):
        return self._depth.tobytes()

    def get_width(self):
        return self._depth.shape[1]

    def get_height(self):
        return self._depth.shape[0]

    def get_depth_scale(self):
        return self._scale


def test_wait_for_complete_frames_skips_partial_framesets():
    pipeline = _FakePipeline([
        None,
        _FakeFrameSet(has_color=True, has_depth=False),
        _FakeFrameSet(has_color=False, has_depth=True),
        _FakeFrameSet(has_color=True, has_depth=True),
    ])

    frames = _wait_for_complete_frames(pipeline, timeout_ms=3000, poll_timeout_ms=100)

    assert frames.get_color_frame() is not None
    assert frames.get_depth_frame() is not None
    assert pipeline.calls == 4


def test_align_frames_to_color_uses_orbbec_align_filter():
    original = object()
    aligned = object()

    class FakeAlignFilter:
        def __init__(self, *, align_to_stream):
            assert align_to_stream == "color"

        def process(self, frames):
            assert frames is original
            return aligned

    obsdk = SimpleNamespace(
        AlignFilter=FakeAlignFilter,
        OBStreamType=SimpleNamespace(COLOR_STREAM="color"),
    )

    assert _align_frames_to_color(original, obsdk) is aligned


def test_apply_enabled_depth_filters_runs_only_enabled_filters_in_order():
    calls = []

    class FakeFiltered:
        def __init__(self, frame):
            self.frame = frame

        def as_depth_frame(self):
            return self.frame

    class FakeFilter:
        def __init__(self, name, enabled, output):
            self.name = name
            self.enabled = enabled
            self.output = output

        def is_enabled(self):
            return self.enabled

        def process(self, frame):
            calls.append((self.name, frame))
            return FakeFiltered(self.output)

    class FakeFilterList:
        filters = [
            FakeFilter("disabled", False, "unused"),
            FakeFilter("first", True, "b"),
            FakeFilter("second", True, "c"),
        ]

        def get_count(self):
            return len(self.filters)

        def get_filter(self, index):
            return self.filters[index]

    assert _apply_enabled_depth_filters("a", FakeFilterList()) == "c"
    assert calls == [("first", "a"), ("second", "b")]


def test_color_frame_to_bgr_decodes_mjpg_frames():
    bgr = np.zeros((4, 5, 3), dtype=np.uint8)
    bgr[:, :] = (10, 80, 200)
    ok, encoded = cv2.imencode(".jpg", bgr)
    assert ok
    obsdk = SimpleNamespace(OBFormat=SimpleNamespace(MJPG="mjpg", RGB="rgb", BGR="bgr", YUYV="yuyv"))
    frame = _FakeColorFrame(encoded.tobytes(), width=5, height=4, fmt=obsdk.OBFormat.MJPG)

    decoded = _color_frame_to_bgr(frame, obsdk)

    assert decoded.shape == (4, 5, 3)
    assert decoded.dtype == np.uint8


def test_color_frame_to_bgr_accepts_non_contiguous_ndarray_data():
    bgr = np.asfortranarray(
        np.array(
            [
                [[10, 20, 30], [40, 50, 60]],
                [[70, 80, 90], [100, 110, 120]],
            ],
            dtype=np.uint8,
        )
    )
    obsdk = SimpleNamespace(OBFormat=SimpleNamespace(MJPG="mjpg", RGB="rgb", BGR="bgr", YUYV="yuyv"))
    frame = _FakeColorFrame(bgr, width=2, height=2, fmt=obsdk.OBFormat.BGR)

    decoded = _color_frame_to_bgr(frame, obsdk)

    assert np.array_equal(decoded, bgr)


def test_profile_intrinsics_supports_current_orbbec_sdk_method_name():
    intrinsics = SimpleNamespace(fx=1.0, fy=2.0, cx=3.0, cy=4.0)
    profile = SimpleNamespace(get_intrinsic=lambda: intrinsics)

    assert _profile_intrinsics(profile) is intrinsics


def test_depth_frame_to_meters_converts_orbbec_millimeters_to_meters():
    raw = np.array([[252, 0], [1000, 65535]], dtype=np.uint16)
    frame = _FakeDepthFrame(raw, scale=1.0)

    depth_m = _depth_frame_to_meters(frame)

    assert depth_m.dtype == np.float32
    assert depth_m[0, 0] == np.float32(0.252)
    assert depth_m[1, 0] == np.float32(1.0)
    assert depth_m[1, 1] == np.float32(65.535)


def test_depth_frame_to_meters_accepts_non_contiguous_ndarray_data():
    class FakeDepthArrayFrame(_FakeDepthFrame):
        def get_data(self):
            return self._depth

    raw = np.asfortranarray(np.array([[252, 0], [1000, 65535]], dtype=np.uint16))
    frame = FakeDepthArrayFrame(raw, scale=1.0)

    depth_m = _depth_frame_to_meters(frame)

    assert depth_m.dtype == np.float32
    assert np.array_equal(
        depth_m,
        np.array([[0.252, 0.0], [1.0, 65.535]], dtype=np.float32),
    )


def test_robust_depth_uses_center_region_median_and_filters_invalid_values():
    depth = np.zeros((6, 6), dtype=np.float32)
    depth[2:4, 2:4] = np.array([[0.41, math.nan], [0.43, 5.0]], dtype=np.float32)

    sample = robust_depth_m(depth, bbox=(1, 1, 4, 4), min_depth_m=0.2, max_depth_m=1.0)

    assert sample.depth_m == 0.42
    assert sample.valid_count == 2
    assert sample.total_count == 4
    assert sample.valid_ratio == 0.5


def test_project_pixel_to_camera_uses_pinhole_intrinsics():
    intr = CameraIntrinsics(fx=600.0, fy=600.0, cx=320.0, cy=240.0)

    point = project_pixel_to_camera(u=350.0, v=210.0, depth_m=0.6, intrinsics=intr)

    assert point == (0.03, -0.03, 0.6)


def test_enrich_detection_estimates_metric_size_from_depth():
    intr = CameraIntrinsics(fx=600.0, fy=600.0, cx=320.0, cy=240.0)
    depth = np.full((480, 640), 0.6, dtype=np.float32)
    det = Detection2D(category="cube", color="yellow", bbox=(300, 220, 40, 30))

    obj = enrich_detection_with_depth(det, depth, intr)

    assert obj.distance_m == 0.6
    assert obj.point_camera == (0.0, -0.005, 0.6)
    assert obj.estimated_size_m.width == 0.04
    assert obj.estimated_size_m.height == 0.03
    assert obj.depth_valid_ratio == 1.0


def test_enrich_detection_uses_mask_point_cloud_centroid_instead_of_bbox_center():
    intr = CameraIntrinsics(fx=100.0, fy=100.0, cx=0.0, cy=0.0)
    depth = np.full((10, 10), 1.0, dtype=np.float32)
    mask = np.zeros((10, 10), dtype=np.uint8)
    mask[2:4, 6:8] = 255
    det = Detection2D(category="cube", color="yellow", bbox=(0, 0, 10, 10), mask=mask)

    obj = enrich_detection_with_depth(det, depth, intr)

    assert obj.point_camera == (0.065, 0.025, 1.0)
    assert obj.geometry_source == "mask_point_cloud_centroid"


def test_enrich_detection_uses_near_depth_surface_for_mask_geometry():
    intr = CameraIntrinsics(fx=500.0, fy=500.0, cx=50.0, cy=50.0)
    depth = np.full((120, 120), 0.29, dtype=np.float32)
    depth[30:90, 40:100] = 0.25
    mask = np.zeros((120, 120), dtype=np.uint8)
    mask[20:100, 20:100] = 255
    det = Detection2D(category="cube", color="yellow", bbox=(20, 20, 80, 80), mask=mask)

    obj = enrich_detection_with_depth(det, depth, intr)

    assert obj.point_camera == (0.00975, 0.00475, 0.25)
    assert obj.estimated_size_m == SizeEstimate(width=0.03, height=0.03)
    assert obj.geometry_source == "mask_point_cloud_centroid"


def test_depth_mask_centroid_camera_filters_invalid_depth_values():
    intr = CameraIntrinsics(fx=100.0, fy=100.0, cx=0.0, cy=0.0)
    depth = np.full((6, 6), 1.0, dtype=np.float32)
    depth[2, 4] = 0.0
    depth[3, 4] = 5.0
    mask = np.zeros((6, 6), dtype=np.uint8)
    mask[2:4, 4:6] = 255

    centroid, valid_count, total_count = depth_mask_centroid_camera(
        depth,
        mask,
        intr,
        min_depth_m=0.2,
        max_depth_m=2.0,
    )

    assert centroid == (0.05, 0.025, 1.0)
    assert valid_count == 2
    assert total_count == 4


def test_filter_detections_matches_color_category_and_actual_size_range():
    objs = [
        Detection2D(category="cube", color="yellow", bbox=(0, 0, 20, 20)),
        Detection2D(category="cube", color="red", bbox=(0, 0, 40, 40)),
        Detection2D(category="apple", color="red", bbox=(0, 0, 30, 30)),
    ]
    depth = np.full((100, 100), 0.6, dtype=np.float32)
    intr = CameraIntrinsics(fx=600.0, fy=600.0, cx=50.0, cy=50.0)

    matches = filter_detections(
        objs,
        depth,
        intr,
        category="cube",
        color="red",
        size_range=SizeRange(min_width=0.035, max_width=0.045),
    )

    assert len(matches) == 1
    assert matches[0].category == "cube"
    assert matches[0].color == "red"
    assert matches[0].estimated_size_m.width == 0.04
