# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

from pydantic_settings import BaseSettings


class IBMiConfig(BaseSettings):
    model_config = {"env_prefix": "IBMI_"}

    # Global defaults
    host: str = ""
    user: str = ""
    password: str = ""

    # 5250-specific overrides
    host_5250: str = ""
    port: int = 23
    ssl: bool = False
    user_5250: str = ""
    password_5250: str = ""
    device_name: str = ""
    codepage: str = "cp037"
    terminal_type: str = "IBM-3179-2"

    # SSH/SFTP-specific overrides
    host_sftp: str = ""
    user_sftp: str = ""
    password_sftp: str = ""
    ssh_port: int = 22
    ssh_key_file: str = ""
    ssh_known_hosts: str = ""

    # SSH tunnel settings
    ssh_tunnel: bool = False
    ssh_tunnel_5250: bool | None = None
    ssh_tunnel_sql: bool | None = None

    # SQL-specific overrides
    host_sql: str = ""
    port_sql: int = 8471
    user_sql: str = ""
    password_sql: str = ""
    db_schema: str = ""

    def resolve_5250(self) -> dict:
        return {
            "host": self.host_5250 or self.host,
            "port": self.port,
            "user": self.user_5250 or self.user,
            "password": self.password_5250 or self.password,
        }

    def resolve_sftp(self) -> dict:
        return {
            "host": self.host_sftp or self.host,
            "port": self.ssh_port,
            "user": self.user_sftp or self.user,
            "password": self.password_sftp or self.password,
        }

    def resolve_sql(self) -> dict:
        return {
            "host": self.host_sql or self.host,
            "port": self.port_sql,
            "user": self.user_sql or self.user,
            "password": self.password_sql or self.password,
            "schema": self.db_schema,
        }

    def use_tunnel_5250(self) -> bool:
        if self.ssh_tunnel_5250 is not None:
            return self.ssh_tunnel_5250
        return self.ssh_tunnel

    def use_tunnel_sql(self) -> bool:
        if self.ssh_tunnel_sql is not None:
            return self.ssh_tunnel_sql
        return self.ssh_tunnel
