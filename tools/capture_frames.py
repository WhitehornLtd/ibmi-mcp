# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

"""Capture the raw 5250 datastream a host sends, for building test fixtures.

Drives a real session and dumps every GDS frame the host sends, so parser
defects can be diagnosed from real bytes rather than from theory. Credentials
come from the IBMI_* environment, exactly as the server itself reads them.

Usage:
    IBMI_HOST=... IBMI_USER=... IBMI_PASSWORD=... \
        python tools/capture_frames.py <out.json> "<cmd to run>" [key ...]
"""

import asyncio
import json
import os
import sys

# Credentials come from the IBMI_* environment. As a convenience for local
# diagnosis, fall back to the ibmi-5250 entry of an MCP config file named by
# IBMI_MCP_CONFIG, so secrets need not be typed on the command line.
_config_path = os.environ.get("IBMI_MCP_CONFIG")
if _config_path and os.path.exists(_config_path):
    with open(_config_path) as _handle:
        _servers = json.load(_handle).get("mcpServers", {})
    for _key, _value in _servers.get("ibmi-5250", {}).get("env", {}).items():
        os.environ.setdefault(_key, _value)

from ibmi_mcp import server  # noqa: E402
from ibmi_mcp.tn5250 import session as session_mod  # noqa: E402


def _tool(name):
    """The MCP decorator may yield a wrapper object or the plain function."""
    obj = getattr(server, name)
    return getattr(obj, "fn", obj)

FRAMES: list[dict] = []
PHASE = ["connect"]
_orig_process = session_mod.Tn5250Session._process_gds_frame


def _spy(self, frame: bytes):
    FRAMES.append({"phase": PHASE[0], "hex": frame.hex()})
    return _orig_process(self, frame)


session_mod.Tn5250Session._process_gds_frame = _spy


def _show(label: str, result: dict, rows: int = 8) -> None:
    print(f"\n--- {label} ---")
    if result.get("error"):
        print("ERROR:", result["error"])
    for row in result.get("screen", [])[:rows]:
        print(repr(row))
    if result.get("fields"):
        print("fields:", json.dumps(result["fields"])[:500])
    if result.get("warning"):
        print("warning:", result["warning"])


async def main() -> None:
    out_path = sys.argv[1]
    command = sys.argv[2]
    keys = sys.argv[3:] or ["enter"]

    result = await _tool("connect")()
    if "error" in result:
        print("CONNECT ERROR:", result["error"])
        return
    print("connected:", result["screen"][0][:70])

    # Sign-on may land on an informational screen that must be dismissed
    # before the menu with its command line appears.
    PHASE[0] = "dismiss"
    for _ in range(3):
        if "Main Menu" in " ".join(result.get("screen", [])):
            break
        result = await _tool("send_key")("enter")
    print("at menu:", result["screen"][0][:70])

    # The IBM i main menu command line needs an explicit cursor placement.
    PHASE[0] = "menu"
    await _tool("set_cursor")(20, 7)
    await _tool("send_keys")(command)

    for action in keys:
        PHASE[0] = action
        if action.startswith("type:"):
            result = await _tool("send_keys")(action[5:])
            _show(f"after type {action[5:]!r}", result)
        elif action.startswith("at:"):
            row, col = action[3:].split(",")
            result = await _tool("set_cursor")(int(row), int(col))
            _show(f"after cursor {row},{col}", result)
        else:
            result = await _tool("send_key")(action)
            _show(f"after {action}", result)

    await _tool("disconnect")()

    with open(out_path, "w") as handle:
        json.dump(FRAMES, handle, indent=1)
    print(f"\nwrote {len(FRAMES)} frames to {out_path}")


asyncio.run(main())
