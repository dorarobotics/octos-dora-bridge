#!/usr/bin/env python3
"""Stand-in for dora-nav's planner — echoes goals as 'arrived' status."""
from __future__ import annotations

import json

import pyarrow as pa
from dora import Node


def main() -> None:
    node = Node()
    for event in node:
        if event["type"] != "INPUT":
            continue
        topic = event["id"]
        if topic == "goal":
            node.send_output("status", pa.array([json.dumps("arrived")]))
        elif topic == "cancel":
            node.send_output("status", pa.array([json.dumps("idle")]))


if __name__ == "__main__":
    main()
