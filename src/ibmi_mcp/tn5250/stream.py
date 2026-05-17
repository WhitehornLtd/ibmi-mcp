# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

import asyncio
import logging
import ssl
from collections.abc import Callable, Coroutine
from typing import Any

from ibmi_mcp.tn5250.constants import (
    DO,
    DONT,
    EOR,
    IAC,
    SB,
    SE,
    WILL,
    WONT,
)

logger = logging.getLogger(__name__)

TelnetOptionHandler = Callable[[int, int], Coroutine[Any, Any, None]]
TelnetSBHandler = Callable[[int, bytes], Coroutine[Any, Any, None]]


class TelnetStream:
    def __init__(self):
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pushback: list[int] = []
        self.on_option: TelnetOptionHandler | None = None
        self.on_subnegotiation: TelnetSBHandler | None = None

    async def connect(self, host: str, port: int, use_ssl: bool = False) -> None:
        ssl_ctx = None
        if use_ssl:
            ssl_ctx = ssl.create_default_context()
        self._reader, self._writer = await asyncio.open_connection(
            host, port, ssl=ssl_ctx
        )

    async def close(self) -> None:
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
            self._reader = None

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def _read_raw_byte(self) -> int:
        if self._pushback:
            return self._pushback.pop(0)
        data = await self._reader.readexactly(1)
        return data[0]

    async def read_frame(self) -> bytes:
        """Read a 5250 data frame delimited by IAC EOR.

        Telnet commands (DO/WILL/DONT/WONT/SB) encountered during reading
        are handled transparently via the registered callbacks and stripped
        from the returned data.
        """
        buf = bytearray()
        while True:
            b = await self._read_raw_byte()
            if b == IAC:
                b2 = await self._read_raw_byte()
                if b2 == EOR:
                    break
                elif b2 == IAC:
                    buf.append(IAC)
                elif b2 in (DO, DONT, WILL, WONT):
                    opt = await self._read_raw_byte()
                    if self.on_option:
                        await self.on_option(b2, opt)
                elif b2 == SB:
                    await self._read_subnegotiation()
                else:
                    logger.debug(f"Unknown IAC command: {b2:#x}")
            else:
                buf.append(b)
        return bytes(buf)

    async def _read_subnegotiation(self) -> None:
        """Read a subnegotiation (SB ... SE) and dispatch to handler."""
        sb_buf = bytearray()
        while True:
            b = await self._read_raw_byte()
            if b == IAC:
                b2 = await self._read_raw_byte()
                if b2 == SE:
                    break
                elif b2 == IAC:
                    sb_buf.append(IAC)
                else:
                    sb_buf.append(IAC)
                    sb_buf.append(b2)
            else:
                sb_buf.append(b)
        if sb_buf and self.on_subnegotiation:
            await self.on_subnegotiation(sb_buf[0], bytes(sb_buf[1:]))

    async def write_raw(self, data: bytes) -> None:
        self._writer.write(data)
        await self._writer.drain()

    async def write_frame(self, data: bytes) -> None:
        """Write a telnet frame, escaping IAC bytes and appending IAC EOR."""
        buf = bytearray()
        for b in data:
            if b == IAC:
                buf.append(IAC)
                buf.append(IAC)
            else:
                buf.append(b)
        buf.append(IAC)
        buf.append(EOR)
        await self.write_raw(bytes(buf))
