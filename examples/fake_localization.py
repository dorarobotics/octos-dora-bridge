#!/usr/bin/env python3
"""Stand-in for dora-nav's localization node — publishes a static pose."""
from __future__ import annotations

import json
import time

import pyarrow as pa
from dora import Node


def main() -> None:
    node = Node()
    for event in node:
        if event["type"] != "INPUT":
            continue
        pose = {"x": 0.0, "y": 0.0, "theta": 0.0}
        node.send_output("pose", pa.array([json.dumps(pose)]))
        node.send_output("obstacles", pa.array([json.dumps([])]))
        time.sleep(0.2)


if __name__ == "__main__":
    main()
