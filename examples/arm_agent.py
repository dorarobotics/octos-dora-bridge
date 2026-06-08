#!/usr/bin/env python3
"""octos agent: drive the UR5e pick-and-place from one natural-language sentence.

Registers 4 skill-level tools (get_ball_position, get_plate_position, pick_at,
place_at) backed by arm_skills.py, points the octos Agent at the local Ollama
qwen3:8b, and runs agent.process_message(<sentence>). The LLM reads the sentence,
senses the ball + plate, and sequences the skills — the robot executes over the
same bridge HTTP tools as the scripted demo, but the *plan* is the LLM's.

Usage: python arm_agent.py "pick up the red ball and place it on the green plate"
Env: OCTOS_PY_DIR (parent of the octos_py package), OLLAMA_BASE, OLLAMA_MODEL,
     plus arm_skills' env (MODEL_NAME, ARM_BRIDGE_URL, BALL_URL, PLATE_X/Y).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.environ.get("OCTOS_PY_DIR", "/home/demo/dorarobotics-test"))

import arm_skills  # noqa: E402
from octos_py.agent import Agent, AgentConfig  # noqa: E402
from octos_py.provider import OpenAIProvider  # noqa: E402
from octos_py.tools import Tool, ToolRegistry, ToolResult  # noqa: E402

_NUM = {"type": "number"}


class _Fn(Tool):
    def __init__(self, name, desc, schema, fn):
        self._n, self._d, self._s, self._fn = name, desc, schema, fn

    def name(self):
        return self._n

    def description(self):
        return self._d

    def input_schema(self):
        return self._s

    def tags(self):
        return []

    def execute(self, args):
        return ToolResult(output=str(self._fn(**(args or {}))))


TOOLS = [
    _Fn("get_ball_position",
        "Return the red ball's position on the table as 'x=.., y=..' in meters.",
        {"type": "object", "properties": {}, "required": []},
        lambda: arm_skills.get_ball_position()),
    _Fn("get_plate_position",
        "Return the green target plate's position on the table as 'x=.., y=..' in meters.",
        {"type": "object", "properties": {}, "required": []},
        lambda: arm_skills.get_plate_position()),
    _Fn("pick_at",
        "Pick up the object at table position (x, y): approach from above, close the "
        "gripper, and lift. Read the object's position first and pass those exact coords.",
        {"type": "object", "properties": {"x": _NUM, "y": _NUM}, "required": ["x", "y"]},
        lambda x, y: arm_skills.pick_at(x, y)),
    _Fn("place_at",
        "Place the currently-held object down at table position (x, y) and open the "
        "gripper. You must pick_at something before calling this.",
        {"type": "object", "properties": {"x": _NUM, "y": _NUM}, "required": ["x", "y"]},
        lambda x, y: arm_skills.place_at(x, y)),
]

SYSTEM_PROMPT = """You are a robot arm agent controlling a UR5e with a gripper in simulation.

You move objects using these tools:
- get_ball_position(): where the red ball is (returns x, y in meters)
- get_plate_position(): where the green plate is (returns x, y in meters)
- pick_at(x, y): pick up the object at that position
- place_at(x, y): put the held object down at that position

To move an object onto a target: read the object's position, read the target's
position, then pick_at the object's coordinates, then place_at the target's
coordinates. Call ONE tool at a time and wait for its result. Use the exact
numbers returned by the position tools. When the object has been placed, briefly
say you are done and stop (do not call more tools).
"""


def main():
    sentence = " ".join(sys.argv[1:]).strip() or \
        "Pick up the red ball and place it on the green plate."

    reg = ToolRegistry()
    for t in TOOLS:
        reg.register(t)
    reg.set_base_tools([t.name() for t in TOOLS])  # always present all 4 to the LLM

    provider = OpenAIProvider(
        model=os.environ.get("OLLAMA_MODEL", "qwen3:8b"),
        api_key="ollama",
        api_base=os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434/v1"),
    )
    agent = Agent(provider=provider, registry=reg,
                  config=AgentConfig(max_iterations=15, max_timeout_secs=600))
    agent._system_prompt = SYSTEM_PROMPT  # override the SDK's hardcoded dora_* prompt

    def tool_executor(name, args):
        tool = reg.get(name)
        if tool is None:
            return f"ERROR: unknown tool {name}"
        try:
            return tool.execute(args or {}).output
        except Exception as e:  # noqa: BLE001
            return f"ERROR executing {name}: {e}"

    print(f"\n=== octos agent (qwen3:8b) — sentence: {sentence!r} ===", flush=True)
    agent.process_message(sentence, tool_executor)


if __name__ == "__main__":
    main()
