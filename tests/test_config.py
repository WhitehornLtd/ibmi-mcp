"""Tests for cascading configuration resolution."""

from ibmi_mcp.config import IBMiConfig


class TestResolve5250:
    def test_falls_back_to_global(self):
        cfg = IBMiConfig(host="global.example.com", user="guser", password="gpass")
        r = cfg.resolve_5250()
        assert r["host"] == "global.example.com"
        assert r["user"] == "guser"
        assert r["password"] == "gpass"

    def test_protocol_specific_overrides_global(self):
        cfg = IBMiConfig(
            host="global.example.com",
            user="guser",
            password="gpass",
            host_5250="tn.example.com",
            user_5250="tnuser",
            password_5250="tnpass",
        )
        r = cfg.resolve_5250()
        assert r["host"] == "tn.example.com"
        assert r["user"] == "tnuser"
        assert r["password"] == "tnpass"

    def test_partial_override(self):
        cfg = IBMiConfig(host="global.example.com", user="guser", password="gpass", host_5250="tn.example.com")
        r = cfg.resolve_5250()
        assert r["host"] == "tn.example.com"
        assert r["user"] == "guser"
        assert r["password"] == "gpass"

    def test_port_default(self):
        cfg = IBMiConfig()
        assert cfg.resolve_5250()["port"] == 23


class TestResolveSftp:
    def test_falls_back_to_global(self):
        cfg = IBMiConfig(host="global.example.com", user="guser", password="gpass")
        r = cfg.resolve_sftp()
        assert r["host"] == "global.example.com"
        assert r["user"] == "guser"
        assert r["password"] == "gpass"

    def test_protocol_specific_overrides_global(self):
        cfg = IBMiConfig(
            host="global.example.com",
            user="guser",
            host_sftp="sftp.example.com",
            user_sftp="sftpuser",
        )
        r = cfg.resolve_sftp()
        assert r["host"] == "sftp.example.com"
        assert r["user"] == "sftpuser"

    def test_port_default(self):
        cfg = IBMiConfig()
        assert cfg.resolve_sftp()["port"] == 22


class TestResolveSql:
    def test_falls_back_to_global(self):
        cfg = IBMiConfig(host="global.example.com", user="guser", password="gpass")
        r = cfg.resolve_sql()
        assert r["host"] == "global.example.com"
        assert r["user"] == "guser"
        assert r["password"] == "gpass"

    def test_protocol_specific_overrides_global(self):
        cfg = IBMiConfig(
            host="global.example.com",
            host_sql="sql.example.com",
            user_sql="sqluser",
            password_sql="sqlpass",
        )
        r = cfg.resolve_sql()
        assert r["host"] == "sql.example.com"
        assert r["user"] == "sqluser"
        assert r["password"] == "sqlpass"

    def test_port_default(self):
        cfg = IBMiConfig()
        assert cfg.resolve_sql()["port"] == 8471

    def test_schema(self):
        cfg = IBMiConfig(db_schema="MYLIB")
        assert cfg.resolve_sql()["schema"] == "MYLIB"

    def test_schema_empty_by_default(self):
        cfg = IBMiConfig()
        assert cfg.resolve_sql()["schema"] == ""


class TestTunnelResolution:
    def test_tunnel_5250_inherits_global(self):
        cfg = IBMiConfig(ssh_tunnel=True)
        assert cfg.use_tunnel_5250() is True

    def test_tunnel_5250_inherits_global_false(self):
        cfg = IBMiConfig(ssh_tunnel=False)
        assert cfg.use_tunnel_5250() is False

    def test_tunnel_5250_overrides_global(self):
        cfg = IBMiConfig(ssh_tunnel=True, ssh_tunnel_5250=False)
        assert cfg.use_tunnel_5250() is False

    def test_tunnel_5250_overrides_global_inverse(self):
        cfg = IBMiConfig(ssh_tunnel=False, ssh_tunnel_5250=True)
        assert cfg.use_tunnel_5250() is True

    def test_tunnel_5250_none_falls_back(self):
        cfg = IBMiConfig(ssh_tunnel=True, ssh_tunnel_5250=None)
        assert cfg.use_tunnel_5250() is True
