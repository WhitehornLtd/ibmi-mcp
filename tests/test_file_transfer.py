"""Tests for file transfer transport."""

# TODO: migrate from deprecated asyncio.get_event_loop().run_until_complete() to asyncio.run()
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import asyncssh
import pytest

from ibmi_mcp.config import IBMiConfig
from ibmi_mcp.transfer.sftp import SftpTransport


class TestSftpTransportConnect:
    def test_not_connected_initially(self):
        transport = SftpTransport(IBMiConfig(host="test"))
        assert transport.is_connected is False

    @patch("ibmi_mcp.transfer.sftp.asyncssh")
    def test_connect_uses_resolved_sftp_config(self, mock_asyncssh):
        config = IBMiConfig(
            host="global.example.com",
            user="guser",
            password="gpass",
            host_sftp="sftp.example.com",
            user_sftp="sftpuser",
        )
        transport = SftpTransport(config)

        mock_conn = AsyncMock()
        mock_conn.is_closed.return_value = False
        mock_conn.start_sftp_client = AsyncMock(return_value=MagicMock())
        mock_asyncssh.connect = AsyncMock(return_value=mock_conn)

        asyncio.get_event_loop().run_until_complete(transport.connect())

        call_kwargs = mock_asyncssh.connect.call_args[1]
        assert call_kwargs["host"] == "sftp.example.com"
        assert call_kwargs["username"] == "sftpuser"
        assert call_kwargs["password"] == "gpass"


class TestSftpUpload:
    @patch("ibmi_mcp.transfer.sftp.asyncssh")
    def test_upload_missing_file(self, mock_asyncssh):
        transport = SftpTransport(IBMiConfig(host="test"))
        transport._conn = MagicMock()
        transport._sftp = AsyncMock()

        result = asyncio.get_event_loop().run_until_complete(
            transport.upload("/nonexistent/path.txt", "/remote/path.txt")
        )
        assert "error" in result
        assert "not found" in result["error"]

    @patch("ibmi_mcp.transfer.sftp.asyncssh")
    def test_upload_success(self, mock_asyncssh, tmp_path):
        local_file = tmp_path / "test.txt"
        local_file.write_text("hello")

        transport = SftpTransport(IBMiConfig(host="test"))
        transport._conn = MagicMock()
        transport._conn.is_closed.return_value = False
        transport._sftp = AsyncMock()
        transport._sftp.put = AsyncMock()

        result = asyncio.get_event_loop().run_until_complete(
            transport.upload(str(local_file), "/remote/test.txt")
        )
        assert result["status"] == "uploaded"
        assert result["bytes"] == 5
        transport._sftp.put.assert_called_once()


class TestSftpDownload:
    @patch("ibmi_mcp.transfer.sftp.asyncssh")
    def test_download_success(self, mock_asyncssh, tmp_path):
        local_file = tmp_path / "downloaded.txt"

        transport = SftpTransport(IBMiConfig(host="test"))
        transport._conn = MagicMock()
        transport._conn.is_closed.return_value = False
        transport._sftp = AsyncMock()

        async def fake_get(remote, local):
            Path(local).write_text("content")

        transport._sftp.get = fake_get

        result = asyncio.get_event_loop().run_until_complete(
            transport.download("/remote/file.txt", str(local_file))
        )
        assert result["status"] == "downloaded"
        assert result["bytes"] == 7


class TestSftpRetry:
    def test_upload_retries_on_connection_error(self, tmp_path):
        local_file = tmp_path / "test.txt"
        local_file.write_text("hello")

        transport = SftpTransport(IBMiConfig(host="test", user="u", password="p"))

        call_count = 0
        mock_sftp = AsyncMock()

        async def put_with_failure(local, remote):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError(60, "Operation timed out")

        mock_sftp.put = put_with_failure
        mock_sftp.exit = MagicMock()

        mock_conn = MagicMock()
        mock_conn.is_closed.return_value = False
        mock_conn.close = MagicMock()
        mock_conn.wait_closed = AsyncMock()

        transport._conn = mock_conn
        transport._sftp = mock_sftp

        mock_new_conn = MagicMock()
        mock_new_conn.is_closed.return_value = False
        mock_new_conn.start_sftp_client = AsyncMock(return_value=mock_sftp)

        with patch("asyncssh.connect", AsyncMock(return_value=mock_new_conn)):
            result = asyncio.get_event_loop().run_until_complete(
                transport.upload(str(local_file), "/remote/test.txt")
            )
        assert result["status"] == "uploaded"
        assert call_count == 2


class TestSftpPortForward:
    def test_forward_stores_listener(self):
        transport = SftpTransport(IBMiConfig(host="test"))
        mock_listener = MagicMock()
        mock_listener.get_port.return_value = 54321
        transport._conn = AsyncMock()
        transport._conn.forward_local_port = AsyncMock(return_value=mock_listener)

        port = asyncio.get_event_loop().run_until_complete(
            transport.forward_local_port("remote", 23)
        )
        assert port == 54321
        assert transport._tunnel_listener is mock_listener

    def test_disconnect_closes_listener(self):
        transport = SftpTransport(IBMiConfig(host="test"))
        mock_listener = MagicMock()
        transport._tunnel_listener = mock_listener
        transport._conn = AsyncMock()
        transport._sftp = MagicMock()

        asyncio.get_event_loop().run_until_complete(transport.disconnect())
        mock_listener.close.assert_called_once()
        assert transport._tunnel_listener is None
