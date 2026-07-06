from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

from octos_object_perception.types import Object3D, SizeEstimate


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "diagnose_open3d_geometry.py"


def _load_script():
    loader = SourceFileLoader("diagnose_open3d_geometry", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_workspace_bounds_accepts_axis_ranges():
    script = _load_script()

    bounds = script.parse_workspace_bounds('{"x":[-0.3,0.3],"y":[-0.2,0.2],"z":[0.15,0.8]}')

    assert bounds == {
        "x": [-0.3, 0.3],
        "y": [-0.2, 0.2],
        "z": [0.15, 0.8],
    }


def test_parse_workspace_bounds_rejects_bad_shape():
    script = _load_script()

    try:
        script.parse_workspace_bounds('{"x":[0.1]}')
    except ValueError as exc:
        assert "exactly two numbers" in str(exc)
    else:
        raise AssertionError("bad workspace bounds should fail")


def test_parse_size_range_accepts_metric_bounds():
    script = _load_script()

    size_range = script.parse_size_range('{"min_width":0.02,"max_width":0.18,"min_height":0.01,"max_height":0.16}')

    assert size_range.min_width == 0.02
    assert size_range.max_width == 0.18
    assert size_range.min_height == 0.01
    assert size_range.max_height == 0.16


def test_parse_size_range_rejects_non_object_json():
    script = _load_script()

    try:
        script.parse_size_range("[0.02,0.18]")
    except ValueError as exc:
        assert "size range must be a JSON object" in str(exc)
    else:
        raise AssertionError("bad size range should fail")


def test_parser_accepts_target_color():
    script = _load_script()

    args = script.build_parser().parse_args(["--color", "orange"])

    assert args.color == "orange"


def test_build_report_serializes_open3d_objects():
    script = _load_script()
    obj = Object3D(
        category="object",
        color=None,
        bbox=(3, 2, 4, 2),
        confidence=0.5,
        distance_m=0.3,
        point_camera=(-0.0015, -0.0015, 0.3),
        estimated_size_m=SizeEstimate(width=0.03, height=0.02),
        depth_valid_ratio=1.0,
        geometry_source="open3d_tabletop_cluster_obb",
    )

    report = script.build_report(
        objects=[obj],
        color_shape=(6, 8, 3),
        depth_shape=(6, 8),
        detector_config={"dbscan_eps_m": 0.025},
        depth_stats={"valid_count": 48, "median": 0.4},
    )

    assert report["summary"]["object_count"] == 1
    assert report["summary"]["geometry_source"] == "open3d_geometry"
    assert report["detector_config"] == {"dbscan_eps_m": 0.025}
    assert report["objects"][0]["point_camera"] == [-0.0015, -0.0015, 0.3]
