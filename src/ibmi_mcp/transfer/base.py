# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

from abc import ABC, abstractmethod


class FileTransport(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @abstractmethod
    async def upload(self, local_path: str, remote_path: str) -> dict: ...

    @abstractmethod
    async def download(self, remote_path: str, local_path: str) -> dict: ...

    async def forward_local_port(self, remote_host: str, remote_port: int) -> int:
        raise NotImplementedError
