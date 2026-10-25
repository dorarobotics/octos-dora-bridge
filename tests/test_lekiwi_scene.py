"""Build a movable LeKiwi scene from the pristine MJCF and assert it loads."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

from lekiwi_scene import build_scene  # noqa: E402

# LeKiwi-sim lives next to the workspace; allow override for CI/epyc.
LEKIWI_DIR = os.environ.get(
    "LEKIWI_SIM_DIR", "/Users/Shared/github_dorarobotics/LeKiwi-sim"
)
SRC = os.path.join(LEKIWI_DIR, "mjcf_lcmm_robot.xml")


@pytest.mark.skipif(not os.path.exists(SRC), reason="LeKiwi-sim MJCF not present")
def test_build_scene_injects_free_joint_and_floor():
    xml = build_scene(SRC, meshdir=LEKIWI_DIR)
    assert '<freejoint name="base_free"/>' in xml
    assert 'type="plane"' in xml
    assert 'meshdir=' in xml


@pytest.mark.skipif(not os.path.exists(SRC), reason="LeKiwi-sim MJCF not present")
def test_scene_loads_in_mujoco_with_movable_base():
    mujoco = pytest.importorskip("mujoco")
    xml = build_scene(SRC, meshdir=LEKIWI_DIR)
    model = mujoco.MjModel.from_xml_string(xml)
    # the injected free joint must exist and be addressable
    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "base_free")
    assert jid >= 0
    assert model.jnt_type[jid] == mujoco.mjtJoint.mjJNT_FREE
