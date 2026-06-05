# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

from ibmi_mcp.config import IBMiConfig
from ibmi_mcp.transfer.base import FileTransport
from ibmi_mcp.transfer.sftp import SftpTransport

__all__ = ["FileTransport", "get_transport"]


def get_transport(config: IBMiConfig) -> FileTransport:
    return SftpTransport(config)
