from __future__ import annotations

from dataclasses import dataclass
import ctypes
import os
from pathlib import Path

import numpy as np

from .depth_geometry import CameraIntrinsics


@dataclass
class RgbdFrame:
    color_bgr: np.ndarray
    depth_m: np.ndarray
    intrinsics: CameraIntrinsics


def _wait_for_complete_frames(pipeline, timeout_ms: int, poll_timeout_ms: int = 300):
    import time

    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
        frames = pipeline.wait_for_frames(min(poll_timeout_ms, remaining_ms))
        if frames is None:
            continue
        if frames.get_color_frame() is not None and frames.get_depth_frame() is not None:
            return frames
    raise RuntimeError("Timed out waiting for complete Orbbec color+depth frames")


def _frame_data_array(frame, dtype) -> np.ndarray:
    raw = frame.get_data()
    if isinstance(raw, np.ndarray):
        data = np.ascontiguousarray(raw)
        if data.dtype == np.dtype(dtype):
            return data.reshape(-1)
        return data.view(dtype).reshape(-1)
    return np.frombuffer(raw, dtype=dtype)


def _color_frame_to_bgr(color_frame, obsdk) -> np.ndarray:
    import cv2

    width = color_frame.get_width()
    height = color_frame.get_height()
    fmt = color_frame.get_format()
    data = _frame_data_array(color_frame, np.uint8)
    if fmt == obsdk.OBFormat.MJPG:
        image = cv2.imdecode(data.copy(), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("Failed to decode Orbbec MJPG color frame")
        return image
    if fmt == obsdk.OBFormat.RGB:
        return cv2.cvtColor(data.reshape((height, width, 3)), cv2.COLOR_RGB2BGR)
    if fmt == obsdk.OBFormat.BGR:
        return data.reshape((height, width, 3))
    if fmt == obsdk.OBFormat.YUYV:
        return cv2.cvtColor(data.reshape((height, width, 2)), cv2.COLOR_YUV2BGR_YUYV)
    raise RuntimeError(f"Unsupported Orbbec color frame format: {fmt}")


def _profile_intrinsics(profile):
    if hasattr(profile, "get_intrinsic"):
        return profile.get_intrinsic()
    return profile.get_intrinsics()


def _depth_frame_to_meters(depth_frame) -> np.ndarray:
    depth_raw = _frame_data_array(depth_frame, np.uint16).reshape(
        depth_frame.get_height(), depth_frame.get_width()
    )
    scale_to_millimeters = float(getattr(depth_frame, "get_depth_scale", lambda: 1.0)())
    return depth_raw.astype(np.float32) * scale_to_millimeters * 0.001


def _align_frames_to_color(frames, obsdk, align_filter=None):
    align_filter = align_filter or obsdk.AlignFilter(
        align_to_stream=obsdk.OBStreamType.COLOR_STREAM
    )
    return align_filter.process(frames)


def _apply_enabled_depth_filters(depth_frame, filter_list):
    if filter_list is None:
        return depth_frame
    for index in range(filter_list.get_count()):
        post_filter = filter_list.get_filter(index)
        if post_filter and post_filter.is_enabled() and depth_frame is not None:
            filtered = post_filter.process(depth_frame)
            depth_frame = filtered.as_depth_frame()
    return depth_frame


def _video_profile(profile_list, width: int, height: int, fmt, fps: int):
    try:
        return profile_list.get_video_stream_profile(width, height, fmt, fps)
    except Exception:
        return profile_list.get_default_video_stream_profile()


class Gemini335Camera:
    """Minimal Orbbec Gemini 335 RGB-D capture wrapper.

    Importing this module does not require pyorbbecsdk; opening the camera does.
    """

    def __init__(self, serial_number: str | None = None) -> None:
        self.serial_number = serial_number
        self._pipeline = None
        self._color_profile = None
        self._depth_profile = None
        self._align_filter = None
        self._depth_filter_list = None

    @staticmethod
    def _preload_sdk() -> None:
        candidates = [
            os.environ.get("ORBBEC_SDK_LIB"),
            "/home/dora/.local/lib/python3.10/site-packages/libOrbbecSDK.so.1.10",
            "/home/dora/SDK/pyorbbecsdk/install/lib/libOrbbecSDK.so.1.10",
            "/home/dora/SDK/pyorbbecsdk/sdk/lib/linux_x64/libOrbbecSDK.so.1.10",
            "/home/dora/SDK/OrbbecViewer_v1.10.22_202504110154_linux_x64_release/lib/libOrbbecSDK.so.1.10",
            "/home/dora/so101-sim/venv/lib/python3.10/site-packages/libOrbbecSDK.so.1.10",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                ctypes.CDLL(str(candidate), mode=ctypes.RTLD_GLOBAL)
                return

    def open(self) -> None:
        self._preload_sdk()
        import pyorbbecsdk as obsdk

        ctx = obsdk.Context()
        devices = ctx.query_devices()
        if devices.get_count() == 0:
            raise RuntimeError("No Orbbec Gemini device found")
        device = None
        if self.serial_number:
            device = devices.get_device_by_serial_number(self.serial_number)
        if device is None:
            device = devices.get_device_by_index(0)

        pipeline = obsdk.Pipeline(device)
        config = obsdk.Config()
        depth_profiles = pipeline.get_stream_profile_list(obsdk.OBSensorType.DEPTH_SENSOR)
        if depth_profiles is None:
            raise RuntimeError("Orbbec device has no depth sensor profile")
        depth_profile = depth_profiles.get_default_video_stream_profile()
        config.enable_stream(depth_profile)

        color_profiles = pipeline.get_stream_profile_list(obsdk.OBSensorType.COLOR_SENSOR)
        if color_profiles is None:
            raise RuntimeError("Orbbec device has no color sensor profile")
        color_profile = _video_profile(
            color_profiles,
            width=depth_profile.get_width(),
            height=depth_profile.get_height(),
            fmt=obsdk.OBFormat.MJPG,
            fps=depth_profile.get_fps(),
        )
        config.enable_stream(color_profile)

        pipeline.start(config)
        try:
            pipeline.enable_frame_sync()
        except Exception:
            pass
        self._align_filter = obsdk.AlignFilter(align_to_stream=obsdk.OBStreamType.COLOR_STREAM)
        try:
            depth_sensor = device.get_sensor(obsdk.OBSensorType.DEPTH_SENSOR)
            self._depth_filter_list = depth_sensor.get_recommended_filters()
        except Exception:
            self._depth_filter_list = None
        self._pipeline = pipeline
        self._color_profile = color_profile
        self._depth_profile = depth_profile

    def close(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()
        self._pipeline = None
        self._color_profile = None
        self._depth_profile = None
        self._align_filter = None
        self._depth_filter_list = None

    def read(self, timeout_ms: int = 3000) -> RgbdFrame:
        self._preload_sdk()
        import pyorbbecsdk as obsdk

        if self._pipeline is None:
            self.open()
        frames = _wait_for_complete_frames(self._pipeline, timeout_ms)
        frames = _align_frames_to_color(frames, obsdk, self._align_filter)
        color_frame = frames.get_color_frame()
        depth_frame = frames.get_depth_frame()
        if color_frame is None or depth_frame is None:
            raise RuntimeError("Aligned Orbbec frames missing color or depth frame")
        depth_frame = _apply_enabled_depth_filters(depth_frame, self._depth_filter_list)
        color_bgr = _color_frame_to_bgr(color_frame, obsdk)
        depth_m = _depth_frame_to_meters(depth_frame)

        intr = _profile_intrinsics(self._color_profile)
        return RgbdFrame(
            color_bgr=color_bgr,
            depth_m=depth_m,
            intrinsics=CameraIntrinsics(
                fx=float(intr.fx),
                fy=float(intr.fy),
                cx=float(intr.cx),
                cy=float(intr.cy),
                width=int(color_frame.get_width()),
                height=int(color_frame.get_height()),
            ),
        )
