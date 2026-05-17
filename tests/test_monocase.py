"""Tests for monocase field handling — FFW2 bit 0x20 should auto-uppercase input."""

import asyncio

import pytest

from ibmi_mcp.tn5250.commands import parse_write_to_display
from ibmi_mcp.tn5250.constants import ORDER_SBA, ORDER_SF
from ibmi_mcp.tn5250.field import ScreenField
from ibmi_mcp.tn5250.screen import ScreenBuffer
from ibmi_mcp.tn5250.session import Tn5250Session


def make_wtd_data(*orders: bytes) -> bytes:
    return b"\x00\x00" + b"".join(orders)


def sba(row: int, col: int) -> bytes:
    return bytes([ORDER_SBA, row, col])


class TestMonocaseField:
    """Test that typing into a monocase field uppercases input."""

    def _make_screen_with_monocase_field(self) -> ScreenBuffer:
        """Create a screen with a monocase input field at row 4, col 24, length 10."""
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),  # FFW2=0x20 → monocase
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        return screen

    def _make_screen_with_normal_field(self) -> ScreenBuffer:
        """Create a screen with a normal (non-monocase) input field."""
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x0A]),  # FFW2=0x00 → no monocase
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        return screen

    def test_monocase_field_detected(self):
        """Field with FFW2 bit 0x20 is identified as monocase."""
        screen = self._make_screen_with_monocase_field()
        field = screen.fields[0]
        assert field.ffw2 & 0x20  # monocase bit set

    def test_normal_field_not_monocase(self):
        """Field without FFW2 bit 0x20 is not monocase."""
        screen = self._make_screen_with_normal_field()
        field = screen.fields[0]
        assert not (field.ffw2 & 0x20)

    def test_type_keys_uppercases_in_monocase_field(self):
        """Typing lowercase into a monocase field produces uppercase on screen."""
        session = Tn5250Session(host="test")
        session._screen = self._make_screen_with_monocase_field()
        # Position cursor on the field
        session._screen.set_cursor(4, 24)

        asyncio.get_event_loop().run_until_complete(session.type_keys("hello"))

        value = session._screen.get_field_value(session._screen.fields[0])
        assert value.rstrip() == "HELLO"

    def test_type_keys_preserves_case_in_normal_field(self):
        """Typing lowercase into a non-monocase field preserves case."""
        session = Tn5250Session(host="test")
        session._screen = self._make_screen_with_normal_field()
        session._screen.set_cursor(4, 24)

        asyncio.get_event_loop().run_until_complete(session.type_keys("Hello"))

        value = session._screen.get_field_value(session._screen.fields[0])
        assert value.rstrip() == "Hello"

    def test_type_keys_uppercase_unaffected_by_monocase(self):
        """Already-uppercase text in monocase field stays uppercase."""
        session = Tn5250Session(host="test")
        session._screen = self._make_screen_with_monocase_field()
        session._screen.set_cursor(4, 24)

        asyncio.get_event_loop().run_until_complete(session.type_keys("WORLD"))

        value = session._screen.get_field_value(session._screen.fields[0])
        assert value.rstrip() == "WORLD"

    def test_type_keys_mixed_content_monocase(self):
        """Numbers and special chars pass through, only letters uppercased."""
        session = Tn5250Session(host="test")
        session._screen = self._make_screen_with_monocase_field()
        session._screen.set_cursor(4, 24)

        asyncio.get_event_loop().run_until_complete(session.type_keys("ab1@z"))

        value = session._screen.get_field_value(session._screen.fields[0])
        assert value.rstrip() == "AB1@Z"


class TestMonocaseWithTwoFields:
    """Test monocase behavior with username (monocase) + password (normal) fields."""

    def _make_sign_on_screen(self) -> ScreenBuffer:
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),  # username: monocase
            sba(6, 24),
            bytes([ORDER_SF, 0x40, 0x00, 0x27, 0x00, 0x80]),  # password: normal
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        return screen

    def test_username_uppercased_password_preserved(self):
        """Username field uppercases, password field preserves case."""
        session = Tn5250Session(host="test")
        session._screen = self._make_sign_on_screen()

        # Type in username field (monocase)
        session._screen.set_cursor(4, 24)
        asyncio.get_event_loop().run_until_complete(session.type_keys("testuser"))

        # Type in password field (normal)
        session._screen.set_cursor(5, 24)
        asyncio.get_event_loop().run_until_complete(session.type_keys("testpassword123"))

        username = session._screen.get_field_value(session._screen.fields[0]).rstrip()
        password = session._screen.get_field_value(session._screen.fields[1]).rstrip()

        assert username == "TESTUSER"
        assert password == "testpassword123"
