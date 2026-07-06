---
name: so101-depth-pick
description: SO101 pick-and-place skill using Orbbec Gemini 335 depth for colored object distance, real metric size filtering, camera-frame localization, SO101 base-frame conversion, and grasp execution.
version: 0.1.0
author: dorarobotics
robot_type: so101
required_safety_tier: safe_motion
hardware_requirements: so-arm101, feetech-sts3215, orbbec-gemini-335, dora-moveit2 runtime
init:
  - label: start dora bridge dataflow
    command: |
      bash -lc 'for f in "${OCTOS_DORA_BRIDGE:-}/scripts/start_bridge.sh" "$PWD/scripts/start_bridge.sh" "$PWD/../../scripts/start_bridge.sh" "$HOME/.octos/skills/skills/octos-dora-bridge/scripts/start_bridge.sh"; do [ -x "$f" ] && OCTOS_ROBOT=so101 "$f"; done; echo "scripts/start_bridge.sh not found" >&2; exit 1'
    timeout_secs: 90
    critical: true
ready_check:
  - label: bridge HTTP responds
    command: |
      bash -lc 'NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost curl -fsS -m 2 http://127.0.0.1:8768/healthz'
    timeout_secs: 3
    retries: 10
    critical: true
shutdown:
  - label: stop dora dataflow
    command: |
      bash -lc 'for f in "${OCTOS_DORA_BRIDGE:-}/scripts/stop_bridge.sh" "$PWD/scripts/stop_bridge.sh" "$PWD/../../scripts/stop_bridge.sh" "$HOME/.octos/skills/skills/octos-dora-bridge/scripts/stop_bridge.sh"; do [ -x "$f" ] && "$f"; done; echo "scripts/stop_bridge.sh not found" >&2; exit 0'
    timeout_secs: 10
    critical: false
---

# SO101 Depth Pick

Use this skill to pick tabletop objects with an SO101 arm and Orbbec Gemini 335.
The perception path uses the bridge-level `octos_object_perception` package:
RGB detects candidates, depth points inside the object mask estimate the 3D
geometry center and real size, then this skill transforms the camera-frame point
into the SO101 base frame and executes motion through the dora bridge.

The grasp strategy uses the bridge-level `octos_grasp_planning` boundary. The
current workflow still uses a geometry top-down grasp; future AnyGrasp support
should be added behind that boundary, not inside this skill's motion code.

For colored cubes, `point_camera` and `point_base` are the mask point-cloud
centroid when the detector can build an object mask. The output includes
`geometry_source: "mask_point_cloud_centroid"` in that case. If a detector has no
mask, the skill falls back to the older bbox-center depth path and reports
`geometry_source: "bbox_center_depth"`.

This skill does not own perception algorithms. Select the perception backend with
`detector` and consume the unified `Object3D` output:

| Detector | Backend role |
|----------|--------------|
| `color_size` | Color mask + depth geometry for colored cubes/objects |
| `yolo_seg` | YOLO bbox/mask + depth geometry for semantic targets |
| `prop_detector` | YOLO wrapper that remaps demo prop labels |
| `open3d_geometry` | RGB-D point-cloud geometry for unknown separated tabletop objects |

Use `open3d_geometry` for model-free tabletop localization. It returns direct 3D
clusters with `geometry_source: "open3d_tabletop_cluster_obb"` and works best
when objects are separated and depth is reliable.

Current SO101 + Gemini 335 open3d debugging notes, measured perception poses,
and remaining TODOs are tracked in `PROGRESS_zh.md`.

## Target Selection

Use actual metric ranges instead of names like small/medium/large:

```json
{
  "category": "cube",
  "color": "yellow",
  "size_range_m": {
    "min_width": 0.025,
    "max_width": 0.040,
    "min_height": 0.025,
    "max_height": 0.040
  }
}
```

Current category support is `cube`; the interface is prepared for later props
such as `apple` and `pear`. The original `octos_depth_perception` code remains
in the repository as a reference path, but new object recognition should be
implemented in `octos_object_perception`.

## Tools

| Tool | Purpose |
|------|---------|
| `detect_objects` | Gemini 335 RGB-D detections in camera frame |
| `locate_object_camera` | Best match with `point_camera`, `geometry_source`, distance, and estimated size |
| `locate_object_base` | Best match transformed into SO101 base frame |
| `grasp_object` | Detect, locate, transform, and grasp the matching object |
| `pick_cube_at` | Low-level SO101 pick at explicit base-frame coordinates |
| `set_gripper` | Open or close the SO101 gripper |
| `pick_yellow_to_black_box` | Full workflow: detect yellow cube, grasp with table-safe height, locate black box, place, release, retract |

## Safe SO101 Cube Workflow

Use `pick_yellow_to_black_box` for the command "抓取黄色方块放到黑色盒子".
It does not lower to `point_base.z` directly. Instead it uses the detected cube
height and a `table_clearance_m` guard so the SO101 gripper body does not hit the
table while closing around small cubes.

## Calibration

`locate_object_base` and `grasp_object` require hand-eye calibration. The skill
looks for `SO101_DEPTH_HAND_EYE`, then `skills/so101-depth-pick/calibration/hand_eye.json`,
then the existing `SKILL_PACK/calibration/hand_eye.json`.
