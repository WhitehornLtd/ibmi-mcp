# ibmi-mcp

Give your AI Agent terminal access to your IBM i system via TN5250.

ibmi-mcp is an MCP server that lets AI Agents like Claude interact with IBM i the same way a human would through a 5250 green-screen terminal.

## Installation

Install and register with Claude Code:

```bash
claude mcp add ibmi-5250 -- uvx ibmi-mcp
```

## Configuration

Configure the connection using environment variables:

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `IBMI_HOST` | IBM i hostname or IP | Yes | — |
| `IBMI_PORT` | TN5250 port | No | 23 |
| `IBMI_SSL` | Enable TLS | No | false |
| `IBMI_USER` | Username for auto-signon | No | — |
| `IBMI_PASSWORD` | Password for auto-signon | No | — |
| `IBMI_DEVICE_NAME` | Virtual device name | No | — |
| `IBMI_CODEPAGE` | EBCDIC codepage | No | cp037 |
| `IBMI_TERMINAL_TYPE` | Terminal type | No | IBM-3179-2 |

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

## Features

- **Auto-signon** — Automatically detects sign-on screens and logs in with configured credentials
- **Full key support** — Enter, F1-F24, PageUp, PageDown, Tab, Backtab, Clear, Help, Print, Attn
- **Local editing** — Backspace, Delete, Field Exit, Home, and End handled locally for responsive editing
- **Structured screen data** — Returns screen text, cursor position, and input field metadata
- **Configurable codepage** — Supports EBCDIC codepage translation (default: CP037)

## License

BSD 2-Clause. See [LICENSE](LICENSE) for details.

## About Whitehorn Ltd. Co.

ibmi-mcp is developed and maintained by Whitehorn Ltd. Co., a legacy system modernization firm. We specialize in IBM i, RPG, COBOL, and midrange platforms. We help our clients protect what they can't afford to break while building a path forward.

Learn more about how Whitehorn Ltd. Co. can help you modernize your IBM midrange systems at [whitehorn.ltd](https://whitehorn.ltd).
