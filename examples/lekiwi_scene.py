"""Build a movable LeKiwi MuJoCo scene from the PRISTINE mjcf_lcmm_robot.xml.

The shipped model bolts the base root (base_plate_layer1-v5-1) directly to the
world (no joint) and comments out its floor, so the robot cannot translate. We
read that file as text (never modify it) and inject: a free joint on the base
root, a floor plane, an <option>, and an absolute meshdir so meshes resolve when
the scene is loaded from a string. Returns the scene XML string.
"""
from __future__ import annotations

ROOT_BODY_TAG = '<body name="base_plate_layer1-v5-1" pos="0.0 0.0 0.0" euler="-0.0 0.0 -0.0">'
COMPILER_TAG = '<compiler angle="radian" />'
WORLDBODY_OPEN = "<worldbody>"
WORLDBODY_CLOSE = "</worldbody>"
BASE_Z = 0.06   # m — lift the base so the wheels rest on the floor

_FLOOR = (
    '\n        <geom name="floor" type="plane" size="5 5 0.1" '
    'rgba="0.82 0.85 0.90 1" pos="0 0 0"/>'
)
# Virtual omni-drive: gravity off + contacts disabled. The base is placed by
# forward-kinematics and the wheels are spun by velocity actuators under mj_step;
# no contact is needed (and the single-body omniwheels can't roll correctly), so
# disabling contact also avoids costly collision on the 78k-triangle wheel meshes.
_OPTION = (
    '\n    <option timestep="0.002" gravity="0 0 0">'
    '\n      <flag contact="disable"/>'
    '\n    </option>'
)


def build_scene(src_mjcf: str, meshdir: str) -> str:
    with open(src_mjcf, "r", encoding="utf-8") as fh:
        xml = fh.read()

    # 1) absolute meshdir so from_xml_string resolves the meshes
    xml = xml.replace(
        COMPILER_TAG,
        f'<compiler angle="radian" meshdir="{meshdir}" />{_OPTION}',
        1,
    )
    # 1b) make the 3 wheel drives VELOCITY actuators so octos can command wheel
    # speeds (motors 7/8/9). The shipped model uses <motor> (torque); velocity
    # control lets ctrl = target wheel angular speed (rad/s).
    xml = xml.replace('<motor name="drive_motor_', '<velocity kv="8" name="drive_motor_')
    # 2) floor
    xml = xml.replace(WORLDBODY_OPEN, WORLDBODY_OPEN + _FLOOR, 1)
    # 3) The MJCF has THREE sibling top-level bodies (base_plate_layer1 = wheels,
    # base_plate_layer2 = arm mount, drive_motor_mount-v4). Wrap them ALL in one
    # `chassis` body carrying the free joint, so the whole robot moves together
    # (a free joint on just base_plate_layer1 would drive the base off the arm).
    xml = xml.replace(
        ROOT_BODY_TAG,
        f'<body name="chassis" pos="0 0 0">\n        <freejoint name="base_free"/>\n        {ROOT_BODY_TAG}',
        1,
    )
    xml = xml.replace(WORLDBODY_CLOSE, f"        </body>\n    {WORLDBODY_CLOSE}", 1)
    return xml
