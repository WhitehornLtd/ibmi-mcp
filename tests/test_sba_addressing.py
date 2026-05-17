"""Tests proving that SBA addresses are 1-based in the 5250 protocol.

Row 1, col 1 = top-left corner of the screen.
Row 24, col 80 = bottom-right corner of a 24x80 screen.

Internally, the screen buffer is 0-based: row 0, col 0 = first position.
The conversion is: buffer_pos = (sba_row - 1) * cols + (sba_col - 1)
"""

import pytest

from ibmi_mcp.tn5250.commands import build_response, parse_write_to_display
from ibmi_mcp.tn5250.constants import (
    AID_ENTER,
    ORDER_EA,
    ORDER_IC,
    ORDER_RA,
    ORDER_SBA,
    ORDER_SF,
)
from ibmi_mcp.tn5250.ebcdic import to_ebcdic
from ibmi_mcp.tn5250.field import ScreenField
from ibmi_mcp.tn5250.screen import ScreenBuffer


def make_wtd_data(*orders: bytes) -> bytes:
    """Build minimal WTD data: CC1 + CC2 + orders."""
    return b"\x00\x00" + b"".join(orders)


def sba(row: int, col: int) -> bytes:
    return bytes([ORDER_SBA, row, col])


class TestSBAAddressingBasics:
    """SBA row/col are 1-based: SBA(1,1) = top-left, SBA(24,80) = bottom-right."""

    def test_sba_1_1_writes_to_top_left(self):
        """SBA(1,1) followed by a character should write to buffer[0] (row 0, col 0)."""
        data = make_wtd_data(sba(1, 1), bytes([0xC1]))  # EBCDIC 'A'
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        assert screen.buffer[0] == "A"

    def test_first_text_row_not_blank(self):
        """Writing at SBA(1,1) should appear on get_text_rows()[0], not leave it blank."""
        data = make_wtd_data(sba(1, 1), bytes([0xC1]))  # EBCDIC 'A'
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        rows = screen.get_text_rows()
        assert rows[0][0] == "A"

    def test_sba_24_80_writes_to_last_position(self):
        """SBA(24,80) should write to the very last screen position (row 23, col 79)."""
        data = make_wtd_data(sba(24, 80), bytes([0xC1]))  # EBCDIC 'A'
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        assert screen.buffer[23 * 80 + 79] == "A"

    def test_sba_24_1_writes_to_last_row(self):
        """SBA(24,1) should write to the start of the last row (row 23 in 0-based)."""
        data = make_wtd_data(sba(24, 1), bytes([0xC1]))
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        rows = screen.get_text_rows()
        assert rows[23][0] == "A"

    def test_sba_1_80_writes_to_end_of_first_row(self):
        """SBA(1,80) should write to position 79 (last col of first row)."""
        data = make_wtd_data(sba(1, 80), bytes([0xC1]))
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        assert screen.buffer[79] == "A"

    def test_multiple_sba_different_rows(self):
        """Characters placed via SBA on rows 1, 12, and 24 go to buffer rows 0, 11, 23."""
        data = make_wtd_data(
            sba(1, 1), bytes([0xC1]),    # 'A' at row 1 → buffer row 0
            sba(12, 1), bytes([0xC2]),   # 'B' at row 12 → buffer row 11
            sba(24, 1), bytes([0xC3]),   # 'C' at row 24 → buffer row 23
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        assert screen.buffer[0 * 80] == "A"
        assert screen.buffer[11 * 80] == "B"
        assert screen.buffer[23 * 80] == "C"


class TestICCursorPosition:
    """IC (Insert Cursor) should reflect the 1-based SBA address, stored 0-based."""

    def test_ic_after_sba_sets_cursor_0based(self):
        """IC after SBA(5, 25) → cursor at row 4, col 24 (0-based internally)."""
        data = make_wtd_data(sba(5, 25), bytes([ORDER_IC]))
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        assert screen.cursor_row == 4
        assert screen.cursor_col == 24

    def test_ic_cursor_displayed_1based(self):
        """get_screen_data cursor should be 1-based: SBA(5,25)+IC → cursor (5,25)."""
        data = make_wtd_data(sba(5, 25), bytes([ORDER_IC]))
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        sd = screen.get_screen_data()
        assert sd["cursor"]["row"] == 5
        assert sd["cursor"]["col"] == 25

    def test_ic_at_row1_col1(self):
        """IC after SBA(1,1) → cursor at (0, 0) internally, (1, 1) displayed."""
        data = make_wtd_data(sba(1, 1), bytes([ORDER_IC]))
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        assert screen.cursor_row == 0
        assert screen.cursor_col == 0
        sd = screen.get_screen_data()
        assert sd["cursor"]["row"] == 1
        assert sd["cursor"]["col"] == 1


class TestSFFieldPositionWith1BasedSBA:
    """SF fields should reflect 1-based SBA positioning."""

    def test_field_position_internal_0based(self):
        """SF after SBA(5,24): attr at (4,23), field starts at (4,24) 0-based."""
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        field = screen.fields[0]
        assert field.row == 4
        assert field.col == 24

    def test_field_position_displayed_1based(self):
        """get_screen_data should show the field at (5, 25) — 1-based."""
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        sd = screen.get_screen_data()
        assert sd["fields"][0]["row"] == 5
        assert sd["fields"][0]["col"] == 25

    def test_sign_on_screen_fields_match_emulator(self):
        """Username at (5,25) and password at (6,25) in 1-based display coords.

        This matches a real TN5250 emulator showing cursor at 05/025
        on the username field of a PUB400.COM sign-on screen.
        """
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),  # username
            sba(6, 24),
            bytes([ORDER_SF, 0x40, 0x00, 0x27, 0x00, 0x80]),  # password
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        sd = screen.get_screen_data()
        assert len(sd["fields"]) == 2
        assert sd["fields"][0]["row"] == 5
        assert sd["fields"][0]["col"] == 25
        assert sd["fields"][1]["row"] == 6
        assert sd["fields"][1]["col"] == 25


class TestRAandEAAddressing:
    """RA and EA target addresses are also 1-based."""

    def test_ra_fills_correct_range(self):
        """RA from SBA(1,1) to target (1,11) fills positions 0-9 (10 chars)."""
        data = make_wtd_data(
            sba(1, 1),
            bytes([ORDER_RA, 1, 11, 0x5A]),  # fill with '!' (EBCDIC 0x5A)
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        for i in range(10):
            assert screen.buffer[i] == "!", f"buffer[{i}] should be '!' but is '{screen.buffer[i]}'"
        assert screen.buffer[10] == " "  # position 10 not filled

    def test_ra_across_row_boundary(self):
        """RA from SBA(1,79) to (2,2) fills last 2 cols of row 1 + first col of row 2."""
        data = make_wtd_data(
            sba(1, 79),
            bytes([ORDER_RA, 2, 2, 0x5A]),  # fill with '!'
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        # SBA(1,79) → position 78; target (2,2) → position 81
        # Fills: 78, 79, 80 (3 positions)
        assert screen.buffer[78] == "!"
        assert screen.buffer[79] == "!"
        assert screen.buffer[80] == "!"
        assert screen.buffer[81] == " "

    def test_ea_erases_correct_range(self):
        """EA from SBA(1,1) to target (1,6) erases positions 0-4."""
        # Pre-fill with 'X'
        screen = ScreenBuffer()
        for i in range(10):
            screen.set_char(i, "X")

        data = make_wtd_data(
            sba(1, 1),
            bytes([ORDER_EA, 1, 6]),
        )
        parse_write_to_display(data, screen)
        for i in range(5):
            assert screen.buffer[i] == " ", f"buffer[{i}] should be erased"
        assert screen.buffer[5] == "X"  # position 5 not erased


class TestBuildResponseCoordinates:
    """build_response must send 1-based coordinates back to the host."""

    def test_cursor_position_1based_in_response(self):
        """Cursor at internal (4, 24) should appear as (5, 25) in the response."""
        screen = ScreenBuffer()
        screen.set_cursor(4, 24)  # 0-based
        resp = build_response(screen, AID_ENTER)
        assert resp[0] == 5   # row: 0-based 4 → 1-based 5
        assert resp[1] == 25  # col: 0-based 24 → 1-based 25
        assert resp[2] == AID_ENTER

    def test_field_sba_1based_in_response(self):
        """Field at internal (4, 24) should be sent as SBA(5, 25) in the response."""
        screen = ScreenBuffer()
        screen.set_cursor(0, 0)
        field = ScreenField(row=4, col=24, length=10, ffw1=0x40, attr=0x24)
        screen.add_field(field)
        screen.set_char(4 * 80 + 24, "T")
        field.set_modified()

        resp = build_response(screen, AID_ENTER)
        assert resp[3] == ORDER_SBA
        assert resp[4] == 5   # row: 0-based 4 → 1-based 5
        assert resp[5] == 25  # col: 0-based 24 → 1-based 25

    def test_response_no_modified_fields_has_correct_cursor(self):
        """Even with no modified fields, cursor coords should be 1-based."""
        screen = ScreenBuffer()
        screen.set_cursor(0, 0)
        resp = build_response(screen, AID_ENTER)
        assert resp[0] == 1  # row 0 → 1
        assert resp[1] == 1  # col 0 → 1
        assert resp[2] == AID_ENTER


class TestEndToEndAddressing:
    """Integration-style tests combining SBA, SF, IC, typing, and response."""

    def test_type_and_respond_roundtrip(self):
        """Parse a field via SBA+SF, type into it, verify response has correct coords."""
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),
            sba(5, 25),  # position cursor at start of field
            bytes([ORDER_IC]),
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        # Cursor should be on the field
        assert screen.cursor_row == 4
        assert screen.cursor_col == 24

        # Type "TEST" at cursor
        cursor_pos = screen.cursor_pos()
        for i, ch in enumerate("TEST"):
            screen.set_char(cursor_pos + i, ch)
        screen.fields[0].set_modified()
        screen.set_cursor(4, 28)  # cursor moved after typing

        # Build response
        resp = build_response(screen, AID_ENTER)
        # Cursor in response: (4,28) 0-based → (5,29) 1-based
        assert resp[0] == 5
        assert resp[1] == 29
        assert resp[2] == AID_ENTER
        # Field SBA: (4,24) 0-based → (5,25) 1-based
        assert resp[3] == ORDER_SBA
        assert resp[4] == 5
        assert resp[5] == 25
        # EBCDIC data
        assert resp[6:] == to_ebcdic("TEST", "cp037")
