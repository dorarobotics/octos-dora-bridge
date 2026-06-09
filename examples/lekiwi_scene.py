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
BASE_Z = 0.06   # m — lift the base so the wheels rest on the floor

_FLOOR = (
    '\n        <geom name="floor" type="plane" size="5 5 0.1" '
    'rgba="0.82 0.85 0.90 1" pos="0 0 0"/>'
)
_OPTION = '\n    <option timestep="0.002" gravity="0 0 -9.81"/>'


def build_scene(src_mjcf: str, meshdir: str) -> str:
    with open(src_mjcf, "r", encoding="utf-8") as fh:
        xml = fh.read()

    # 1) absolute meshdir so from_xml_string resolves the meshes
    xml = xml.replace(
        COMPILER_TAG,
        f'<compiler angle="radian" meshdir="{meshdir}" />{_OPTION}',
        1,
    )
    # 2) free joint on the base root (raised so wheels sit on the floor)
    xml = xml.replace(
        ROOT_BODY_TAG,
        '<body name="base_plate_layer1-v5-1" pos="0.0 0.0 '
        f'{BASE_Z}" euler="-0.0 0.0 -0.0">\n            '
        '<freejoint name="base_free"/>',
        1,
    )
    # 3) floor
    xml = xml.replace(WORLDBODY_OPEN, WORLDBODY_OPEN + _FLOOR, 1)
    return xml
