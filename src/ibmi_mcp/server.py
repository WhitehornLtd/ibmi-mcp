# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

from mcp.server.fastmcp import FastMCP

from ibmi_mcp.config import IBMiConfig
from ibmi_mcp.tn5250.session import Tn5250Session

mcp = FastMCP("ibmi-5250")

_session: Tn5250Session | None = None
_config = IBMiConfig()


def _screen_response() -> dict:
    data = _session.screen.get_screen_data()
    if _session.timed_out:
        data["warning"] = "Host did not respond within timeout — screen may be incomplete"
    return data


@mcp.tool()
async def connect(host: str = "", port: int = 0, use_ssl: bool | None = None) -> dict:
    """Connect to an IBM i system via TN5250.

    Args:
        host: IBM i hostname or IP. Defaults to IBMI_HOST env var.
        port: TN5250 port. Defaults to IBMI_PORT env var or 23.
        use_ssl: Enable TLS. Defaults to IBMI_SSL env var.

    Returns the initial screen after connection.
    """
    global _session

    if _session is not None and _session.state.value != "disconnected":
        await _session.disconnect()

    resolved_host = host or _config.host
    if not resolved_host:
        return {"error": "No host specified. Set IBMI_HOST or pass host parameter."}

    resolved_port = port or _config.port
    resolved_ssl = use_ssl if use_ssl is not None else _config.ssl

    _session = Tn5250Session(
        host=resolved_host,
        port=resolved_port,
        use_ssl=resolved_ssl,
        terminal_type=_config.terminal_type,
        device_name=_config.device_name,
        codepage=_config.codepage,
        username=_config.user,
        password=_config.password,
    )

    try:
        await _session.connect()
    except Exception as e:
        _session = None
        return {"error": f"Connection failed: {e}"}

    return _screen_response()


@mcp.tool()
async def disconnect() -> dict:
    """Disconnect the active TN5250 session."""
    global _session

    if _session is None:
        return {"status": "already disconnected"}

    await _session.disconnect()
    _session = None
    return {"status": "disconnected"}


@mcp.tool()
async def read_screen() -> dict:
    """Read the current 5250 screen content.

    Returns structured data with:
    - screen: list of text rows (the visible display)
    - cursor: current cursor position {row, col} (1-based)
    - fields: list of input fields with position, length, value, and type
    - dimensions: screen size {rows, cols}
    """
    if _session is None:
        return {"error": "Not connected. Call connect() first."}

    return _session.screen.get_screen_data()


@mcp.tool()
async def send_keys(text: str) -> dict:
    """Type text into the current input field at the cursor position.

    Args:
        text: The text to type.

    Returns the updated screen state.
    """
    if _session is None:
        return {"error": "Not connected. Call connect() first."}

    try:
        await _session.type_keys(text)
    except RuntimeError as e:
        return {"error": str(e)}

    return _screen_response()


@mcp.tool()
async def send_key(key: str) -> dict:
    """Send an attention/function key and wait for the host response.

    Args:
        key: Key name. Valid values: Enter, F1-F24, PageUp, PageDown,
             Tab, Backtab, Clear, Help, Print, Attn.

    Returns the updated screen after the host processes the key.
    """
    if _session is None:
        return {"error": "Not connected. Call connect() first."}

    key_lower = key.lower().strip()

    if key_lower == "attn":
        await _session.send_attention()
    elif key_lower == "tab":
        _move_to_next_field(forward=True)
    elif key_lower in ("backtab", "btab", "shift+tab"):
        _move_to_next_field(forward=False)
    elif _session.handle_local_key(key_lower):
        pass  # Handled as local editing key
    else:
        try:
            await _session.send_aid(key_lower)
        except ValueError as e:
            return {"error": str(e)}

    return _screen_response()


@mcp.tool()
async def set_cursor(row: int, col: int) -> dict:
    """Position the cursor at the specified location.

    Args:
        row: Row number (1-based, top row is 1).
        col: Column number (1-based, leftmost column is 1).

    Returns the updated screen state.
    """
    if _session is None:
        return {"error": "Not connected. Call connect() first."}

    if row < 1 or row > _session.screen.rows:
        return {"error": f"Row must be between 1 and {_session.screen.rows}"}
    if col < 1 or col > _session.screen.cols:
        return {"error": f"Col must be between 1 and {_session.screen.cols}"}

    _session.move_cursor(row, col)
    return _session.screen.get_screen_data()


def _move_to_next_field(forward: bool = True) -> None:
    """Move cursor to the next/previous input field (Tab/Backtab behavior)."""
    if _session is None:
        return

    fields = _session.screen.get_input_fields()
    if not fields:
        return

    cursor_pos = _session.screen.cursor_pos()
    cols = _session.screen.cols

    if forward:
        for f in fields:
            field_start = f.row * cols + f.col
            if field_start > cursor_pos:
                _session.screen.set_cursor(f.row, f.col)
                return
        _session.screen.set_cursor(fields[0].row, fields[0].col)
    else:
        for f in reversed(fields):
            field_start = f.row * cols + f.col
            if field_start < cursor_pos:
                _session.screen.set_cursor(f.row, f.col)
                return
        _session.screen.set_cursor(fields[-1].row, fields[-1].col)
