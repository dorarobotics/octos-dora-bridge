import sys
from types import SimpleNamespace

import numpy as np


def test_gemini335_camera_module_import_does_not_import_pyorbbecsdk():
    sys.modules.pop("pyorbbecsdk", None)

    from octos_camera.orbbec_gemini335 import Gemini335Camera

    assert Gemini335Camera(serial_number="test").serial_number == "test"
    assert "pyorbbecsdk" not in sys.modules


class _FakeColorFrame:
    def __init__(self, data, width: int, height: int, fmt: str) -> None:
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
        return self._depth

    def get_width(self):
        return self._depth.shape[1]

    def get_height(self):
        return self._depth.shape[0]

    def get_depth_scale(self):
        return self._scale


def test_color_frame_to_bgr_accepts_non_contiguous_ndarray_data():
    from octos_camera.orbbec_gemini335 import _color_frame_to_bgr

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


def test_depth_frame_to_meters_accepts_non_contiguous_ndarray_data():
    from octos_camera.orbbec_gemini335 import _depth_frame_to_meters

    raw = np.asfortranarray(np.array([[252, 0], [1000, 65535]], dtype=np.uint16))
    frame = _FakeDepthFrame(raw, scale=1.0)

    depth_m = _depth_frame_to_meters(frame)

    assert depth_m.dtype == np.float32
    assert np.array_equal(
        depth_m,
        np.array([[0.252, 0.0], [1.0, 65.535]], dtype=np.float32),
    )


def test_mjpg_color_decode_uses_owned_numpy_buffer(monkeypatch):
    from octos_camera.orbbec_gemini335 import _color_frame_to_bgr

    calls = []

    class FakeCv2:
        IMREAD_COLOR = 1
        COLOR_RGB2BGR = 2
        COLOR_YUV2BGR_YUYV = 3

        @staticmethod
        def imdecode(data, flags):
            calls.append((data.flags.owndata, flags))
            return np.zeros((2, 2, 3), dtype=np.uint8)

        @staticmethod
        def cvtColor(data, code):
            return data

    monkeypatch.setitem(sys.modules, "cv2", FakeCv2)
    obsdk = SimpleNamespace(OBFormat=SimpleNamespace(MJPG="mjpg", RGB="rgb", BGR="bgr", YUYV="yuyv"))
    data = np.arange(16, dtype=np.uint8).reshape(4, 4).reshape(-1)
    frame = _FakeColorFrame(data, width=2, height=2, fmt=obsdk.OBFormat.MJPG)

    decoded = _color_frame_to_bgr(frame, obsdk)

    assert decoded.shape == (2, 2, 3)
    assert calls == [(True, FakeCv2.IMREAD_COLOR)]
