"""Tests for SQL execution."""

# TODO: migrate from deprecated asyncio.get_event_loop().run_until_complete() to asyncio.run()
import asyncio
from unittest.mock import MagicMock, patch

import pytest

import ibmi_mcp.server as server
from ibmi_mcp.config import IBMiConfig


class TestBuildConnectionString:
    def setup_method(self):
        self._original_config = server._config

    def teardown_method(self):
        server._config = self._original_config

    def test_basic_connection_string(self):
        server._config = IBMiConfig(host="myhost", user="myuser", password="mypass")
        cs = server._build_connection_string()
        assert "SYSTEM=myhost" in cs
        assert "UID=myuser" in cs
        assert "PWD=mypass" in cs
        assert "DRIVER={IBM i Access ODBC Driver}" in cs
        assert "CCSID=1208" in cs

    def test_connection_string_with_schema(self):
        server._config = IBMiConfig(host="myhost", user="myuser", password="mypass", db_schema="MYLIB")
        cs = server._build_connection_string()
        assert "DBQ=MYLIB" in cs

    def test_connection_string_without_schema(self):
        server._config = IBMiConfig(host="myhost", user="myuser", password="mypass")
        cs = server._build_connection_string()
        assert "DBQ" not in cs

    def test_connection_string_uses_sql_override(self):
        server._config = IBMiConfig(host="global", user="guser", password="gpass", host_sql="sqlhost", user_sql="sqluser")
        cs = server._build_connection_string()
        assert "SYSTEM=sqlhost" in cs
        assert "UID=sqluser" in cs
        assert "PWD=gpass" in cs

    def test_password_with_semicolon_is_escaped(self):
        server._config = IBMiConfig(host="myhost", user="myuser", password="pass;word")
        cs = server._build_connection_string()
        assert "PWD={pass;word}" in cs

    def test_password_with_closing_brace_is_escaped(self):
        server._config = IBMiConfig(host="myhost", user="myuser", password="pass}word")
        cs = server._build_connection_string()
        assert "PWD={pass}}word}" in cs


class TestEnsureSql:
    def test_missing_pyodbc(self):
        server._config = IBMiConfig(host="myhost", user="myuser", password="mypass")
        original = server._has_pyodbc
        server._has_pyodbc = False
        try:
            result = asyncio.get_event_loop().run_until_complete(server._ensure_sql())
            assert "error" in result
            assert "pyodbc" in result["error"]
        finally:
            server._has_pyodbc = original

    def test_missing_host(self):
        server._config = IBMiConfig(user="myuser", password="mypass")
        original = server._has_pyodbc
        server._has_pyodbc = True
        try:
            result = asyncio.get_event_loop().run_until_complete(server._ensure_sql())
            assert "error" in result
            assert "host" in result["error"].lower()
        finally:
            server._has_pyodbc = original

    def test_missing_user(self):
        server._config = IBMiConfig(host="myhost", password="mypass")
        original = server._has_pyodbc
        server._has_pyodbc = True
        try:
            result = asyncio.get_event_loop().run_until_complete(server._ensure_sql())
            assert "error" in result
            assert "credentials" in result["error"].lower()
        finally:
            server._has_pyodbc = original

    def test_valid_config(self):
        server._config = IBMiConfig(host="myhost", user="myuser", password="mypass")
        original = server._has_pyodbc
        server._has_pyodbc = True
        try:
            result = asyncio.get_event_loop().run_until_complete(server._ensure_sql())
            assert result is None
        finally:
            server._has_pyodbc = original


class TestDoExecuteSql:
    def _make_pyodbc_mock(self):
        mock = MagicMock()
        mock.Error = type("Error", (Exception,), {})
        return mock

    @patch.dict("sys.modules", {"pyodbc": MagicMock()})
    def test_select_returns_columns_and_rows(self):
        mock_pyodbc = self._make_pyodbc_mock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("ID",), ("NAME",)]
        mock_cursor.fetchall.return_value = [[1, "Alice"], [2, "Bob"]]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        with patch.object(server, "pyodbc", mock_pyodbc, create=True):
            server._has_pyodbc = True
            result = server._do_execute_sql("DSN=test", "SELECT * FROM TEST")

        assert result["columns"] == ["ID", "NAME"]
        assert result["rows"] == [[1, "Alice"], [2, "Bob"]]
        assert result["row_count"] == 2
        mock_conn.close.assert_called_once()

    @patch.dict("sys.modules", {"pyodbc": MagicMock()})
    def test_insert_returns_rows_affected(self):
        mock_pyodbc = self._make_pyodbc_mock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.rowcount = 3
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        with patch.object(server, "pyodbc", mock_pyodbc, create=True):
            server._has_pyodbc = True
            result = server._do_execute_sql("DSN=test", "INSERT INTO TEST VALUES (1)")

        assert result["status"] == "ok"
        assert result["rows_affected"] == 3
        mock_conn.close.assert_called_once()

    @patch.dict("sys.modules", {"pyodbc": MagicMock()})
    def test_dml_is_committed(self):
        mock_pyodbc = self._make_pyodbc_mock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.rowcount = 1
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        with patch.object(server, "pyodbc", mock_pyodbc, create=True):
            server._has_pyodbc = True
            server._do_execute_sql("DSN=test", "INSERT INTO TEST VALUES (1)")

        mock_conn.commit.assert_called_once()

    @patch.dict("sys.modules", {"pyodbc": MagicMock()})
    def test_sql_error_returns_error_dict(self):
        mock_pyodbc = self._make_pyodbc_mock()
        mock_pyodbc.connect.side_effect = mock_pyodbc.Error("table not found")

        with patch.object(server, "pyodbc", mock_pyodbc, create=True):
            server._has_pyodbc = True
            result = server._do_execute_sql("DSN=test", "SELECT * FROM NOPE")

        assert "error" in result
        assert "table not found" in result["error"]

    @patch.dict("sys.modules", {"pyodbc": MagicMock()})
    def test_connection_closed_on_error(self):
        mock_pyodbc = self._make_pyodbc_mock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = mock_pyodbc.Error("bad sql")
        mock_conn.cursor.return_value = mock_cursor
        mock_pyodbc.connect.return_value = mock_conn

        with patch.object(server, "pyodbc", mock_pyodbc, create=True):
            server._has_pyodbc = True
            server._do_execute_sql("DSN=test", "BAD SQL")

        mock_conn.close.assert_called_once()
