---
name: gemini-depth-perception
description: Shared Orbbec Gemini 335 RGB-D object perception using color-size rules, YOLO segmentation, or Open3D-style point-cloud geometry to estimate camera-frame 3D objects without controlling a robot arm.
version: 0.1.0
author: dorarobotics
hardware_requirements: orbbec-gemini-335, pyorbbecsdk
---

# Gemini 335 Depth Perception

Use this skill for robot-agnostic RGB-D perception. It turns Gemini 335 RGB-D
frames into camera-frame `Object3D` results: object center, distance, estimated
metric size, confidence, and the geometry source used to produce the result.

This skill does not move any robot. Robot-specific skills should transform
`point_camera` into their own base frame using that robot's hand-eye calibration.

## Perception Backends

All backends should be hidden behind `octos_object_perception` and return the
same `Object3D` contract to robot-specific skills.

| Backend | Detector | Best use | Notes |
|---------|----------|----------|-------|
| Color-size rules | `color_size` | Colored cubes and high-contrast tabletop objects | RGB color mask -> depth geometry -> `Object3D` |
| YOLO segmentation | `yolo_seg` | Known semantic classes or open-vocabulary YOLO-style models | YOLO bbox/mask -> depth geometry -> `Object3D` |
| Prop detector | `prop_detector` | Demo props whose YOLO labels need remapping | Wrapper around `yolo_seg`, not a separate perception algorithm |
| Point-cloud geometry | `open3d_geometry` | Unknown isolated tabletop objects | RGB-D point cloud -> workspace crop -> table removal -> DBSCAN clusters -> OBB -> `Object3D` |

Use `open3d_geometry` when the task is "find the object on the table" rather
than "recognize a named class". It is more general and engineering-oriented, but
does not infer semantic labels such as cup, apple, or bottle.

## Tools

| Tool | Input | Output |
|------|-------|--------|
| `detect_objects` | `{"detector":"open3d_geometry","category":"object","workspace_bounds_m":{"x":[-0.3,0.3],"y":[-0.2,0.2],"z":[0.15,0.8]}}` | matching RGB-D detections |
| `locate_object_camera` | same as `detect_objects` | best matching object with `point_camera` |
| `get_object_distance` | same as `detect_objects` | best matching object distance and size |

`size_range_m` uses real dimensions in meters. Supported keys are
`min_width`, `max_width`, `min_height`, and `max_height`.

For `color_size`, current color support is `red`, `yellow`, `green`, `blue`, and
`black`. For `yolo_seg`, pass `yolo_model_path`, `yolo_classes`,
`yolo_confidence`, and `yolo_device`. For `open3d_geometry`, tune
`workspace_bounds_m`, `open3d_voxel_size_m`, `open3d_table_threshold_m`,
`open3d_dbscan_eps_m`, `open3d_dbscan_min_points`, and
`open3d_min_cluster_points`.

The Open3D-style backend is for separated tabletop objects with reliable depth.
It is not a good fit for transparent, reflective, heavily stacked, or touching
objects unless additional filtering is added.

## Open3D Geometry Diagnostics

Before using `open3d_geometry` for robot motion, run the single-frame diagnostic:

```bash
scripts/diagnose_open3d_geometry.py \
  --workspace-bounds-m '{"x":[-0.3,0.3],"y":[-0.25,0.25],"z":[0.15,0.8]}' \
  --dbscan-eps-m 0.025 \
  --min-cluster-points 80
```

The script captures one Gemini 335 RGB-D frame, runs the point-cloud geometry
backend, and writes `open3d_geometry_report.json`, `color_bgr.png`,
`depth_preview.png`, and `open3d_geometry_overlay.png` under
`/tmp/octos_open3d_geometry_diag` by default.

Tune the workspace first, then `open3d_table_threshold_m`, then DBSCAN settings.
The first milestone is stable one-object-in, one-cluster-out behavior.
