from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import numpy as np

from octos_object_perception.types import Object3D, SizeEstimate


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "live_open3d_geometry_viewer.py"


def _load_script():
    loader = SourceFileLoader("live_open3d_geometry_viewer", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parser_accepts_live_viewer_target_options():
    script = _load_script()

    args = script.build_parser().parse_args([
        "--color",
        "orange",
        "--workspace-bounds-m",
        '{"x":[-0.2,0.2],"y":[0.02,0.24],"z":[0.25,0.65]}',
        "--size-range-m",
        '{"min_width":0.02,"max_width":0.10,"min_height":0.02,"max_height":0.10}',
        "--once",
        "--no-window",
    ])

    assert args.color == "orange"
    assert args.once is True
    assert args.no_window is True


def test_should_quit_accepts_escape_q_and_window_close():
    script = _load_script()

    assert script.should_quit(27, visible=True)
    assert script.should_quit(ord("q"), visible=True)
    assert script.should_quit(ord("Q"), visible=True)
    assert script.should_quit(-1, visible=False)
    assert not script.should_quit(-1, visible=True)


def test_draw_live_overlay_labels_detected_objects():
    script = _load_script()
    frame = np.zeros((80, 120, 3), dtype=np.uint8)
    obj = Object3D(
        category="object",
        color="orange",
        bbox=(30, 20, 40, 30),
        confidence=0.8,
        distance_m=0.3,
        point_camera=(0.0, 0.0, 0.3),
        estimated_size_m=SizeEstimate(width=0.04, height=0.03),
        depth_valid_ratio=1.0,
        geometry_source="open3d_tabletop_cluster_obb",
    )

    overlay = script.draw_live_overlay(frame, [obj], fps=12.3)

    assert overlay.shape == frame.shape
    assert np.count_nonzero(overlay) > 0
