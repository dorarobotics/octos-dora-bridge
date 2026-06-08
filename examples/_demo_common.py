"""Tiny zero-dependency HTTP helper for the visual demo drivers."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def say(msg: str) -> None:
    print(f"\n\033[1;36m▶ {msg}\033[0m", flush=True)


def detail(msg: str) -> None:
    print(f"  {msg}", flush=True)


def call(base_url: str, verb: str, *, timeout: float = 70.0, **args: Any) -> dict[str, Any]:
    """POST /tools/{verb} with {"args": {...}} and return the parsed JSON."""
    body = json.dumps({"args": args}).encode()
    req = urllib.request.Request(
        f"{base_url}/tools/{verb}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def wait_healthz(base_url: str, tries: int = 60) -> bool:
    for _ in range(tries):
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=2) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1)
    return False


def check(resp: dict[str, Any], what: str) -> dict[str, Any]:
    ok = resp.get("ok")
    code = resp.get("code")
    if ok:
        detail(f"✓ {what}: ok (code={code})")
    else:
        detail(f"✗ {what}: ok={ok} code={code} msg={resp.get('msg')}")
    return resp


def require_healthz(base_url: str) -> None:
    say(f"Waiting for bridge at {base_url} …")
    if not wait_healthz(base_url):
        print(f"bridge never became healthy at {base_url}", file=sys.stderr)
        sys.exit(1)
    detail("bridge is up")
