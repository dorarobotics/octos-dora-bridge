from __future__ import annotations

import importlib.util
import json
import os
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import numpy as np

from octos_object_perception.types import Object3D, SizeEstimate


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_MAIN = REPO_ROOT / "skills" / "so101-depth-pick" / "main"
SKILL_MANIFEST = REPO_ROOT / "skills" / "so101-depth-pick" / "manifest.json"


def _load_skill_main():
    loader = SourceFileLoader("so101_depth_pick_main", str(SKILL_MAIN))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_so101_depth_pick_runtime_defaults_do_not_use_adora_skill(monkeypatch):
    for key in ("SKILL_PACK", "MODEL_NAME", "ROBOT_MANIFEST"):
        monkeypatch.delenv(key, raising=False)

    main = _load_skill_main()

    skill_pack = main.configure_so101_runtime()

    assert "Adora-RGB-pick" not in str(skill_pack)
    assert os.environ["SKILL_PACK"].endswith("moveit-arm-dora-node/skill_pack")
    assert os.environ["MODEL_NAME"].endswith("dora-moveit2/examples/move_group_demo/models/so101_pickplace.xml")
    assert os.environ["ROBOT_MANIFEST"].endswith("rebot-hw-dora-node/manifests/so101-hw.json")
    assert "Adora-RGB-pick" not in os.environ["MODEL_NAME"]
    assert "Adora-RGB-pick" not in os.environ["ROBOT_MANIFEST"]


def test_so101_depth_pick_main_uses_new_perception_packages():
    source = SKILL_MAIN.read_text()

    assert "octos_depth_perception" not in source
    assert "octos_depth_perception.object_detector" not in source
    assert "octos_depth_perception.depth_geometry" not in source
    assert "octos_object_perception" in source
    assert "octos_camera" in source


def test_so101_depth_pick_rejects_unsupported_detector():
    main = _load_skill_main()

    try:
        main.validate_detector({"detector": "yolo"})
    except ValueError as exc:
        assert "unsupported detector" in str(exc)
    else:
        raise AssertionError("unsupported detector should fail")


def test_so101_depth_pick_accepts_anygrasp_planner():
    main = _load_skill_main()

    assert main.validate_grasp_planner({"grasp_planner": "anygrasp"}) == "anygrasp"


def test_so101_depth_pick_accepts_yolo_seg_detector():
    main = _load_skill_main()

    assert main.validate_detector({"detector": "yolo_seg"}) == "yolo_seg"
    assert main.validate_detector({"detector": "prop_detector"}) == "prop_detector"
    assert main.validate_detector({"detector": "open3d_geometry"}) == "open3d_geometry"


def test_so101_depth_pick_profile_merges_defaults_with_call_args(monkeypatch, tmp_path):
    main = _load_skill_main()
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (profiles_dir / "orange_cube_5cm_open3d.json").write_text(
        json.dumps(
            {
                "detector": "open3d_geometry",
                "category": "object",
                "object_height_m": 0.05,
                "size_range_m": {
                    "min_width": 0.045,
                    "max_width": 0.095,
                    "min_height": 0.045,
                    "max_height": 0.095,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(main, "SKILL_DIR", tmp_path)

    resolved = main.resolve_profile_args(
        {
            "profile": "orange_cube_5cm_open3d",
            "object_height_m": 0.06,
            "show_viewer": True,
        }
    )

    assert resolved["profile"] == "orange_cube_5cm_open3d"
    assert resolved["detector"] == "open3d_geometry"
    assert resolved["category"] == "object"
    assert resolved["object_height_m"] == 0.06
    assert resolved["show_viewer"] is True
    assert resolved["size_range_m"]["min_width"] == 0.045


def test_so101_depth_pick_rejects_profile_path_traversal():
    main = _load_skill_main()

    try:
        main.load_profile("../secret")
    except ValueError as exc:
        assert "profile must be a simple name" in str(exc)
    else:
        raise AssertionError("unsafe profile names should fail")


def test_yolo_class_names_ignores_empty_entries(monkeypatch):
    main = _load_skill_main()
    monkeypatch.setenv("YOLO_CLASSES", "cup, water bottle, ")

    assert main.yolo_class_names({}) == ["cup", "water bottle"]
    assert main.yolo_class_names({"yolo_classes": ["cup", "", "apple"]}) == ["cup", "apple"]


def test_so101_depth_pick_rejects_unknown_grasp_planner():
    main = _load_skill_main()

    try:
        main.validate_grasp_planner({"grasp_planner": "unknown"})
    except ValueError as exc:
        assert "unsupported grasp_planner" in str(exc)
    else:
        raise AssertionError("unsupported grasp_planner should fail")


def test_so101_depth_pick_manifest_exposes_strategy_parameters():
    manifest = json.loads(SKILL_MANIFEST.read_text())
    tool_props = {
        tool["name"]: tool["input_schema"].get("properties", {})
        for tool in manifest["tools"]
    }

    expected_detectors = ["color_size", "prop_detector", "yolo_seg", "open3d_geometry"]
    for tool_name in ("detect_objects", "locate_object_camera", "locate_object_base", "grasp_object"):
        assert tool_props[tool_name]["profile"]["type"] == "string"
        assert tool_props[tool_name]["detector"]["enum"] == expected_detectors
    assert tool_props["diagnose_perception"]["profile"]["type"] == "string"
    assert tool_props["diagnose_perception"]["detector"]["enum"] == expected_detectors
    assert tool_props["grasp_object"]["object_height_m"]["default"] == 0.03
    assert tool_props["grasp_object"]["grasp_height_ratio"]["default"] == 0.35
    assert tool_props["grasp_object"]["min_grasp_clearance_m"]["default"] == 0.008
    assert tool_props["plan_grasp_camera"]["detector"]["enum"] == expected_detectors
    assert tool_props["plan_grasp_camera"]["grasp_planner"]["enum"] == ["geometry_topdown", "anygrasp"]
    assert tool_props["plan_grasp_camera"]["profile"]["type"] == "string"
    assert tool_props["pick_yellow_to_black_box"]["detector"]["enum"] == expected_detectors
    assert tool_props["pick_yellow_to_black_box"]["grasp_planner"]["enum"] == ["geometry_topdown", "anygrasp"]
    assert tool_props["pick_yellow_to_black_box"]["profile"]["type"] == "string"


def test_so101_depth_pick_monitor_overlay_draws_stage_and_objects():
    main = _load_skill_main()
    frame = np.zeros((120, 180, 3), dtype=np.uint8)
    obj = Object3D(
        category="cube",
        color="orange",
        bbox=(40, 30, 50, 35),
        confidence=0.82,
        distance_m=0.41,
        point_camera=(0.07, 0.06, 0.41),
        estimated_size_m=SizeEstimate(width=0.034, height=0.028),
        depth_valid_ratio=0.71,
        geometry_source="mask_point_cloud_centroid",
    )

    overlay = main.draw_pick_monitor_overlay(
        frame,
        [obj],
        stage="detect orange cube",
        base_points={"target": [0.388, -0.028, 0.015]},
    )

    assert overlay.shape == frame.shape
    assert np.count_nonzero(overlay) > 0
    assert np.count_nonzero(overlay[30:66, 40:91]) > 0


def test_so101_depth_pick_manifest_exposes_monitor_options():
    manifest = json.loads(SKILL_MANIFEST.read_text())
    tool_props = {
        tool["name"]: tool["input_schema"].get("properties", {})
        for tool in manifest["tools"]
    }

    for tool_name in ("grasp_object", "pick_yellow_to_black_box"):
        props = tool_props[tool_name]
        assert props["show_viewer"]["type"] == "boolean"
        assert props["show_viewer"]["default"] is False
        assert props["viewer_live"]["type"] == "boolean"
        assert props["viewer_live"]["default"] is False
        assert props["viewer_max_fps"]["type"] == "number"
        assert props["viewer_window"]["type"] == "string"
        assert props["viewer_save_path"]["type"] == "string"


def test_pick_monitor_live_loop_updates_overlay_and_stops(monkeypatch, tmp_path):
    main = _load_skill_main()
    writes = []

    fake_cv2 = types.SimpleNamespace(
        WINDOW_NORMAL=0,
        namedWindow=lambda *args, **kwargs: None,
        imshow=lambda *args, **kwargs: None,
        waitKey=lambda *args, **kwargs: None,
        destroyWindow=lambda *args, **kwargs: None,
        imwrite=lambda path, image: writes.append((path, int(np.count_nonzero(image)))) or True,
        rectangle=lambda *args, **kwargs: None,
        putText=lambda image, text, org, *args, **kwargs: image.__setitem__((slice(0, 1), slice(0, 1), slice(None)), 255),
        FONT_HERSHEY_SIMPLEX=0,
    )
    monkeypatch.setitem(__import__("sys").modules, "cv2", fake_cv2)

    frame = types.SimpleNamespace(color_bgr=np.zeros((40, 60, 3), dtype=np.uint8))
    obj = Object3D(
        category="object",
        color=None,
        bbox=(10, 8, 20, 18),
        confidence=1.0,
        distance_m=0.39,
        point_camera=(0.08, 0.06, 0.39),
        estimated_size_m=SizeEstimate(width=0.05, height=0.05),
        depth_valid_ratio=1.0,
        geometry_source="open3d_tabletop_cluster_obb",
    )
    calls = {"count": 0}

    def fake_capture(args):
        calls["count"] += 1
        return frame, [obj]

    monkeypatch.setattr(main, "capture_frame_objects", fake_capture)
    monitor = main.PickMonitor(
        {
            "show_viewer": True,
            "viewer_live": True,
            "viewer_max_fps": 200,
            "viewer_save_path": str(tmp_path / "live.png"),
        }
    )
    monitor.update("move above grasp", base_points={"grasp": [0.39, -0.04, 0.025]})
    monitor.start_live({"detector": "open3d_geometry"})
    main.time.sleep(0.03)
    monitor.close()

    assert calls["count"] > 0
    assert writes
    assert monitor._live_thread is None or not monitor._live_thread.is_alive()


def test_so101_depth_pick_manifest_exposes_yolo_parameters():
    manifest = json.loads(SKILL_MANIFEST.read_text())
    tool_props = {
        tool["name"]: tool["input_schema"].get("properties", {})
        for tool in manifest["tools"]
    }
    detector_tools = (
        "detect_objects",
        "diagnose_perception",
        "locate_object_camera",
        "locate_object_base",
        "grasp_object",
        "plan_grasp_camera",
        "pick_yellow_to_black_box",
    )

    for tool_name in detector_tools:
        props = tool_props[tool_name]
        assert props["yolo_model_path"]["type"] == "string"
        assert props["yolo_confidence"]["type"] == "number"
        assert props["yolo_confidence"]["default"] == 0.25
        assert props["yolo_device"]["type"] == "string"
        assert props["yolo_device"]["default"] == "cpu"
        assert props["yolo_classes"]["type"] == "array"


def test_so101_depth_pick_manifest_exposes_open3d_image_roi_parameter():
    manifest = json.loads(SKILL_MANIFEST.read_text())
    tool_props = {
        tool["name"]: tool["input_schema"].get("properties", {})
        for tool in manifest["tools"]
    }
    detector_tools = (
        "detect_objects",
        "diagnose_perception",
        "locate_object_camera",
        "locate_object_base",
        "grasp_object",
        "plan_grasp_camera",
        "pick_yellow_to_black_box",
    )

    for tool_name in detector_tools:
        props = tool_props[tool_name]
        assert props["open3d_image_roi_fraction"]["type"] == "object"


def test_so101_depth_pick_manifest_exposes_perception_pose_for_base_workflows():
    manifest = json.loads(SKILL_MANIFEST.read_text())
    tool_props = {
        tool["name"]: tool["input_schema"].get("properties", {})
        for tool in manifest["tools"]
    }

    for tool_name in ("locate_object_base", "grasp_object", "pick_yellow_to_black_box"):
        props = tool_props[tool_name]
        assert props["move_to_perception_pose"]["type"] == "boolean"
        assert props["perception_pose_name"]["type"] == "string"
        assert props["perception_joint_state"]["type"] == "array"
        assert props["perception_pose_timeout_s"]["type"] == "number"


def test_so101_bridge_dataflow_template_uses_rebot_hw_manifest():
    dataflow = (REPO_ROOT / "dataflows" / "so101-hw-bridge.yaml").read_text()

    assert "${REBOT_HW_NODE}/manifests/so101-hw.json" in dataflow
    assert "Adora-RGB-pick" not in dataflow


def test_redirect_native_stdout_to_stderr_keeps_json_stdout_clean(capfd):
    main = _load_skill_main()

    with main.redirect_native_stdout_to_stderr():
        os.write(1, b"orbbec native log\n")
    print('{"success": true}')

    out, err = capfd.readouterr()
    assert out == '{"success": true}\n'
    assert "orbbec native log" in err


def test_project_camera_point_to_table_plane_uses_known_so101_mount_height():
    main = _load_skill_main()
    transform = np.eye(4)
    transform[:3, 3] = [0.0, 0.0, 0.10]

    point = main.project_camera_point_to_base_plane(
        point_camera=(0.10, 0.00, -1.00),
        t_base_to_cam=transform,
        plane_z=-0.15,
    )

    assert point == [0.025, 0.0, -0.15]


def test_build_grasp_points_uses_table_plane_and_object_height():
    main = _load_skill_main()

    points = main.build_grasp_points(
        table_point=[0.20, 0.10, -0.15],
        object_height_m=0.06,
        approach_clearance_m=0.08,
    )

    assert points["point_base"] == [0.2, 0.1, -0.12]
    assert points["point_base_table"] == [0.2, 0.1, -0.15]
    assert points["approach_point_base"] == [0.2, 0.1, -0.04]


def test_default_base_xy_offset_is_zero_for_direct_table_mount():
    main = _load_skill_main()

    corrected = main.apply_base_xy_offset(
        table_point=[0.321447, -0.036054, 0.0],
        x_offset_m=main.DEFAULT_BASE_X_OFFSET_M,
        y_offset_m=main.DEFAULT_BASE_Y_OFFSET_M,
    )

    assert corrected == [0.321447, -0.036054, 0.0]


def test_apply_base_xy_offset_uses_explicit_pick_correction():
    main = _load_skill_main()

    corrected = main.apply_base_xy_offset(
        table_point=[0.321447, -0.036054, 0.0],
        x_offset_m=-0.015,
        y_offset_m=0.070,
    )

    assert corrected == [0.306447, 0.033946, 0.0]


def test_build_grasp_points_keeps_grasp_center_above_table():
    main = _load_skill_main()

    points = main.build_grasp_points(
        table_point=[0.215862, 0.117883, -0.15],
        object_height_m=0.065805,
        approach_clearance_m=0.08,
    )

    assert points["point_base"] == [0.215862, 0.117883, -0.117097]
    assert points["point_base_table"] == [0.215862, 0.117883, -0.15]
    assert points["approach_point_base"] == [0.215862, 0.117883, -0.037097]


def test_safe_grasp_z_uses_lower_middle_of_known_cube_height():
    main = _load_skill_main()

    z = main.safe_grasp_z(
        {
            "table_z": -0.15,
            "estimated_size_m": {"height": 0.038},
        },
        {
            "object_height_m": 0.03,
            "grasp_height_ratio": 0.4,
            "min_grasp_clearance_m": 0.008,
        },
    )

    assert z == -0.138


def test_safe_grasp_z_defaults_cube_to_three_centimeters():
    main = _load_skill_main()

    z = main.safe_grasp_z(
        {
            "category": "cube",
            "table_z": 0.0,
            "estimated_size_m": {"height": 0.015},
        },
        {
            "grasp_height_ratio": 0.4,
            "min_grasp_clearance_m": 0.008,
        },
    )

    assert z == 0.012


def test_safe_grasp_z_default_ratio_grasps_below_cube_midline():
    main = _load_skill_main()

    z = main.safe_grasp_z(
        {
            "category": "cube",
            "table_z": 0.0,
            "estimated_size_m": {"height": 0.015},
        },
        {},
    )

    assert z == 0.0105


def test_move_to_pose_waits_for_arm_settle(monkeypatch):
    main = _load_skill_main()
    calls = []

    monkeypatch.setattr(main, "bridge_tool", lambda name, args, timeout=45.0: calls.append(name) or {})
    monkeypatch.setattr(main, "wait_for_arm_settle", lambda: calls.append("wait"))

    main.move_to_pose([0.1, 0.2, 0.3])

    assert calls == ["vendor.moveit.arm.move_to_pose", "wait"]


def test_locate_base_moves_to_named_perception_pose_before_capture(monkeypatch):
    main = _load_skill_main()
    calls = []
    obj = Object3D(
        category="object",
        color=None,
        bbox=(1, 2, 30, 40),
        confidence=1.0,
        distance_m=0.35,
        point_camera=(0.01, 0.02, 0.35),
        estimated_size_m=SizeEstimate(width=0.05, height=0.05),
        depth_valid_ratio=1.0,
        geometry_source="open3d_tabletop_cluster_obb",
    )

    monkeypatch.setattr(main, "move_to_named_pose", lambda name, timeout=45.0: calls.append(("move", name)))
    monkeypatch.setattr(
        main,
        "capture_frame_objects",
        lambda args: calls.append(("capture", args.get("perception_pose_name"))) or (None, [obj]),
    )
    monkeypatch.setattr(main, "_object_to_base_data", lambda best, args: {"point_base": [0.3, 0.0, 0.025]})

    result = main.locate_base({"perception_pose_name": "perception", "move_to_perception_pose": True})

    assert result["point_base"] == [0.3, 0.0, 0.025]
    assert calls == [("move", "perception"), ("capture", "perception")]


def test_locate_base_can_move_to_joint_perception_pose_before_capture(monkeypatch):
    main = _load_skill_main()
    calls = []
    obj = Object3D(
        category="object",
        color=None,
        bbox=(1, 2, 30, 40),
        confidence=1.0,
        distance_m=0.35,
        point_camera=(0.01, 0.02, 0.35),
        estimated_size_m=SizeEstimate(width=0.05, height=0.05),
        depth_valid_ratio=1.0,
        geometry_source="open3d_tabletop_cluster_obb",
    )

    monkeypatch.setattr(
        main,
        "move_to_joint_state",
        lambda joints, timeout=45.0, timeout_joint_tolerance_rad=None: calls.append(
            ("move_joints", joints, timeout_joint_tolerance_rad)
        ),
    )
    monkeypatch.setattr(main, "move_to_named_pose", lambda name, timeout=45.0: calls.append(("move_named", name)))
    monkeypatch.setattr(main, "capture_frame_objects", lambda args: calls.append(("capture", True)) or (None, [obj]))
    monkeypatch.setattr(main, "_object_to_base_data", lambda best, args: {"point_base": [0.3, 0.0, 0.025]})

    joints = [-0.1, -0.8, 0.4, 1.2, -0.5]
    result = main.locate_base(
        {
            "move_to_perception_pose": True,
            "perception_joint_state": joints,
            "perception_joint_tolerance_rad": 0.035,
        }
    )

    assert result["point_base"] == [0.3, 0.0, 0.025]
    assert calls == [("move_joints", joints, 0.035), ("capture", True)]


def test_move_to_joint_state_accepts_timeout_when_actual_joints_reached_and_releases(monkeypatch):
    main = _load_skill_main()
    target = [-0.1, -0.8, 0.4, 1.2, -0.5]
    calls = []

    def fake_bridge_tool(name, args, timeout=45.0):
        calls.append((name, args))
        if name == "vendor.moveit.arm.move_to_joint_state":
            raise TimeoutError("timed out")
        return {}

    monkeypatch.setattr(main, "bridge_tool", fake_bridge_tool)
    monkeypatch.setattr(main, "current_joint_positions", lambda: ([v + 0.0005 for v in target], "bridge_state"))
    monkeypatch.setattr(main, "wait_for_arm_settle", lambda: calls.append(("wait", {})))

    result = main.move_to_joint_state(target, timeout=0.01)

    assert result["timeout_recovered"] is True
    assert calls[0][0] == "vendor.moveit.arm.move_to_joint_state"
    assert ("robot.release_control", {"control_source": "octos"}) in calls
    assert ("wait", {}) in calls


def test_grasp_object_locks_detected_target_and_does_not_relocate_during_motion(monkeypatch):
    main = _load_skill_main()
    calls = []
    located = {
        "category": "object",
        "point_base": [0.31, -0.02, 0.025],
        "table_z": 0.0,
        "estimated_size_m": {"height": 0.05},
    }

    def fake_locate(args, monitor, stage):
        calls.append(("locate", stage))
        return located

    monkeypatch.setattr(main, "locate_base_for_stage", fake_locate)
    monkeypatch.setattr(main, "set_gripper_width", lambda width: calls.append(("gripper", round(width, 3))))
    monkeypatch.setattr(main, "move_to_pose", lambda pos: calls.append(("move", [round(float(v), 6) for v in pos])))

    result = main.grasp_object(
        {
            "object_height_m": 0.05,
            "grasp_height_ratio": 0.35,
            "min_grasp_clearance_m": 0.008,
            "open_width": 0.06,
            "closed_width": 0.0,
            "high_z": 0.08,
            "lift_z": 0.07,
        }
    )

    assert [call for call in calls if call[0] == "locate"] == [("locate", "detect object")]
    assert ("move", [0.31, -0.02, 0.08]) in calls
    assert ("move", [0.31, -0.02, 0.0175]) in calls
    assert result["target_base"] == [0.31, -0.02, 0.0175]


def test_solve_pinch_ik_converts_real_table_z_to_mujoco_z(monkeypatch):
    main = _load_skill_main()
    monkeypatch.setenv("MODEL_NAME", str(main.DEFAULT_SO101_MODEL))

    target_base = [0.25, 0.10, -0.085]
    joints = main.solve_pinch_ik_for_base_point(
        target_base,
        seed=main.DEFAULT_SO101_HOME,
        table_z=-0.15,
        iters=80,
    )
    fk = main.forward_kinematics(joints, with_gripper=True)

    assert len(joints) == 5
    assert np.linalg.norm(np.asarray(fk["position"]) - np.asarray([0.25, 0.10, 0.065])) < 0.025


def test_forward_kinematics_supports_explicit_tcp_offset(monkeypatch):
    main = _load_skill_main()
    monkeypatch.setenv("MODEL_NAME", str(main.DEFAULT_SO101_MODEL))

    joints = main.DEFAULT_SO101_HOME
    gripper = main.forward_kinematics(joints, with_gripper=False)
    tcp = main.forward_kinematics(joints, tcp_offset_in_gripper_m=[0.01, 0.02, -0.03])

    expected = np.asarray(gripper["position"]) + gripper["rotation"] @ np.asarray([0.01, 0.02, -0.03])
    assert np.linalg.norm(np.asarray(tcp["position"]) - expected) < 1e-9


def test_move_pinch_to_base_point_reports_actual_fk_after_execution(monkeypatch):
    main = _load_skill_main()
    target = [0.1, 0.2, 0.3]
    commanded = [0.1, 0.2, 0.3, 0.4, 0.5]
    actual = [0.1, 0.2, 0.31, 0.4, 0.5]

    monkeypatch.setattr(main, "current_joint_positions", lambda: ([0.0] * 5, "bridge_state"))
    monkeypatch.setattr(main, "solve_pinch_ik_for_base_point", lambda *args, **kwargs: commanded)
    monkeypatch.setattr(main, "move_to_joint_state", lambda joints, timeout=45.0: {})

    calls = {"fk": 0}

    def fake_fk(joints, **kwargs):
        calls["fk"] += 1
        position = target if list(joints) == commanded else [0.11, 0.2, 0.3]
        return {"position": tuple(position), "rotation": np.eye(3), "transform": np.eye(4)}

    def fake_current_after_move():
        return (actual, "bridge_state")

    monkeypatch.setattr(main, "forward_kinematics", fake_fk)
    monkeypatch.setattr(main, "current_joint_positions", fake_current_after_move)

    result = main.move_pinch_to_base_point({"x": target[0], "y": target[1], "z": target[2]})

    assert result["commanded_joints"] == commanded
    assert result["actual_joints"] == actual
    assert result["commanded_pinch_fk"] == target
    assert result["actual_pinch_fk"] == [0.11, 0.2, 0.3]
    assert result["actual_error_m"] == [0.01, 0.0, 0.0]
    assert result["actual_error_norm_m"] == 0.01
    assert calls["fk"] == 2


def test_grasp_object_uses_depth_safe_motion_path(monkeypatch):
    main = _load_skill_main()
    calls = []

    located = {
        "point_base": [0.21, 0.08, -0.125],
        "table_z": -0.15,
        "estimated_size_m": {"width": 0.035, "height": 0.05},
    }

    monkeypatch.setattr(main, "locate_base", lambda args: located)
    monkeypatch.setattr(
        main,
        "set_gripper_width",
        lambda width: calls.append(("gripper", round(float(width), 6))),
    )
    monkeypatch.setattr(
        main,
        "move_to_pose",
        lambda point: calls.append(("move", [round(float(v), 6) for v in point])),
    )

    result = main.grasp_object(
        {
            "color": "yellow",
            "object_height_m": 0.03,
            "grasp_height_ratio": 0.4,
            "min_grasp_clearance_m": 0.008,
            "open_width": 0.06,
            "closed_width": 0.0,
            "high_z": 0.08,
            "lift_z": 0.07,
        }
    )

    assert calls == [
        ("gripper", 0.06),
        ("move", [0.21, 0.08, 0.08]),
        ("move", [0.21, 0.08, -0.02]),
        ("move", [0.21, 0.08, -0.138]),
        ("gripper", 0.0),
        ("move", [0.21, 0.08, 0.07]),
    ]
    assert result["grasped"] is True
    assert result["target_base"] == [0.21, 0.08, -0.138]
    assert result["perception"] == located
