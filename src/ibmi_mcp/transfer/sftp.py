# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

import errno
from pathlib import Path

import asyncssh

from ibmi_mcp.config import IBMiConfig
from ibmi_mcp.transfer.base import FileTransport

_RETRY_ERRNOS = {
    errno.ETIMEDOUT, errno.ECONNRESET, errno.ECONNREFUSED,
    errno.ENOTCONN, errno.EPIPE, errno.ENETUNREACH, errno.EHOSTUNREACH,
}


class SftpTransport(FileTransport):
    def __init__(self, config: IBMiConfig):
        self._config = config
        self._conn: asyncssh.SSHClientConnection | None = None
        self._sftp: asyncssh.SFTPClient | None = None
        self._tunnel_listener: asyncssh.SSHListener | None = None

    async def connect(self) -> None:
        cfg = self._config.resolve_sftp()
        kwargs: dict = {
            "host": cfg["host"],
            "port": cfg["port"],
            "username": cfg["user"],
            "known_hosts": self._config.ssh_known_hosts or None,
        }

        if self._config.ssh_key_file:
            kwargs["client_keys"] = [self._config.ssh_key_file]
        if cfg["password"]:
            kwargs["password"] = cfg["password"]

        self._conn = await asyncssh.connect(**kwargs)
        self._sftp = await self._conn.start_sftp_client()

    async def disconnect(self) -> None:
        if self._tunnel_listener is not None:
            self._tunnel_listener.close()
            self._tunnel_listener = None
        if self._sftp is not None:
            self._sftp.exit()
            self._sftp = None
        if self._conn is not None:
            self._conn.close()
            await self._conn.wait_closed()
            self._conn = None

    @property
    def is_connected(self) -> bool:
        return (
            self._conn is not None
            and not self._conn.is_closed()
            and self._sftp is not None
        )

    def _is_connection_error(self, exc: Exception) -> bool:
        if isinstance(exc, OSError) and exc.errno in _RETRY_ERRNOS:
            return True
        if isinstance(exc, (asyncssh.ConnectionLost, asyncssh.DisconnectError)):
            return True
        return False

    async def _reconnect(self) -> None:
        await self.disconnect()
        await self.connect()

    async def upload(self, local_path: str, remote_path: str) -> dict:
        local = Path(local_path)
        if not local.exists():
            return {"error": f"Local file not found: {local_path}"}
        if not local.is_file():
            return {"error": f"Not a file: {local_path}"}

        for attempt in range(2):
            try:
                await self._sftp.put(local_path, remote_path)
                size = local.stat().st_size
                return {
                    "status": "uploaded",
                    "local_path": local_path,
                    "remote_path": remote_path,
                    "bytes": size,
                }
            except (asyncssh.SFTPError, OSError) as e:
                if attempt == 0 and self._is_connection_error(e):
                    await self._reconnect()
                    continue
                if isinstance(e, asyncssh.SFTPError):
                    return {"error": f"SFTP error: {e}"}
                return {"error": f"File error: {e}"}
        return {"error": "Upload failed after reconnect"}

    async def download(self, remote_path: str, local_path: str) -> dict:
        for attempt in range(2):
            try:
                await self._sftp.get(remote_path, local_path)
                size = Path(local_path).stat().st_size
                return {
                    "status": "downloaded",
                    "remote_path": remote_path,
                    "local_path": local_path,
                    "bytes": size,
                }
            except (asyncssh.SFTPError, OSError) as e:
                if attempt == 0 and self._is_connection_error(e):
                    await self._reconnect()
                    continue
                if isinstance(e, asyncssh.SFTPError):
                    return {"error": f"SFTP error: {e}"}
                return {"error": f"File error: {e}"}
        return {"error": "Download failed after reconnect"}

    async def forward_local_port(
        self, remote_host: str, remote_port: int, local_port: int = 0
    ) -> int:
        if self._tunnel_listener is not None:
            self._tunnel_listener.close()
        self._tunnel_listener = await self._conn.forward_local_port(
            "", local_port, remote_host, remote_port
        )
        return self._tunnel_listener.get_port()
