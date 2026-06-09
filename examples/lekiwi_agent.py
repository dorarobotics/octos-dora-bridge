#!/usr/bin/env python3
"""octos agent: drive the LeKiwi mobile base from one natural-language sentence.

Registers 3 tools (move_base, stop_base, get_base_pose) backed by the nav-base
bridge HTTP (:8770), points the octos Agent at local Ollama qwen3:8b, and runs
agent.process_message(<sentence>). The LLM reads e.g. "move forward" and calls
move_base — the same bridge verbs the scripted demo used, but the plan is the
LLM's. Mirrors examples/arm_agent.py.

Usage: python lekiwi_agent.py "move forward"
Env: OCTOS_PY_DIR (parent of octos_py), OLLAMA_BASE, OLLAMA_MODEL, LEKIWI_BRIDGE_URL.
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.environ.get("OCTOS_PY_DIR", "/home/demo/dorarobotics-test"))

from octos_py.agent import Agent, AgentConfig  # noqa: E402
from octos_py.provider import OpenAIProvider  # noqa: E402
from octos_py.tools import Tool, ToolRegistry, ToolResult  # noqa: E402

BRIDGE = os.environ.get("LEKIWI_BRIDGE_URL", "http://127.0.0.1:8770")
MAX_SECONDS = 10.0
_NUM = {"type": "number"}


def _post(verb: str, **args):
    body = json.dumps({"args": args}).encode()
    req = urllib.request.Request(
        f"{BRIDGE}/tools/{verb}", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def _pose():
    return (_post("vendor.dora_nav.localization.get_pose").get("data") or {}).get("pose")


def move_base(linear=0.0, angular=0.0, seconds=2.0):
    seconds = max(0.0, min(float(seconds), MAX_SECONDS))
    r = _post("vendor.dora_nav.base.set_velocity",
              linear=float(linear), angular=float(angular), control_source="octos")
    if not r.get("ok"):
        return f"set_velocity failed: {r.get('code')} {r.get('msg')}"
    time.sleep(seconds)
    _post("vendor.dora_nav.base.stop")
    return f"moved linear={linear} angular={angular} for {seconds}s; pose now {_pose()}"


def stop_base():
    _post("vendor.dora_nav.base.stop")
    return f"stopped; pose {_pose()}"


def get_base_pose():
    return f"pose: {_pose()}"


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
    _Fn("move_base",
        "Drive the mobile base for a few seconds then auto-stop. linear>0 forward, "
        "linear<0 back; angular>0 turn left, angular<0 turn right. 'move forward' -> "
        "linear=0.3, angular=0, seconds=2.",
        {"type": "object",
         "properties": {"linear": _NUM, "angular": _NUM, "seconds": _NUM},
         "required": []},
        move_base),
    _Fn("stop_base", "Stop the base immediately.",
        {"type": "object", "properties": {}, "required": []},
        lambda: stop_base()),
    _Fn("get_base_pose", "Return the base pose as x, y, theta.",
        {"type": "object", "properties": {}, "required": []},
        lambda: get_base_pose()),
]

SYSTEM_PROMPT = """You are a mobile-base robot agent controlling a LeKiwi omni-wheel base in simulation.

You drive it with these tools:
- move_base(linear, angular, seconds): drive then auto-stop. linear in m/s (+forward, -back), angular in rad/s (+left, -right).
- stop_base(): stop now.
- get_base_pose(): current x, y, theta.

For "move forward" call move_base(linear=0.3, angular=0.0, seconds=2). For "turn left" use angular=0.8, for "turn right" angular=-0.8. Call ONE tool at a time and wait for its result. When the requested motion is done, briefly say so and stop (do not call more tools).
"""


def main():
    sentence = " ".join(sys.argv[1:]).strip() or "move forward"

    reg = ToolRegistry()
    for t in TOOLS:
        reg.register(t)
    reg.set_base_tools([t.name() for t in TOOLS])

    provider = OpenAIProvider(
        model=os.environ.get("OLLAMA_MODEL", "qwen3:8b"),
        api_key="ollama",
        api_base=os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434/v1"),
    )
    agent = Agent(provider=provider, registry=reg,
                  config=AgentConfig(max_iterations=10, max_timeout_secs=300))
    agent._system_prompt = SYSTEM_PROMPT

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
