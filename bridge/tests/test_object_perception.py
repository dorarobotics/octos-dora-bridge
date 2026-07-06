import numpy as np

from octos_object_perception.detectors.color_size_detector import ColorSizeDetector
from octos_object_perception.detectors.open3d_geometry_detector import (
    Open3DGeometryDetector,
    ImageRoiFraction,
    _remove_largest_depth_plane,
)
from octos_object_perception.detectors.prop_detector import PropDetector
from octos_object_perception.detectors.yolo_seg_detector import YoloSegDetector
from octos_object_perception.depth_geometry import CameraIntrinsics, depth_mask_centroid_camera
from octos_object_perception.depth_geometry import enrich_detection_with_depth
from octos_object_perception.diagnostics import diagnose_color_size_frame, diagnose_detector_frame
from octos_object_perception.pipeline import ObjectPerceptionPipeline
from octos_object_perception.types import Detection2D, Object3D, SizeEstimate, SizeRange, TargetSpec


def test_size_range_contains_actual_metric_size():
    size_range = SizeRange(
        min_width=0.015,
        max_width=0.060,
        min_height=0.015,
        max_height=0.060,
    )

    assert size_range.contains(SizeEstimate(width=0.040, height=0.035))
    assert not size_range.contains(SizeEstimate(width=0.080, height=0.035))


def test_target_spec_builds_size_range_from_mapping():
    spec = TargetSpec.from_mapping(
        {
            "category": "cube",
            "color": "yellow",
            "size_range_m": {
                "min_width": 0.015,
                "max_width": 0.060,
                "min_height": 0.015,
                "max_height": 0.060,
            },
        }
    )

    assert spec.category == "cube"
    assert spec.color == "yellow"
    assert spec.size_range_m is not None
    assert spec.size_range_m.contains(SizeEstimate(width=0.040, height=0.040))


def test_target_spec_accepts_min_valid_ratio_from_mapping():
    spec = TargetSpec.from_mapping({"min_valid_ratio": 0.15})

    assert spec.min_valid_ratio == 0.15


def test_color_size_detector_returns_yellow_detection_with_mask():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[30:80, 40:95] = (0, 255, 255)

    detections = ColorSizeDetector(min_area_px=100).detect(
        frame,
        TargetSpec(category="cube", color="yellow"),
    )

    assert len(detections) == 1
    detection = detections[0]
    assert detection.category == "cube"
    assert detection.color == "yellow"
    assert detection.bbox == (40, 30, 55, 50)
    assert detection.mask is not None
    assert int(np.count_nonzero(detection.mask)) == 55 * 50


def test_color_size_detector_returns_orange_detection_with_mask():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[30:80, 40:95] = (0, 140, 255)

    detections = ColorSizeDetector(min_area_px=100).detect(
        frame,
        TargetSpec(category="cube", color="orange"),
    )

    assert len(detections) == 1
    assert detections[0].color == "orange"
    assert detections[0].bbox == (40, 30, 55, 50)


def test_yolo_seg_detector_converts_model_masks_to_detections():
    class FakeTensor:
        def __init__(self, value):
            self.value = np.asarray(value)

        def cpu(self):
            return self

        def numpy(self):
            return self.value

    class FakeBoxes:
        xyxy = FakeTensor([[10, 20, 50, 70], [80, 10, 120, 50]])
        conf = FakeTensor([0.8, 0.9])
        cls = FakeTensor([0, 1])

    class FakeMasks:
        data = FakeTensor(np.array([
            [[0, 0, 0], [0, 1, 1], [0, 1, 1]],
            [[1, 1, 0], [1, 1, 0], [0, 0, 0]],
        ], dtype=np.float32))

    class FakeResult:
        names = {0: "cup", 1: "bottle"}
        boxes = FakeBoxes()
        masks = FakeMasks()

    class FakeModel:
        def __call__(self, image, conf=0.25, verbose=False):
            return [FakeResult()]

    detections = YoloSegDetector(model=FakeModel(), class_names=["cup"]).detect(
        np.zeros((90, 160, 3), dtype=np.uint8),
        TargetSpec(category="cup"),
    )

    assert len(detections) == 1
    detection = detections[0]
    assert detection.category == "cup"
    assert detection.bbox == (10, 20, 40, 50)
    assert detection.confidence == 0.8
    assert detection.mask.shape == (90, 160)
    assert np.count_nonzero(detection.mask) > 0


def test_yolo_seg_detector_passes_requested_device_to_model():
    class FakeModel:
        def __init__(self):
            self.calls = []

        def __call__(self, image, **kwargs):
            self.calls.append(kwargs)
            return []

    model = FakeModel()

    YoloSegDetector(model=model, device="cpu").detect(
        np.zeros((90, 160, 3), dtype=np.uint8),
        TargetSpec(category="cup"),
    )

    assert model.calls == [{"conf": 0.25, "verbose": False, "device": "cpu"}]


def test_prop_detector_maps_yolo_toilet_candidate_to_requested_cup():
    class FakeDetector:
        def detect(self, frame_bgr, target):
            assert target.category is None
            return [
                Detection2D(
                    category="toilet",
                    color=None,
                    bbox=(10, 20, 40, 50),
                    confidence=0.9,
                    mask=np.ones((90, 160), dtype=np.uint8) * 255,
                )
            ]

    detections = PropDetector(base_detector=FakeDetector()).detect(
        np.zeros((90, 160, 3), dtype=np.uint8),
        TargetSpec(category="cup"),
    )

    assert len(detections) == 1
    assert detections[0].category == "cup"
    assert detections[0].bbox == (10, 20, 40, 50)
    assert detections[0].confidence == 0.9


def test_prop_detector_filters_unrelated_candidates_after_mapping():
    class FakeDetector:
        def detect(self, frame_bgr, target):
            return [
                Detection2D(category="person", color=None, bbox=(1, 2, 3, 4), confidence=0.7),
                Detection2D(category="toilet", color=None, bbox=(10, 20, 40, 50), confidence=0.9),
            ]

    detections = PropDetector(base_detector=FakeDetector()).detect(
        np.zeros((90, 160, 3), dtype=np.uint8),
        TargetSpec(category="cup"),
    )

    assert [d.category for d in detections] == ["cup"]
    assert detections[0].bbox == (10, 20, 40, 50)


def test_prop_detector_rejects_full_frame_alias_candidate():
    class FakeDetector:
        def detect(self, frame_bgr, target):
            return [
                Detection2D(category="toilet", color=None, bbox=(0, 0, 160, 90), confidence=0.9),
                Detection2D(category="mouse", color=None, bbox=(50, 20, 40, 40), confidence=0.8),
            ]

    detections = PropDetector(base_detector=FakeDetector(), max_bbox_area_ratio=0.8).detect(
        np.zeros((90, 160, 3), dtype=np.uint8),
        TargetSpec(category="cup"),
    )

    assert len(detections) == 1
    assert detections[0].category == "cup"
    assert detections[0].bbox == (50, 20, 40, 40)


def test_depth_mask_centroid_projects_valid_depth_pixels():
    depth = np.zeros((4, 4), dtype=np.float32)
    depth[1:3, 1:3] = 1.0
    mask = np.zeros((4, 4), dtype=np.uint8)
    mask[1:3, 1:3] = 255
    intrinsics = CameraIntrinsics(fx=100.0, fy=100.0, cx=1.5, cy=1.5, width=4, height=4)

    point, valid_count, total_count = depth_mask_centroid_camera(depth, mask, intrinsics)

    assert point == (0.0, 0.0, 1.0)
    assert valid_count == 4
    assert total_count == 4


def test_enrich_detection_uses_near_depth_surface_for_mask_geometry():
    depth = np.full((120, 120), 0.29, dtype=np.float32)
    depth[30:90, 40:100] = 0.25
    mask = np.zeros((120, 120), dtype=np.uint8)
    mask[20:100, 20:100] = 255
    intrinsics = CameraIntrinsics(fx=500.0, fy=500.0, cx=50.0, cy=50.0, width=120, height=120)
    detection = Detection2D(category="cube", color="yellow", bbox=(20, 20, 80, 80), mask=mask)

    obj = enrich_detection_with_depth(
        detection,
        depth,
        intrinsics,
        TargetSpec(category="cube", color="yellow"),
    )

    assert obj.point_camera == (0.00975, 0.00475, 0.25)
    assert obj.estimated_size_m == SizeEstimate(width=0.03, height=0.03)
    assert obj.geometry_source == "mask_point_cloud_centroid"


def test_pipeline_filters_by_metric_size_and_returns_best_object():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[30:70, 40:80] = (0, 255, 255)
    frame[20:110, 100:150] = (0, 255, 255)
    depth = np.full((120, 160), 0.4, dtype=np.float32)
    intrinsics = CameraIntrinsics(fx=400.0, fy=400.0, cx=80.0, cy=60.0, width=160, height=120)
    target = TargetSpec(
        category="cube",
        color="yellow",
        size_range_m=SizeRange(min_width=0.030, max_width=0.050, min_height=0.030, max_height=0.050),
    )

    objects = ObjectPerceptionPipeline(ColorSizeDetector(min_area_px=100)).detect(
        color_bgr=frame,
        depth_m=depth,
        intrinsics=intrinsics,
        target=target,
    )

    assert len(objects) == 1
    obj = objects[0]
    assert obj.category == "cube"
    assert obj.color == "yellow"
    assert obj.bbox == (40, 30, 40, 40)
    assert obj.distance_m == 0.4
    assert obj.estimated_size_m == SizeEstimate(width=0.04, height=0.04)
    assert obj.geometry_source == "mask_point_cloud_centroid"


def test_pipeline_accepts_direct_3d_backend_output():
    expected = Object3D(
        category="object",
        color=None,
        bbox=(0, 0, 1, 1),
        confidence=0.75,
        distance_m=0.42,
        point_camera=(0.1, 0.2, 0.42),
        estimated_size_m=SizeEstimate(width=0.04, height=0.03),
        depth_valid_ratio=1.0,
        geometry_source="fake_3d_backend",
    )

    class Fake3DBackend:
        def detect_3d(self, *, color_bgr, depth_m, intrinsics, target):
            assert target.category == "object"
            return [expected]

    objects = ObjectPerceptionPipeline(Fake3DBackend()).detect(
        color_bgr=np.zeros((10, 10, 3), dtype=np.uint8),
        depth_m=np.ones((10, 10), dtype=np.float32),
        intrinsics=CameraIntrinsics(fx=100.0, fy=100.0, cx=5.0, cy=5.0, width=10, height=10),
        target=TargetSpec(category="object"),
    )

    assert objects == [expected]


def test_open3d_geometry_detector_segments_tabletop_cluster():
    color = np.zeros((6, 8, 3), dtype=np.uint8)
    depth = np.full((6, 8), 0.40, dtype=np.float32)
    depth[2:4, 3:5] = 0.30
    intrinsics = CameraIntrinsics(fx=100.0, fy=100.0, cx=4.0, cy=3.0, width=8, height=6)

    detector = Open3DGeometryDetector(
        workspace_bounds_m={
            "x": (-0.05, 0.05),
            "y": (-0.05, 0.05),
            "z": (0.20, 0.50),
        },
        voxel_size_m=0.0,
        table_distance_threshold_m=0.002,
        dbscan_eps_m=0.025,
        dbscan_min_points=2,
        min_cluster_points=2,
    )

    objects = detector.detect_3d(
        color_bgr=color,
        depth_m=depth,
        intrinsics=intrinsics,
        target=TargetSpec(category="object", min_depth_m=0.20, max_depth_m=0.50),
    )

    assert len(objects) == 1
    obj = objects[0]
    assert obj.category == "object"
    assert obj.geometry_source == "open3d_tabletop_cluster_obb"
    assert obj.depth_valid_ratio == 1.0
    assert obj.distance_m == 0.3
    assert obj.point_camera == (0.0, 0.0, 0.3)
    assert obj.estimated_size_m.width > 0.0
    assert obj.estimated_size_m.height > 0.0


def test_open3d_geometry_cluster_target_uses_footprint_center_not_visible_centroid():
    color = np.zeros((80, 100, 3), dtype=np.uint8)
    depth = np.full((80, 100), 0.40, dtype=np.float32)
    depth[40:50, 40:60] = 0.30
    depth[45:50, 55:60] = 0.28
    intrinsics = CameraIntrinsics(fx=100.0, fy=100.0, cx=50.0, cy=40.0, width=100, height=80)

    detector = Open3DGeometryDetector(
        workspace_bounds_m={
            "x": (-0.10, 0.10),
            "y": (-0.05, 0.05),
            "z": (0.20, 0.50),
        },
        voxel_size_m=0.0,
        table_distance_threshold_m=0.004,
        dbscan_eps_m=0.035,
        dbscan_min_points=4,
        min_cluster_points=20,
    )

    objects = detector.detect_3d(
        color_bgr=color,
        depth_m=depth,
        intrinsics=intrinsics,
        target=TargetSpec(category="object", min_depth_m=0.20, max_depth_m=0.50),
    )

    assert len(objects) == 1
    obj = objects[0]
    visible_points = depth[40:50, 40:60]
    assert float(np.mean(visible_points)) < obj.distance_m
    assert obj.point_camera == (0.0, 0.015, 0.3)


def test_open3d_geometry_plane_removal_handles_tilted_tabletop():
    xs, ys = np.meshgrid(np.linspace(-0.12, 0.12, 25), np.linspace(-0.08, 0.08, 25))
    table_z = 0.40 + 0.12 * xs + 0.05 * ys
    table_points = np.column_stack([xs.ravel(), ys.ravel(), table_z.ravel()])
    table_pixels = np.column_stack([
        np.arange(table_points.shape[0]),
        np.zeros(table_points.shape[0], dtype=int),
    ])

    obj_xs, obj_ys = np.meshgrid(np.linspace(-0.025, 0.025, 7), np.linspace(-0.025, 0.025, 7))
    obj_plane_z = 0.40 + 0.12 * obj_xs + 0.05 * obj_ys
    object_points = np.column_stack([obj_xs.ravel(), obj_ys.ravel(), (obj_plane_z + 0.04).ravel()])
    object_pixels = np.column_stack([
        np.arange(object_points.shape[0]) + 1000,
        np.ones(object_points.shape[0], dtype=int),
    ])

    points = np.vstack([table_points, object_points])
    pixels = np.vstack([table_pixels, object_pixels])

    remaining_points, remaining_pixels = _remove_largest_depth_plane(points, pixels, threshold_m=0.006)

    del remaining_points
    table_remaining = np.count_nonzero(remaining_pixels[:, 0] < 1000)
    object_remaining = np.count_nonzero(remaining_pixels[:, 0] >= 1000)
    assert table_remaining < 20
    assert object_remaining >= 40


def test_open3d_geometry_detector_filters_clusters_by_target_color():
    color = np.zeros((80, 100, 3), dtype=np.uint8)
    color[30:45, 30:45] = (0, 140, 255)
    color[30:45, 65:80] = (150, 150, 150)
    depth = np.full((80, 100), 0.40, dtype=np.float32)
    depth[30:45, 30:45] = 0.30
    depth[30:45, 65:80] = 0.30
    intrinsics = CameraIntrinsics(fx=140.0, fy=140.0, cx=50.0, cy=40.0, width=100, height=80)

    detector = Open3DGeometryDetector(
        workspace_bounds_m={
            "x": (-0.10, 0.10),
            "y": (-0.05, 0.05),
            "z": (0.20, 0.50),
        },
        voxel_size_m=0.0,
        table_distance_threshold_m=0.004,
        dbscan_eps_m=0.012,
        dbscan_min_points=4,
        min_cluster_points=20,
    )

    objects = detector.detect_3d(
        color_bgr=color,
        depth_m=depth,
        intrinsics=intrinsics,
        target=TargetSpec(category="cube", color="orange", min_depth_m=0.20, max_depth_m=0.50),
    )

    assert len(objects) == 1
    assert objects[0].color == "orange"
    assert objects[0].bbox == (30, 30, 15, 15)


def test_open3d_geometry_detector_uses_color_component_size_for_sparse_depth_target():
    color = np.zeros((100, 120, 3), dtype=np.uint8)
    color[35:70, 45:85] = (0, 140, 255)
    depth = np.zeros((100, 120), dtype=np.float32)
    depth[48:54, 58:64] = 0.30
    intrinsics = CameraIntrinsics(fx=120.0, fy=120.0, cx=60.0, cy=50.0, width=120, height=100)

    detector = Open3DGeometryDetector(
        workspace_bounds_m={
            "x": (-0.10, 0.10),
            "y": (-0.05, 0.10),
            "z": (0.20, 0.50),
        },
        voxel_size_m=0.0,
        dbscan_eps_m=0.02,
        dbscan_min_points=2,
        min_cluster_points=4,
    )

    objects = detector.detect_3d(
        color_bgr=color,
        depth_m=depth,
        intrinsics=intrinsics,
        target=TargetSpec(
            category="cube",
            color="orange",
            size_range_m=SizeRange(min_width=0.06, min_height=0.06),
            min_depth_m=0.20,
            max_depth_m=0.50,
        ),
    )

    assert len(objects) == 1
    assert objects[0].bbox == (45, 35, 40, 35)
    assert objects[0].estimated_size_m == SizeEstimate(width=0.1, height=0.0875)


def test_open3d_geometry_detector_can_exclude_bottom_foreground_by_image_roi():
    color = np.zeros((100, 120, 3), dtype=np.uint8)
    depth = np.full((100, 120), 0.40, dtype=np.float32)
    depth[35:55, 45:75] = 0.30
    depth[80:95, 40:80] = 0.30
    intrinsics = CameraIntrinsics(fx=120.0, fy=120.0, cx=60.0, cy=50.0, width=120, height=100)

    detector = Open3DGeometryDetector(
        workspace_bounds_m={
            "x": (-0.20, 0.20),
            "y": (-0.20, 0.20),
            "z": (0.20, 0.50),
        },
        image_roi_fraction=ImageRoiFraction(y_max=0.75),
        voxel_size_m=0.0,
        table_distance_threshold_m=0.004,
        dbscan_eps_m=0.025,
        dbscan_min_points=4,
        min_cluster_points=20,
    )

    objects = detector.detect_3d(
        color_bgr=color,
        depth_m=depth,
        intrinsics=intrinsics,
        target=TargetSpec(category="object", min_depth_m=0.20, max_depth_m=0.50),
    )

    assert len(objects) == 1
    assert objects[0].bbox == (45, 35, 30, 20)


def test_diagnose_color_size_frame_reports_matching_and_rejected_candidates():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[:, :] = (0, 120, 60)
    frame[30:70, 40:80] = (0, 255, 255)
    frame[20:110, 100:150] = (0, 255, 255)
    depth = np.full((120, 160), 0.4, dtype=np.float32)
    intrinsics = CameraIntrinsics(fx=400.0, fy=400.0, cx=80.0, cy=60.0, width=160, height=120)
    target = TargetSpec(
        category="cube",
        color="yellow",
        size_range_m=SizeRange(min_width=0.030, max_width=0.050, min_height=0.030, max_height=0.050),
    )

    report = diagnose_color_size_frame(
        color_bgr=frame,
        depth_m=depth,
        intrinsics=intrinsics,
        target=target,
        min_area_px=100,
    )

    assert report["target"] == {"category": "cube", "color": "yellow"}
    assert report["summary"]["yellow"]["detections_2d"] == 2
    assert report["summary"]["yellow"]["matches"] == 1
    assert report["summary"]["yellow"]["rejected"] == 1
    assert report["matches"][0]["bbox"] == [40, 30, 40, 40]
    assert report["rejected"][0]["reason"] == "size_range"


def test_diagnose_color_size_frame_reports_absent_target_color():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[:, :] = (0, 120, 60)
    depth = np.full((120, 160), 0.4, dtype=np.float32)
    intrinsics = CameraIntrinsics(fx=400.0, fy=400.0, cx=80.0, cy=60.0, width=160, height=120)

    report = diagnose_color_size_frame(
        color_bgr=frame,
        depth_m=depth,
        intrinsics=intrinsics,
        target=TargetSpec(category="cube", color="yellow"),
        min_area_px=100,
    )

    assert report["summary"]["yellow"]["detections_2d"] == 0
    assert report["matches"] == []


def test_diagnose_detector_frame_reports_detector_matches():
    class FakeDetector:
        def detect(self, color_bgr, target):
            mask = np.zeros((120, 160), dtype=np.uint8)
            mask[30:70, 40:80] = 255
            return [
                Detection2D(
                    category="cup",
                    color=None,
                    bbox=(40, 30, 40, 40),
                    confidence=0.9,
                    mask=mask,
                )
            ]

    depth = np.full((120, 160), 0.4, dtype=np.float32)
    intrinsics = CameraIntrinsics(fx=400.0, fy=400.0, cx=80.0, cy=60.0, width=160, height=120)

    report = diagnose_detector_frame(
        detector=FakeDetector(),
        color_bgr=np.zeros((120, 160, 3), dtype=np.uint8),
        depth_m=depth,
        intrinsics=intrinsics,
        target=TargetSpec(category="cup"),
    )

    assert report["summary"] == {"cup": {"detections_2d": 1, "matches": 1, "rejected": 0}}
    assert report["matches"][0]["category"] == "cup"
