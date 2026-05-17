"""Tests for 5250 Query command detection and Query Reply building."""

from ibmi_mcp.tn5250.constants import (
    CMD_WRITE_STRUCTURED_FIELD,
    CMD_WRITE_TO_DISPLAY,
    ESC,
    OP_PUT_GET,
)
from ibmi_mcp.tn5250.session import Tn5250Session


class TestQueryDetection:
    """Detect 5250 Query (0xD9) in Write Structured Field commands."""

    def test_detects_query_in_structured_field(self):
        """CMD_WRITE_STRUCTURED_FIELD with class 0xD9 sets _pending_query."""
        session = Tn5250Session(host="test")
        # ESC + WSF + SF_LEN(5) + CLASS(D9) + TYPE(70) + DATA(00)
        data = bytes([ESC, CMD_WRITE_STRUCTURED_FIELD, 0x00, 0x05, 0xD9, 0x70, 0x00])
        session._parse_commands(data)
        assert session._pending_query is True

    def test_non_query_structured_field_no_flag(self):
        """CMD_WRITE_STRUCTURED_FIELD with a different class does NOT set _pending_query."""
        session = Tn5250Session(host="test")
        # ESC + WSF + SF_LEN(4) + CLASS(D1) + TYPE(00)
        data = bytes([ESC, CMD_WRITE_STRUCTURED_FIELD, 0x00, 0x04, 0xD1, 0x00])
        session._parse_commands(data)
        assert session._pending_query is False

    def test_wtd_does_not_set_query_flag(self):
        """Regular WTD commands do not set _pending_query."""
        session = Tn5250Session(host="test")
        # ESC + WTD + CC1 + CC2
        data = bytes([ESC, CMD_WRITE_TO_DISPLAY, 0x00, 0x00])
        session._parse_commands(data)
        assert session._pending_query is False

    def test_put_get_with_query_does_not_unlock(self):
        """PUT_GET containing a query should NOT unlock the keyboard."""
        session = Tn5250Session(host="test")
        session._keyboard_locked = True

        # Build a GDS frame with PUT_GET opcode containing a query
        sf_data = bytes([ESC, CMD_WRITE_STRUCTURED_FIELD, 0x00, 0x05, 0xD9, 0x70, 0x00])
        frame = bytearray(10 + len(sf_data))
        frame[0] = 0x00
        frame[1] = len(frame)
        frame[2] = 0x12
        frame[3] = 0xA0
        frame[6] = 0x04  # var_hdr_len
        frame[7] = 0x00  # flags
        frame[9] = OP_PUT_GET
        frame[10:] = sf_data

        session._process_gds_frame(bytes(frame))
        assert session._keyboard_locked is True  # Should NOT have unlocked
        assert session._pending_query is True

    def test_put_get_without_query_unlocks(self):
        """PUT_GET with a regular WTD should unlock as normal."""
        session = Tn5250Session(host="test")
        session._keyboard_locked = True

        wtd_data = bytes([ESC, CMD_WRITE_TO_DISPLAY, 0x00, 0x00])
        frame = bytearray(10 + len(wtd_data))
        frame[0] = 0x00
        frame[1] = len(frame)
        frame[2] = 0x12
        frame[3] = 0xA0
        frame[6] = 0x04
        frame[7] = 0x00
        frame[9] = OP_PUT_GET
        frame[10:] = wtd_data

        session._process_gds_frame(bytes(frame))
        assert session._keyboard_locked is False


class TestQueryReply:
    """Test the query reply byte format."""

    def test_query_reply_starts_with_cursor_and_aid(self):
        """Reply starts with 1-based cursor position and AID 0x88."""
        session = Tn5250Session(host="test")
        session._screen.set_cursor(4, 24)  # 0-based
        reply = session._build_query_reply()
        assert reply[0] == 5   # cursor row: 0-based 4 → 1-based 5
        assert reply[1] == 25  # cursor col: 0-based 24 → 1-based 25
        assert reply[2] == 0x88  # Structured Field AID

    def test_query_reply_sf_header(self):
        """SF data starts with length (58), type 0xD9, class 0x70."""
        session = Tn5250Session(host="test")
        reply = session._build_query_reply()
        # SF data starts at byte 3
        assert reply[3] == 0x00  # length high
        assert reply[4] == 0x3A  # length low (58)
        assert reply[5] == 0xD9  # SF type (Query Reply)
        assert reply[6] == 0x70  # SF class

    def test_query_reply_flags(self):
        """Flags indicate a display workstation."""
        session = Tn5250Session(host="test")
        reply = session._build_query_reply()
        assert reply[7] == 0x80  # display station flag
        assert reply[8] == 0x06  # standard flags

    def test_query_reply_total_length(self):
        """Total reply = 3 (cursor+AID) + 58 (SF data) = 61 bytes."""
        session = Tn5250Session(host="test")
        reply = session._build_query_reply()
        assert len(reply) == 61

    def test_query_reply_model_24x80(self):
        """Reply reports model as 24x80 display."""
        session = Tn5250Session(host="test")
        reply = session._build_query_reply()
        assert reply[14] == 0x01  # machine type: display
        assert reply[15] == 0x01  # model: 24x80
