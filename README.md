# ibmi-mcp

Give your AI Agent terminal, file transfer, and SQL access to your IBM i system.

ibmi-mcp is an MCP server that lets AI Agents like Claude interact with IBM i through 5250 terminal emulation, SFTP file transfer, and SQL queries.

## Installation

Register with Claude Code:

```bash
claude mcp add ibmi-mcp -- uvx ibmi-mcp
```

This requires the connection environment variables to be set in your shell profile. You can also pass them inline with `-e` flags:

```bash
claude mcp add ibmi-mcp \
  -e IBMI_HOST=myhost.example.com \
  -e IBMI_USER=myuser \
  -e IBMI_PASSWORD=mypassword \
  -- uvx ibmi-mcp
```

### SQL support (optional)

SQL access requires the IBM i Access ODBC driver and the `pyodbc` Python package.

To include `pyodbc` when launching via `uvx`, use the `[sql]` extra:

```bash
claude mcp add ibmi-mcp -- uvx "ibmi-mcp[sql]"
```

Or if you've already registered ibmi-mcp without SQL, you can re-register with:

```bash
claude mcp remove ibmi-mcp
claude mcp add ibmi-mcp -- uvx "ibmi-mcp[sql]"
```

You also need the IBM i Access ODBC driver installed on your system. On macOS:

```bash
brew install unixodbc
brew tap ibm/iaccess https://public.dhe.ibm.com/software/ibmi/products/odbc/macos/tap/
brew install ibm-iaccess
```

The 5250 terminal and file transfer features work without these dependencies.

## Configuration

Global settings apply to all protocols. Protocol-specific overrides (e.g., `IBMI_HOST_SQL`) take precedence when set.

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `IBMI_HOST` | IBM i hostname or IP | Yes | — |
| `IBMI_USER` | Username | No | — |
| `IBMI_PASSWORD` | Password | No | — |
| `IBMI_PORT` | TN5250 port | No | 23 |
| `IBMI_SSL` | Enable TLS for TN5250 | No | false |
| `IBMI_DEVICE_NAME` | Virtual device name | No | — |
| `IBMI_CODEPAGE` | EBCDIC codepage | No | cp037 |
| `IBMI_TERMINAL_TYPE` | Terminal type | No | IBM-3179-2 |
| `IBMI_SSH_TUNNEL` | Tunnel traffic through SSH | No | false |
| `IBMI_SSH_TUNNEL_5250` | Override tunnel for 5250 only | No | — |
| `IBMI_SSH_PORT` | SSH port | No | 22 |
| `IBMI_SSH_KEY_FILE` | Path to SSH private key | No | — |
| `IBMI_SSH_KNOWN_HOSTS` | Path to known_hosts file | No | — |
| `IBMI_PORT_SQL` | SQL database host server port | No | 8471 |
| `IBMI_DB_SCHEMA` | Default schema/library for SQL | No | — |

Protocol-specific host, user, and password overrides are also available: `IBMI_HOST_5250`, `IBMI_HOST_SFTP`, `IBMI_HOST_SQL`, `IBMI_USER_5250`, `IBMI_USER_SFTP`, `IBMI_USER_SQL`, `IBMI_PASSWORD_5250`, `IBMI_PASSWORD_SFTP`, `IBMI_PASSWORD_SQL`.

When `IBMI_USER` and `IBMI_PASSWORD` are set, ibmi-mcp will automatically sign on when it detects a login screen after connecting.

## Tools

| Tool | Description |
|------|-------------|
| `connect` | Connect to an IBM i system via TN5250 |
| `disconnect` | Disconnect the active session |
| `read_screen` | Read the current screen content and input fields |
| `send_keys` | Type text into the current input field |
| `send_key` | Send a function/attention key (Enter, F1-F24, PageUp, PageDown, Tab, etc.) |
| `set_cursor` | Position the cursor at a specific row and column |
| `upload_file` | Upload a file from the local system to the IBM i |
| `download_file` | Download a file from the IBM i to the local system |
| `execute_sql` | Execute a SQL statement on the IBM i |

## Features

- **Auto-signon** — Automatically detects sign-on screens and logs in with configured credentials
- **SQL access** — Execute SQL statements via ODBC (requires IBM i Access ODBC driver)
- **File transfer** — Upload and download files to/from the IBM i IFS via SFTP
- **SSH tunneling** — Tunnel TN5250 through SSH when port 23 is not directly reachable
- **Connection resilience** — Automatic reconnect and retry on connection loss
- **Full key support** — Enter, F1-F24, PageUp, PageDown, Tab, Backtab, Clear, Help, Print, Attn
- **Local editing** — Backspace, Delete, Field Exit, Home, and End handled locally for responsive editing
- **Structured screen data** — Returns screen text, cursor position, and input field metadata
- **Configurable codepage** — Supports EBCDIC codepage translation (default: CP037)
- **Per-protocol configuration** — Override host, credentials, and settings per protocol (5250, SFTP, SQL)

## License

BSD 2-Clause. See [LICENSE](LICENSE) for details.

## About Whitehorn Ltd. Co.

ibmi-mcp is developed and maintained by Whitehorn Ltd. Co., a legacy system modernization firm. We specialize in IBM i, RPG, COBOL, and midrange platforms. We help our clients protect what they can't afford to break while building a path forward.

Learn more about how Whitehorn Ltd. Co. can help you modernize your IBM midrange systems at [whitehorn.ltd](https://whitehorn.ltd).
