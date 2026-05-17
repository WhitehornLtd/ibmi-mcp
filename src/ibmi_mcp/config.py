# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

from pydantic_settings import BaseSettings


class IBMiConfig(BaseSettings):
    model_config = {"env_prefix": "IBMI_"}

    host: str = ""
    port: int = 23
    ssl: bool = False
    user: str = ""
    password: str = ""
    device_name: str = ""
    codepage: str = "cp037"
    terminal_type: str = "IBM-3179-2"
