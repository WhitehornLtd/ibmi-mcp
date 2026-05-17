# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

import logging

from ibmi_mcp.tn5250.constants import (
    DO,
    DONT,
    IAC,
    NE_IS,
    NE_USERVAR,
    NE_VALUE,
    NE_VAR,
    OPT_BINARY,
    OPT_END_OF_RECORD,
    OPT_NEW_ENVIRON,
    OPT_TERMINAL_TYPE,
    SB,
    SE,
    TT_IS,
    TT_SEND,
    WILL,
    WONT,
)
from ibmi_mcp.tn5250.stream import TelnetStream

logger = logging.getLogger(__name__)


class TelnetNegotiator:
    """Handles telnet option negotiation via stream callbacks.

    Register this with a TelnetStream before reading frames. It responds
    to DO/WILL/SB commands automatically, so they're handled transparently
    during frame reading.
    """

    def __init__(
        self,
        stream: TelnetStream,
        terminal_type: str = "IBM-3179-2",
        device_name: str = "",
        codepage: str = "037",
        username: str = "",
    ):
        self._stream = stream
        self._terminal_type = terminal_type
        self._device_name = device_name
        self._codepage = codepage
        self._username = username

        stream.on_option = self._handle_option
        stream.on_subnegotiation = self._handle_subnegotiation

    async def run_initial_negotiation(self) -> None:
        """Read and respond to telnet commands until the first data byte arrives.

        Once a non-IAC byte is seen, it's pushed back for read_frame() to consume.
        """
        while True:
            b = await self._stream._read_raw_byte()
            if b == 0xFF:
                b2 = await self._stream._read_raw_byte()
                if b2 in (DO, DONT, WILL, WONT):
                    opt = await self._stream._read_raw_byte()
                    await self._handle_option(b2, opt)
                elif b2 == SB:
                    await self._stream._read_subnegotiation()
                else:
                    logger.debug(f"IAC {b2:#x} during negotiation")
            else:
                self._stream._pushback.append(b)
                return

    async def _handle_option(self, cmd: int, opt: int) -> None:
        if cmd == DO:
            if opt in (OPT_BINARY, OPT_END_OF_RECORD, OPT_TERMINAL_TYPE, OPT_NEW_ENVIRON):
                await self._stream.write_raw(bytes([IAC, WILL, opt]))
                logger.debug(f"WILL {opt:#x}")
            else:
                await self._stream.write_raw(bytes([IAC, WONT, opt]))
                logger.debug(f"WONT {opt:#x}")
        elif cmd == WILL:
            if opt in (OPT_BINARY, OPT_END_OF_RECORD):
                await self._stream.write_raw(bytes([IAC, DO, opt]))
                logger.debug(f"DO {opt:#x}")
            else:
                await self._stream.write_raw(bytes([IAC, DONT, opt]))
                logger.debug(f"DONT {opt:#x}")

    async def _handle_subnegotiation(self, opt: int, data: bytes) -> None:
        if opt == OPT_TERMINAL_TYPE and len(data) > 0 and data[0] == TT_SEND:
            await self._send_terminal_type()
        elif opt == OPT_NEW_ENVIRON:
            await self._send_new_environ()

    async def _send_terminal_type(self) -> None:
        tt_bytes = self._terminal_type.encode("ascii")
        response = bytes([IAC, SB, OPT_TERMINAL_TYPE, TT_IS]) + tt_bytes + bytes([IAC, SE])
        await self._stream.write_raw(response)
        logger.debug(f"Sent terminal type: {self._terminal_type}")

    async def _send_new_environ(self) -> None:
        response = bytearray([IAC, SB, OPT_NEW_ENVIRON, NE_IS])

        if self._username:
            response.append(NE_VAR)
            response.extend(b"USER")
            response.append(NE_VALUE)
            response.extend(self._username.upper().encode("ascii"))

        if self._device_name:
            response.append(NE_USERVAR)
            response.extend(b"DEVNAME")
            response.append(NE_VALUE)
            response.extend(self._device_name.encode("ascii"))

        response.append(NE_USERVAR)
        response.extend(b"KBDTYPE")
        response.append(NE_VALUE)
        response.extend(b"USB")

        response.append(NE_USERVAR)
        response.extend(b"CODEPAGE")
        response.append(NE_VALUE)
        response.extend(self._codepage.encode("ascii"))

        response.append(NE_USERVAR)
        response.extend(b"IBMRSEED")
        response.append(NE_VALUE)
        response.extend(bytes(8))

        response.extend(bytes([IAC, SE]))
        await self._stream.write_raw(bytes(response))
        logger.debug("Sent NEW-ENVIRON response")
