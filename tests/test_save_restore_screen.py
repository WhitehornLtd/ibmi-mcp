"""Tests for the 5250 Save Screen / Restore Screen operations.

RFC 1205 section 4.3:

    Save operation
        Server: Sends Save (Immediate) command with Opcode = Save Screen.
        Client: Sends the screen image to be saved.

    Restore operation
        Server: Sends the saved screen to be restored, Opcode = Restore Screen.
        (No reply is necessary from the client)

and gives the client's reply the form ``LLLL12A0 00000400 00040412 <Screen
Image> FFEF`` — a GDS frame whose opcode is Save Screen and whose data begins
with ESC + the Restore Screen command, so the host can hand the image straight
back later.

Leaving Save Screen unanswered desynchronizes the session by one exchange: the
host waits for the image while the client waits for a frame. That is what makes
the screen appear to lag one keystroke, and what leaves later frames parsed
against the wrong expectation.

The hex fixtures are real frames captured from NEXUS (IBM i V7R6M0) on
2026-07-30 while running RPGC/CAKEYP, whose display file carries a
VALUES(10 20 30) validity-checking keyword.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from ibmi_mcp.tn5250.constants import CMD_RESTORE_SCREEN, ESC, OP_PUT_GET
from ibmi_mcp.tn5250.session import Tn5250Session

# NEXUS, running CALL RPGC/CAKEYP: the WTD that paints the validity-checked
# screen — "Numeric:" label, a signed-numeric input field, and the key legend.
CAKEYP_SCREEN_FRAME = bytes.fromhex(
    "005412a00000040000030440041100280107000000180000"
    "0411040120d5a494859989837a201105011d47002400060000"
    "0000000011080120c6f37ec3c14085a789a34040c6f57ec3c6"
    "40a385a2a32004520000"
)

# NEXUS, immediately after an AID key: the host asks for the screen to be saved.
# Body is ESC + Save Screen; opcode in the GDS header is Save Screen (0x04).
SAVE_SCREEN_FRAME = bytes.fromhex("000c12a00000040000040402")


def make_session() -> Tn5250Session:
    session = Tn5250Session("testhost")
    session._stream = AsyncMock()
    return session


def gds_frame(opcode: int, body: bytes) -> bytes:
    total = 10 + len(body)
    header = bytearray(10)
    header[0] = (total >> 8) & 0xFF
    header[1] = total & 0xFF
    header[2] = 0x12
    header[3] = 0xA0
    header[6] = 0x04
    header[9] = opcode
    return bytes(header) + body


class TestSaveScreenIsAnswered:
    """The host blocks until the client returns the image."""

    def test_save_screen_frame_is_recognized(self):
        session = make_session()
        session._process_gds_frame(CAKEYP_SCREEN_FRAME)
        session._process_gds_frame(SAVE_SCREEN_FRAME)

        assert session._pending_save_screen is True, (
            "a Save Screen frame must be recognized as needing a reply"
        )

    def test_reply_is_a_save_screen_frame_carrying_a_restore_command(self):
        """RFC 1205: the reply is '...0400 0004 0412 <Screen Image>'."""
        session = make_session()
        session._process_gds_frame(CAKEYP_SCREEN_FRAME)

        data = session._build_save_screen_data()

        assert data[0] == ESC
        assert data[1] == CMD_RESTORE_SCREEN, (
            "the saved image is prefixed with ESC + Restore Screen so the host "
            "can replay it verbatim"
        )

    def test_the_saved_image_reproduces_the_screen(self):
        """Round trip: save the image, lose the screen, restore it."""
        session = make_session()
        session._process_gds_frame(CAKEYP_SCREEN_FRAME)
        before = session.screen.get_text_rows()
        fields_before = len(session.screen.fields)
        assert "Numeric:" in before[3], "precondition: the screen rendered"

        saved = session._build_save_screen_data()

        session.screen.clear()
        assert "Numeric:" not in session.screen.get_text_rows()[3]

        session._process_gds_frame(gds_frame(0x05, saved))

        assert session.screen.get_text_rows() == before
        assert len(session.screen.fields) == fields_before

    @pytest.mark.asyncio
    async def test_the_reply_is_actually_sent_and_the_session_continues(self):
        """The stall this ticket is about: no reply, no progress."""
        session = make_session()
        session._process_gds_frame(CAKEYP_SCREEN_FRAME)

        frames = [SAVE_SCREEN_FRAME, gds_frame(OP_PUT_GET, b"\x04\x11\x00\x00")]
        session._stream.read_frame = AsyncMock(side_effect=frames)
        session._keyboard_locked = True

        await asyncio.wait_for(session._process_until_unlocked(timeout=2.0), timeout=5.0)

        assert not session.timed_out, (
            "an unanswered Save Screen makes the host and client wait on each other"
        )
        written = [call.args[0] for call in session._stream.write_frame.call_args_list]
        assert written, "the client must send the screen image back"
        assert written[0][9] == 0x04, "the reply frame's opcode is Save Screen"


class TestRestoreScreen:
    """A restored image repaints the screen; no reply is required."""

    def test_restore_screen_repaints_without_replying(self):
        session = make_session()
        session._process_gds_frame(CAKEYP_SCREEN_FRAME)
        saved = session._build_save_screen_data()
        session.screen.clear()

        session._process_gds_frame(gds_frame(0x05, saved))

        assert "Numeric:" in session.screen.get_text_rows()[3]
        session._stream.write_frame.assert_not_called()

    def test_a_restore_command_inside_a_normal_frame_is_parsed(self):
        """ESC + Restore Screen introduces an image; parsing must continue."""
        session = make_session()
        session._process_gds_frame(CAKEYP_SCREEN_FRAME)
        saved = session._build_save_screen_data()
        session.screen.clear()

        session._process_gds_frame(gds_frame(OP_PUT_GET, saved))

        assert "Numeric:" in session.screen.get_text_rows()[3]


class TestValidityCheckedScreenRenders:
    """Acceptance: a VALUES(...) display file renders through the full cycle."""

    def test_the_validity_checked_screen_is_not_garbled(self):
        session = make_session()
        session._process_gds_frame(CAKEYP_SCREEN_FRAME)
        rows = session.screen.get_text_rows()

        assert "Numeric:" in rows[3]
        assert "F3=CA exit" in rows[7]
        joined = "".join(rows)
        assert joined.count("a") < 50, (
            "the reported failure filled all 24 rows with the letter 'a'"
        )

    def test_the_input_field_keeps_its_signed_numeric_shift(self):
        session = make_session()
        session._process_gds_frame(CAKEYP_SCREEN_FRAME)

        fields = session.screen.get_input_fields()
        assert len(fields) == 1
        assert fields[0].field_type == "signed_numeric"
        assert fields[0].length == 6
