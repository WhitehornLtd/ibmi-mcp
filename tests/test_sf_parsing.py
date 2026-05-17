"""Tests for Start Field (SF) order parsing in parse_write_to_display."""

import pytest

from ibmi_mcp.tn5250.commands import build_response, parse_write_to_display
from ibmi_mcp.tn5250.constants import AID_ENTER, ORDER_SBA, ORDER_SF
from ibmi_mcp.tn5250.screen import ScreenBuffer


def make_wtd_data(*orders: bytes) -> bytes:
    """Build minimal WTD data: CC1 + CC2 + orders."""
    return b"\x00\x00" + b"".join(orders)


def sba(row: int, col: int) -> bytes:
    return bytes([ORDER_SBA, row, col])


class TestSFParsingWithFFW:
    """Test SF order parsing when FFW is present (first byte & 0xE0 != 0x20)."""

    def test_basic_input_field(self):
        """SF with FFW1=0x40 (input, alpha shift), FFW2=0x20 (monocase), attr=0x24, len=10."""
        # This matches the actual username field from an IBM i sign-on screen
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        assert len(screen.fields) == 1
        field = screen.fields[0]
        assert field.row == 4   # SBA row 5 → 0-based row 4
        assert field.col == 24  # SBA col 24 → attr at col 23, field starts at col 24
        assert field.length == 10
        assert field.ffw1 == 0x40
        assert field.ffw2 == 0x20
        assert field.attr == 0x24
        assert field.is_input is True
        assert field.is_bypass is False

    def test_non_display_input_field(self):
        """SF with FFW1=0x40 (input), FFW2=0x00, attr=0x27 (non-display), len=128."""
        # This matches the actual password field from an IBM i sign-on screen
        data = make_wtd_data(
            sba(6, 24),
            bytes([ORDER_SF, 0x40, 0x00, 0x27, 0x00, 0x80]),
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        assert len(screen.fields) == 1
        field = screen.fields[0]
        assert field.row == 5
        assert field.col == 24
        assert field.length == 128
        assert field.ffw1 == 0x40
        assert field.ffw2 == 0x00
        assert field.attr == 0x27
        assert field.is_input is True
        assert field.is_bypass is False

    def test_bypass_field(self):
        """SF with FFW1=0x60 (bypass bit 0x20 set + identifier 0x40), attr=0x20."""
        data = make_wtd_data(
            sba(3, 1),
            bytes([ORDER_SF, 0x60, 0x00, 0x20, 0x00, 0x50]),
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        assert len(screen.fields) == 1
        field = screen.fields[0]
        assert field.ffw1 == 0x60
        assert field.is_bypass is True
        assert field.is_input is False
        assert field.length == 80

    def test_two_fields_sign_on_screen(self):
        """Parse both username and password fields from a sign-on screen."""
        # Actual bytes from a real IBM i sign-on screen WTD
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),  # username: len=10
            sba(6, 24),
            bytes([ORDER_SF, 0x40, 0x00, 0x27, 0x00, 0x80]),  # password: len=128
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        assert len(screen.fields) == 2

        username_field = screen.fields[0]
        assert username_field.row == 4
        assert username_field.col == 24
        assert username_field.length == 10
        assert username_field.is_input is True

        password_field = screen.fields[1]
        assert password_field.row == 5
        assert password_field.col == 24
        assert password_field.length == 128
        assert password_field.is_input is True

    def test_field_with_fcw(self):
        """SF with FFW + one FCW pair before the attribute."""
        # FFW1=0x40, FFW2=0x00, FCW1=0x80, FCW2=0x01, attr=0x20, len=20
        data = make_wtd_data(
            sba(2, 10),
            bytes([ORDER_SF, 0x40, 0x00, 0x80, 0x01, 0x20, 0x00, 0x14]),
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        assert len(screen.fields) == 1
        field = screen.fields[0]
        assert field.ffw1 == 0x40
        assert field.ffw2 == 0x00
        assert field.fcw1 == 0x80
        assert field.fcw2 == 0x01
        assert field.attr == 0x20
        assert field.length == 20
        assert field.is_input is True


class TestSFParsingWithoutFFW:
    """Test SF order parsing when no FFW is present (first byte & 0xE0 == 0x20)."""

    def test_output_only_field(self):
        """SF with no FFW — first byte is attribute 0x20, field is output-only."""
        data = make_wtd_data(
            sba(1, 1),
            bytes([ORDER_SF, 0x20, 0x00, 0x28]),  # attr=0x20, len=40
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)

        assert len(screen.fields) == 1
        field = screen.fields[0]
        assert field.ffw1 == 0
        assert field.attr == 0x20
        assert field.length == 40
        assert field.is_bypass is True
        assert field.is_input is False

    def test_output_field_various_attrs(self):
        """SF without FFW using different attribute values in 0x20-0x3F range."""
        for attr_val in [0x20, 0x27, 0x30, 0x3F]:
            data = make_wtd_data(
                sba(1, 1),
                bytes([ORDER_SF, attr_val, 0x00, 0x0A]),
            )
            screen = ScreenBuffer()
            parse_write_to_display(data, screen)
            assert screen.fields[0].is_bypass is True
            assert screen.fields[0].attr == attr_val


class TestBuildResponse:
    """Test that build_response produces correct response bytes."""

    def test_empty_response_no_modified_fields(self):
        """No fields modified — response is just cursor (1-based) + AID."""
        screen = ScreenBuffer()
        screen.set_cursor(3, 10)
        resp = build_response(screen, AID_ENTER)
        assert resp == bytes([4, 11, AID_ENTER])  # 0-based (3,10) → 1-based (4,11)

    def test_response_with_modified_field(self):
        """Modified field included in response with SBA + field data."""
        screen = ScreenBuffer()
        screen.set_cursor(0, 0)

        from ibmi_mcp.tn5250.field import ScreenField

        field = ScreenField(row=4, col=24, length=10, ffw1=0x40, attr=0x24)
        screen.add_field(field)

        # Simulate typing "TEST" into the field
        for i, ch in enumerate("TEST"):
            screen.set_char(4 * 80 + 24 + i, ch)
        field.set_modified()

        resp = build_response(screen, AID_ENTER)

        # Cursor and field coords are 1-based in the response
        assert resp[0] == 1  # cursor row: 0-based 0 → 1-based 1
        assert resp[1] == 1  # cursor col: 0-based 0 → 1-based 1
        assert resp[2] == AID_ENTER
        assert resp[3] == ORDER_SBA
        assert resp[4] == 5  # field row: 0-based 4 → 1-based 5
        assert resp[5] == 25  # field col: 0-based 24 → 1-based 25
        # "TEST" in EBCDIC cp037
        from ibmi_mcp.tn5250.ebcdic import to_ebcdic

        assert resp[6:] == to_ebcdic("TEST", "cp037")

    def test_response_strips_trailing_blanks(self):
        """Field data has trailing blanks stripped."""
        screen = ScreenBuffer()
        screen.set_cursor(0, 0)

        from ibmi_mcp.tn5250.field import ScreenField

        field = ScreenField(row=2, col=5, length=20, ffw1=0x40, attr=0x20)
        screen.add_field(field)

        # Write "HI" followed by spaces (default buffer is spaces)
        screen.set_char(2 * 80 + 5, "H")
        screen.set_char(2 * 80 + 6, "I")
        field.set_modified()

        resp = build_response(screen, AID_ENTER)

        from ibmi_mcp.tn5250.ebcdic import to_ebcdic

        # SBA coords are 1-based: row 2→3, col 5→6
        assert resp[3] == ORDER_SBA
        assert resp[4] == 3
        assert resp[5] == 6
        expected_data = to_ebcdic("HI", "cp037")
        assert resp[6:] == expected_data  # Only "HI", no trailing spaces

    def test_response_skips_unmodified_fields(self):
        """Fields without MDT bit are not included."""
        screen = ScreenBuffer()
        screen.set_cursor(0, 0)

        from ibmi_mcp.tn5250.field import ScreenField

        field = ScreenField(row=1, col=0, length=10, ffw1=0x40, attr=0x20)
        screen.add_field(field)
        # Don't call set_modified — MDT bit not set

        resp = build_response(screen, AID_ENTER)
        assert resp == bytes([1, 1, AID_ENTER])  # 0-based (0,0) → 1-based (1,1)


class TestTabNavigation:
    """Test that Tab moves cursor between input fields correctly."""

    def test_tab_moves_to_first_input_field(self):
        """Tab from position 0 goes to the first input field."""
        screen = ScreenBuffer()
        screen.set_cursor(0, 0)

        from ibmi_mcp.tn5250.field import ScreenField

        # Output-only field (no FFW)
        screen.add_field(ScreenField(row=1, col=5, length=20, ffw1=0, attr=0x20))
        # Input field
        screen.add_field(ScreenField(row=3, col=10, length=10, ffw1=0x40, attr=0x24))

        fields = screen.get_input_fields()
        assert len(fields) == 1
        assert fields[0].row == 3
        assert fields[0].col == 10

    def test_tab_skips_bypass_fields(self):
        """Tab skips fields with bypass bit set (FFW1 & 0x20)."""
        screen = ScreenBuffer()

        from ibmi_mcp.tn5250.field import ScreenField

        # Bypass field (FFW1 has bit 6 identifier + bit 5 bypass)
        screen.add_field(ScreenField(row=1, col=0, length=10, ffw1=0x60, attr=0x20))
        # Input field
        screen.add_field(ScreenField(row=2, col=0, length=10, ffw1=0x40, attr=0x20))

        fields = screen.get_input_fields()
        assert len(fields) == 1
        assert fields[0].row == 2

    def test_two_input_fields_both_reachable(self):
        """Both username and password fields are reachable by tab."""
        screen = ScreenBuffer()

        from ibmi_mcp.tn5250.field import ScreenField

        screen.add_field(ScreenField(row=4, col=24, length=10, ffw1=0x40, attr=0x24))
        screen.add_field(ScreenField(row=5, col=24, length=128, ffw1=0x40, attr=0x27))

        fields = screen.get_input_fields()
        assert len(fields) == 2
        assert fields[0].row == 4
        assert fields[1].row == 5
