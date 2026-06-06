# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

import asyncio
from functools import partial

from mcp.server.fastmcp import FastMCP

from ibmi_mcp.config import IBMiConfig
from ibmi_mcp.transfer import FileTransport, get_transport
from ibmi_mcp.tn5250.session import Tn5250Session

try:
    import pyodbc

    _has_pyodbc = True
except ImportError:
    _has_pyodbc = False

mcp = FastMCP("ibmi-mcp")

_session: Tn5250Session | None = None
_transport: FileTransport | None = None
_config = IBMiConfig()
_last_connect: dict | None = None


_RECONNECT_WARNING = (
    "Session was re-established after a connection loss. "
    "Screen state may have changed — verify your position before continuing."
)


async def _reconnect_session() -> dict | None:
    global _session
    if _last_connect is None:
        return {"error": "Connection lost. Call connect() to re-establish."}
    _session = None
    result = await connect(**_last_connect)
    if "error" in result:
        return result
    return None


def _screen_response() -> dict:
    data = _session.screen.get_screen_data()
    if _session.timed_out:
        data["warning"] = "Host did not respond within timeout — screen may be incomplete"
    return data


# ── 5250 tools ───────────────────────────────────────────────────────────


@mcp.tool()
async def connect(host: str = "", port: int = 0, use_ssl: bool | None = None) -> dict:
    """Connect to an IBM i system via TN5250.

    Args:
        host: IBM i hostname or IP. Defaults to IBMI_HOST env var.
        port: TN5250 port. Defaults to IBMI_PORT env var or 23.
        use_ssl: Enable TLS. Defaults to IBMI_SSL env var.

    Returns the initial screen after connection.
    """
    global _session, _last_connect

    if _session is not None and _session.state.value != "disconnected":
        await _session.disconnect()

    cfg = _config.resolve_5250()
    resolved_host = host or cfg["host"]
    if not resolved_host:
        return {"error": "No host specified. Set IBMI_HOST or pass host parameter."}

    resolved_port = port or cfg["port"]
    resolved_ssl = use_ssl if use_ssl is not None else _config.ssl

    connect_host = resolved_host
    connect_port = resolved_port

    if _config.use_tunnel_5250():
        transport = await _ensure_transport()
        if isinstance(transport, dict):
            return transport
        try:
            local_port = await transport.forward_local_port(resolved_host, resolved_port)
            connect_host = "127.0.0.1"
            connect_port = local_port
        except Exception as e:
            return {"error": f"SSH tunnel failed: {e}"}

    _session = Tn5250Session(
        host=connect_host,
        port=connect_port,
        use_ssl=resolved_ssl,
        terminal_type=_config.terminal_type,
        device_name=_config.device_name,
        codepage=_config.codepage,
        username=cfg["user"],
        password=cfg["password"],
    )

    try:
        await _session.connect()
    except Exception as e:
        _session = None
        return {"error": f"Connection failed: {e}"}

    _last_connect = {"host": host, "port": port, "use_ssl": use_ssl}
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

    try:
        return _session.screen.get_screen_data()
    except OSError:
        err = await _reconnect_session()
        if err:
            return err
        data = _screen_response()
        data["warning"] = _RECONNECT_WARNING
        return data


@mcp.tool()
async def send_keys(text: str) -> dict:
    """Type text into the current input field at the cursor position.

    Args:
        text: The text to type.

    Returns the updated screen state.
    """
    if _session is None:
        return {"error": "Not connected. Call connect() first."}

    reconnected = False
    try:
        await _session.type_keys(text)
    except OSError:
        err = await _reconnect_session()
        if err:
            return err
        reconnected = True
        try:
            await _session.type_keys(text)
        except RuntimeError as e:
            return {"error": str(e)}
    except RuntimeError as e:
        return {"error": str(e)}

    data = _screen_response()
    if reconnected:
        data["warning"] = _RECONNECT_WARNING
    return data


async def _do_send_key(key_lower: str) -> dict | None:
    if key_lower == "attn":
        await _session.send_attention()
    elif key_lower == "tab":
        _move_to_next_field(forward=True)
    elif key_lower in ("backtab", "btab", "shift+tab"):
        _move_to_next_field(forward=False)
    elif _session.handle_local_key(key_lower):
        pass
    else:
        try:
            await _session.send_aid(key_lower)
        except ValueError as e:
            return {"error": str(e)}
    return None


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
    reconnected = False

    try:
        err = await _do_send_key(key_lower)
    except OSError:
        reconnect_err = await _reconnect_session()
        if reconnect_err:
            return reconnect_err
        reconnected = True
        err = await _do_send_key(key_lower)

    if err:
        return err
    data = _screen_response()
    if reconnected:
        data["warning"] = _RECONNECT_WARNING
    return data


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

    try:
        if row < 1 or row > _session.screen.rows:
            return {"error": f"Row must be between 1 and {_session.screen.rows}"}
        if col < 1 or col > _session.screen.cols:
            return {"error": f"Col must be between 1 and {_session.screen.cols}"}
        _session.move_cursor(row, col)
        return _screen_response()
    except OSError:
        err = await _reconnect_session()
        if err:
            return err
        _session.move_cursor(row, col)
        data = _screen_response()
        data["warning"] = _RECONNECT_WARNING
        return data


# ── File transfer tools ──────────────────────────────────────────────────


async def _ensure_transport() -> FileTransport | dict:
    global _transport
    if _transport is not None and _transport.is_connected:
        return _transport

    cfg = _config.resolve_sftp()
    if not cfg["host"]:
        return {"error": "No host configured. Set IBMI_HOST."}
    if not cfg["user"]:
        return {"error": "Credentials required. Set IBMI_USER and IBMI_PASSWORD."}

    _transport = get_transport(_config)
    try:
        await _transport.connect()
    except Exception as e:
        _transport = None
        return {"error": f"SSH connection failed: {e}"}
    return _transport


@mcp.tool()
async def upload_file(local_path: str, remote_path: str) -> dict:
    """Upload a file from the local system to the IBM i.

    Args:
        local_path: Path to the file on the local system.
        remote_path: Destination path on the IBM i (IFS path).

    Returns status with file details, or an error.
    """
    transport = await _ensure_transport()
    if isinstance(transport, dict):
        return transport
    return await transport.upload(local_path, remote_path)


@mcp.tool()
async def download_file(remote_path: str, local_path: str) -> dict:
    """Download a file from the IBM i to the local system.

    Args:
        remote_path: Path to the file on the IBM i (IFS path).
        local_path: Destination path on the local system.

    Returns status with file details, or an error.
    """
    transport = await _ensure_transport()
    if isinstance(transport, dict):
        return transport
    return await transport.download(remote_path, local_path)


# ── SQL tools ────────────────────────────────────────────────────────────


def _odbc_quote(value: str) -> str:
    if any(c in value for c in ";{}"):
        return "{" + value.replace("}", "}}") + "}"
    return value


def _build_connection_string() -> str:
    cfg = _config.resolve_sql()
    parts = [
        "DRIVER={IBM i Access ODBC Driver}",
        f"SYSTEM={_odbc_quote(cfg['host'])}",
        f"UID={_odbc_quote(cfg['user'])}",
        f"PWD={_odbc_quote(cfg['password'])}",
    ]
    if cfg["schema"]:
        parts.append(f"DBQ={_odbc_quote(cfg['schema'])}")
    parts.append("CCSID=1208")
    parts.append("TRIMCHAR=1")
    return ";".join(parts) + ";"


def _do_execute_sql(conn_str: str, statement: str) -> dict:
    conn = None
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        cursor.execute(statement)

        if cursor.description:
            columns = [col[0] for col in cursor.description]
            rows = [list(row) for row in cursor.fetchall()]
            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            }
        else:
            conn.commit()
            return {
                "status": "ok",
                "rows_affected": cursor.rowcount,
            }
    except pyodbc.Error as e:
        return {"error": f"SQL error: {e}"}
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


async def _ensure_sql() -> dict | None:
    if not _has_pyodbc:
        return {
            "error": (
                "pyodbc is not installed. "
                "Install ibmi-mcp with the sql extra: uvx \"ibmi-mcp[sql]\". "
                "The IBM i Access ODBC driver is also required."
            )
        }

    cfg = _config.resolve_sql()
    if not cfg["host"]:
        return {"error": "No host configured. Set IBMI_HOST or IBMI_HOST_SQL."}
    if not cfg["user"]:
        return {"error": "Credentials required. Set IBMI_USER or IBMI_USER_SQL."}
    return None


@mcp.tool()
async def execute_sql(statement: str) -> dict:
    """Execute a SQL statement on the IBM i.

    This tool runs any SQL statement including SELECT, INSERT, UPDATE, DELETE,
    CREATE, DROP, and other DDL/DML. Use with caution — statements that modify
    data or schema will be executed as provided.

    Args:
        statement: The SQL statement to execute.

    Returns query results with columns and rows for SELECT statements,
    or status with rows_affected for other statements.
    """
    err = await _ensure_sql()
    if err:
        return err

    conn_str = _build_connection_string()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_do_execute_sql, conn_str, statement))


# ── Internal helpers ─────────────────────────────────────────────────────


def _move_to_next_field(forward: bool = True) -> None:
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
