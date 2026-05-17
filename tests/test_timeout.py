"""Tests for timeout handling in session operations."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ibmi_mcp.server import _screen_response
from ibmi_mcp.tn5250.session import Tn5250Session


class TestProcessUntilUnlockedTimeout:
    """Verify that _process_until_unlocked surfaces timeout state."""

    def test_timeout_sets_timed_out_flag(self):
        """When host doesn't respond, session.timed_out should be True."""
        session = Tn5250Session(host="test")
        session._stream = MagicMock()
        async def hang_forever():
            await asyncio.sleep(999)

        session._stream.read_frame = hang_forever
        session._keyboard_locked = True

        asyncio.get_event_loop().run_until_complete(
            session._process_until_unlocked(timeout=0.1)
        )

        assert session.timed_out is True
        assert session._keyboard_locked is False

    def test_no_timeout_clears_timed_out_flag(self):
        """When host responds normally, session.timed_out should be False."""
        session = Tn5250Session(host="test")
        session._stream = MagicMock()
        # GDS frame layout: [len_hi, len_lo, 0x12, 0xA0, rsvd, rsvd, var_hdr_len, flags, rsvd, opcode]
        invite_frame = (
            b"\x00\x0a"  # length = 10
            b"\x12\xa0"  # record type
            b"\x00\x00"  # reserved
            b"\x04"      # var_hdr_len (minimum)
            b"\x00"      # flags
            b"\x00"      # reserved
            b"\x01"      # opcode: OP_INVITE
        )
        session._stream.read_frame = AsyncMock(return_value=invite_frame)
        session._keyboard_locked = True

        asyncio.get_event_loop().run_until_complete(
            session._process_until_unlocked(timeout=1.0)
        )

        assert session.timed_out is False

    def test_send_aid_sets_timed_out_flag(self):
        """After send_aid times out, session.timed_out should be True."""
        session = Tn5250Session(host="test")
        session.response_timeout = 0.1
        session._stream = MagicMock()
        async def hang_forever():
            await asyncio.sleep(999)

        session._stream.read_frame = hang_forever
        session._stream.write_frame = AsyncMock()
        session._keyboard_locked = False

        asyncio.get_event_loop().run_until_complete(
            session.send_aid("enter")
        )

        assert session.timed_out is True

    def test_screen_response_includes_warning_on_timeout(self):
        """_screen_response() injects a warning when session.timed_out is True."""
        import ibmi_mcp.server as server_mod

        session = Tn5250Session(host="test")
        session._timed_out = True
        server_mod._session = session

        data = _screen_response()
        assert "warning" in data
        assert "timeout" in data["warning"].lower()

        server_mod._session = None

    def test_screen_response_no_warning_when_no_timeout(self):
        """_screen_response() has no warning field when no timeout occurred."""
        import ibmi_mcp.server as server_mod

        session = Tn5250Session(host="test")
        session._timed_out = False
        server_mod._session = session

        data = _screen_response()
        assert "warning" not in data

        server_mod._session = None
