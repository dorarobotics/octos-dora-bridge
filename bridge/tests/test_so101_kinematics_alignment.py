import os
import sys
from pathlib import Path

import mujoco
import numpy as np


DORA_MOVEIT2 = Path("/home/dora/so101-sim/dora-moveit2")
SO101_MODEL = DORA_MOVEIT2 / "examples" / "move_group_demo" / "models" / "so101_pickplace.xml"


def test_so101_config_fk_matches_mujoco_pinch_site():
    sys.path[:0] = [str(DORA_MOVEIT2), str(DORA_MOVEIT2 / "examples" / "move_group_demo")]
    os.environ["ROBOT_CONFIG_MODULE"] = "move_group_demo.config.so101"

    from dora_moveit.ik_solver.advanced_ik_solver import ForwardKinematics
    from move_group_demo.config.so101 import SO101Config

    model = mujoco.MjModel.from_xml_path(str(SO101_MODEL))
    data = mujoco.MjData(model)
    pinch_site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "pinch")
    fk = ForwardKinematics(config=SO101Config)

    sample_joints = [
        np.zeros(5),
        SO101Config.HOME_CONFIG,
        np.array([0.13118738553451884, -0.4196461981718234, 0.8208801317072232, -1.1039687004922376, -1.433087930868311]),
    ]

    for joints in sample_joints:
        data.qpos[SO101Config.ARM_QPOS_START : SO101Config.ARM_QPOS_START + 5] = joints
        mujoco.mj_forward(model, data)

        config_tcp, _ = fk.compute_fk(joints)
        mujoco_tcp = data.site_xpos[pinch_site_id].copy()

        assert np.linalg.norm(config_tcp - mujoco_tcp) < 0.002


def test_so101_de_ik_prefers_seed_near_home_for_reachable_point():
    sys.path[:0] = [str(DORA_MOVEIT2), str(DORA_MOVEIT2 / "examples" / "move_group_demo")]
    os.environ["ROBOT_CONFIG_MODULE"] = "move_group_demo.config.so101"

    from dora_moveit.ik_solver.advanced_ik_solver import DifferentialEvolutionIKSolver, IKRequest
    from move_group_demo.config.so101 import SO101Config

    model = mujoco.MjModel.from_xml_path(str(SO101_MODEL))
    data = mujoco.MjData(model)
    pinch_site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "pinch")

    home = SO101Config.HOME_CONFIG.copy()
    reachable_near_home = home + np.array([0.0, -0.08, 0.08, 0.0, 0.0])
    data.qpos[SO101Config.ARM_QPOS_START : SO101Config.ARM_QPOS_START + 5] = reachable_near_home
    mujoco.mj_forward(model, data)
    target_tcp = data.site_xpos[pinch_site_id].copy()

    solver = DifferentialEvolutionIKSolver(config=SO101Config)
    result = solver.solve(IKRequest(target_position=target_tcp, seed_joints=home))

    assert result.success
    assert result.error < 0.001
    assert np.linalg.norm(result.joint_positions - home) < 0.5
    assert abs(result.joint_positions[4] - home[4]) < 0.4


def test_ik_operator_extracts_arm_seed_from_full_qpos():
    sys.path[:0] = [str(DORA_MOVEIT2), str(DORA_MOVEIT2 / "examples" / "move_group_demo")]
    os.environ["ROBOT_CONFIG_MODULE"] = "move_group_demo.config.so101"

    from dora_moveit.ik_solver.ik_op import IKOperator
    from move_group_demo.config.so101 import SO101Config

    operator = IKOperator(num_joints=SO101Config.NUM_JOINTS, solver_type="de")
    full_qpos = np.zeros(SO101Config.ARM_QPOS_START + SO101Config.NUM_JOINTS + 1)
    full_qpos[SO101Config.ARM_QPOS_START : SO101Config.ARM_QPOS_START + SO101Config.NUM_JOINTS] = SO101Config.HOME_CONFIG

    operator.process_joint_state(full_qpos)

    assert np.allclose(operator.current_joints, SO101Config.HOME_CONFIG)


def test_trajectory_executor_holds_final_goal_after_timed_trajectory_completion(monkeypatch):
    sys.path[:0] = [str(DORA_MOVEIT2), str(DORA_MOVEIT2 / "examples" / "move_group_demo")]
    os.environ["ROBOT_CONFIG_MODULE"] = "move_group_demo.config.so101"
    monkeypatch.setenv("EXEC_INTERP_SPEED", "1.0")

    from dora_moveit.trajectory_execution.trajectory_executor import TrajectoryExecutor

    executor = TrajectoryExecutor(num_joints=5, arm_qpos_start=7)
    start = np.zeros(5)
    goal = np.array([0.5, 0.2, -0.1, 0.3, 0.0])
    lagging_actual = np.array([0.25, 0.1, -0.05, 0.15, 0.0])

    executor.update_current_joints(np.r_[np.zeros(7), start, 0.0])
    executor.set_trajectory([start, goal], trajectory_hash=1)
    executor.update_current_joints(np.r_[np.zeros(7), lagging_actual, 0.0])

    command = executor.step()

    assert not executor.is_executing
    assert np.allclose(command, goal)
    assert np.allclose(executor.last_command, goal)


def test_trajectory_executor_can_apply_bounded_hold_correction(monkeypatch):
    sys.path[:0] = [str(DORA_MOVEIT2), str(DORA_MOVEIT2 / "examples" / "move_group_demo")]
    os.environ["ROBOT_CONFIG_MODULE"] = "move_group_demo.config.so101"
    monkeypatch.setenv("EXEC_HOLD_CORRECTION_GAIN", "1.0")
    monkeypatch.setenv("EXEC_HOLD_CORRECTION_MAX_RAD", "0.08")
    monkeypatch.setenv("EXEC_HOLD_CORRECTION_DEADBAND_RAD", "0.0")

    from dora_moveit.trajectory_execution.trajectory_executor import TrajectoryExecutor

    executor = TrajectoryExecutor(num_joints=5, arm_qpos_start=7)
    goal = np.array([0.5, 0.2, -0.1, 0.3, 0.0])
    lagging_actual = np.array([0.45, 0.25, -0.3, 0.29, 0.0])
    executor.last_command = goal.copy()
    executor.current_joints = lagging_actual.copy()

    corrected = executor.step()

    assert np.allclose(corrected, np.array([0.55, 0.15, -0.02, 0.31, 0.0]))


def test_trajectory_executor_hold_correction_mask_and_deadband(monkeypatch):
    sys.path[:0] = [str(DORA_MOVEIT2), str(DORA_MOVEIT2 / "examples" / "move_group_demo")]
    os.environ["ROBOT_CONFIG_MODULE"] = "move_group_demo.config.so101"
    monkeypatch.setenv("EXEC_HOLD_CORRECTION_GAIN", "1.0")
    monkeypatch.setenv("EXEC_HOLD_CORRECTION_MAX_RAD", "0.08")
    monkeypatch.setenv("EXEC_HOLD_CORRECTION_DEADBAND_RAD", "0.02")
    monkeypatch.setenv("EXEC_HOLD_CORRECTION_MASK", "0,1,1,1,0")

    from dora_moveit.trajectory_execution.trajectory_executor import TrajectoryExecutor

    executor = TrajectoryExecutor(num_joints=5, arm_qpos_start=7)
    goal = np.array([0.5, 0.2, -0.1, 0.3, 0.0])
    actual = np.array([0.4, 0.19, -0.3, 0.25, 0.1])
    executor.last_command = goal.copy()
    executor.current_joints = actual.copy()

    corrected = executor.step()

    assert np.allclose(corrected, np.array([0.5, 0.2, -0.02, 0.35, 0.0]))
