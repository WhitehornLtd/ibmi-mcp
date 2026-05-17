# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

from ibmi_mcp.server import mcp


def main():
    mcp.run(transport="stdio")
