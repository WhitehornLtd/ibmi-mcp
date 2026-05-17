"""Tests for IC (Insert Cursor) order placement after connect."""

import pytest

from ibmi_mcp.tn5250.commands import parse_clear, parse_write_to_display
from ibmi_mcp.tn5250.constants import ORDER_IC, ORDER_SBA, ORDER_SF
from ibmi_mcp.tn5250.screen import ScreenBuffer


def make_wtd_data(*orders: bytes) -> bytes:
    return b"\x00\x00" + b"".join(orders)


def sba(row: int, col: int) -> bytes:
    return bytes([ORDER_SBA, row, col])


class TestICCursorPlacement:
    """Test that IC order places cursor at the correct position."""

    def test_ic_places_cursor_at_current_addr(self):
        """IC order sets cursor to the current buffer address."""
        data = make_wtd_data(
            sba(5, 25),  # Move to row 5, col 25 (1-based)
            bytes([ORDER_IC]),  # Insert Cursor here
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        # IC should place cursor at the current_addr after SBA
        # SBA(5,25) → 0-based addr = (5-1)*80 + (25-1) = 344 → row=4, col=24
        assert screen.cursor_row == 4
        assert screen.cursor_col == 24

    def test_ic_after_sf_places_cursor_on_field(self):
        """IC after SF places cursor at the start of the input field."""
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),  # Field: attr at col 23, field starts col 24
            bytes([ORDER_IC]),  # Cursor goes here — right after the field starts
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        # After SF: attr byte at position (row4, col23), current_addr advances to (row4, col24)
        # Then field is created at (row4, col24), current_addr = field_start (row4, col24)
        # Wait — SF parsing: SBA(5,24) → addr=(4*80+23)=343. Then SF: attr placed at 343, addr becomes 344.
        # Field starts at addr 344 → row=4, col=24. IC is at addr 344.
        assert screen.cursor_row == 4
        assert screen.cursor_col == 24

    def test_ic_not_present_cursor_defaults_to_first_input_field(self):
        """Without IC order, cursor defaults to first input field per 5250 spec."""
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),
        )
        screen = ScreenBuffer()
        screen.set_cursor(0, 0)
        parse_write_to_display(data, screen)

        # No IC → cursor lands on first input field (row 4, col 24 in 0-based)
        assert screen.cursor_row == 4
        assert screen.cursor_col == 24

    def test_ic_with_preceding_text(self):
        """IC works correctly after text has been written to the screen."""
        data = make_wtd_data(
            sba(1, 1),
            # Some EBCDIC text (0xC8=H, 0xC5=E, 0xD3=L, 0xD3=L, 0xD6=O in cp037)
            bytes([0xC8, 0xC5, 0xD3, 0xD3, 0xD6]),
            sba(3, 10),
            bytes([ORDER_IC]),  # Cursor at row 3, col 10 (1-based) → (2, 9) 0-based
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        assert screen.cursor_row == 2
        assert screen.cursor_col == 9

    def test_ic_on_sign_on_screen(self):
        """Simulate a sign-on screen where IC is placed on the username field."""
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),  # username field
            bytes([ORDER_IC]),  # Cursor on username field
            sba(6, 24),
            bytes([ORDER_SF, 0x40, 0x00, 0x27, 0x00, 0x80]),  # password field
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        # IC after username SF: current_addr is at field start (row4, col24)
        assert screen.cursor_row == 4
        assert screen.cursor_col == 24

        # Verify field positions are correct too
        assert len(screen.fields) == 2
        assert screen.fields[0].row == 4
        assert screen.fields[0].col == 24

    def test_multiple_ic_last_one_wins(self):
        """If multiple IC orders appear, the last one determines cursor position."""
        data = make_wtd_data(
            sba(2, 5),
            bytes([ORDER_IC]),  # First IC
            sba(8, 15),
            bytes([ORDER_IC]),  # Second IC — this should win
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        assert screen.cursor_row == 7  # row 8, 1-based → 7, 0-based
        assert screen.cursor_col == 14  # col 15, 1-based → 14, 0-based

    def test_mc_order_also_moves_cursor(self):
        """MC (Move Cursor) order explicitly moves cursor (1-based coords)."""
        data = make_wtd_data(
            bytes([ORDER_SBA, 1, 1]),
            # MC order: move cursor to row 10, col 20 (1-based)
            bytes([0x14, 10, 20]),
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        assert screen.cursor_row == 9   # 10 - 1
        assert screen.cursor_col == 19  # 20 - 1


class TestDefaultCursorToFirstField:
    """Test that cursor defaults to first input field when no IC is present.

    Per the IBM 5494 Functions Reference: if no Insert Cursor order is in the
    data stream, the cursor is positioned at the first position of the first
    non-bypass input field.
    """

    def test_no_ic_cursor_defaults_to_first_input_field(self):
        """Screen with fields but no IC → cursor on first input field."""
        # Simulate the Main Menu: Clear + WTD with one command-line field, no IC
        screen = ScreenBuffer()
        parse_clear(screen)  # Clear resets cursor to (0,0)

        data = make_wtd_data(
            sba(20, 7),
            bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x99]),  # input field, len=153
        )
        parse_write_to_display(data, screen)

        # After processing, cursor should be on the field (row 19, col 7 in 0-based)
        # because no IC was sent and spec says default to first input field
        assert screen.cursor_row == 19
        assert screen.cursor_col == 7

    def test_no_ic_multiple_fields_cursor_on_first(self):
        """Screen with multiple input fields but no IC → cursor on first one."""
        # Simulate Customer Maintenance: 3 option fields, no IC
        screen = ScreenBuffer()
        parse_clear(screen)

        data = make_wtd_data(
            sba(4, 2),
            bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x01]),  # option field 1, len=1
            sba(5, 2),
            bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x01]),  # option field 2, len=1
            sba(6, 2),
            bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x01]),  # option field 3, len=1
        )
        parse_write_to_display(data, screen)

        # Cursor should land on first option field (row 3, col 2 in 0-based)
        assert screen.cursor_row == 3
        assert screen.cursor_col == 2

    def test_ic_present_overrides_default(self):
        """When IC IS present, cursor stays where IC put it (not first field)."""
        screen = ScreenBuffer()
        parse_clear(screen)

        data = make_wtd_data(
            sba(4, 2),
            bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x01]),  # field 1
            sba(5, 2),
            bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x01]),  # field 2
            sba(5, 2),
            bytes([ORDER_IC]),  # Explicit cursor on second field
        )
        parse_write_to_display(data, screen)

        # IC said row 5, col 2 (1-based) → (4, 1) 0-based
        assert screen.cursor_row == 4
        assert screen.cursor_col == 1

    def test_no_ic_no_input_fields_cursor_stays_at_origin(self):
        """Screen with only bypass fields and no IC → cursor stays at (0,0)."""
        screen = ScreenBuffer()
        parse_clear(screen)

        data = make_wtd_data(
            sba(3, 1),
            bytes([ORDER_SF, 0x60, 0x00, 0x20, 0x00, 0x50]),  # bypass field
        )
        parse_write_to_display(data, screen)

        # No input fields to land on, cursor stays at clear default
        assert screen.cursor_row == 0
        assert screen.cursor_col == 0

    def test_no_ic_with_clear_then_wtd(self):
        """Full sequence: clear resets cursor, WTD adds fields, cursor defaults to field."""
        screen = ScreenBuffer()
        # Start with cursor somewhere weird
        screen.set_cursor(15, 40)

        parse_clear(screen)  # Resets to (0,0)

        data = make_wtd_data(
            sba(10, 5),
            bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x14]),  # input field, len=20
        )
        parse_write_to_display(data, screen)

        # Should land on the field at (9, 5) 0-based
        assert screen.cursor_row == 9
        assert screen.cursor_col == 5
