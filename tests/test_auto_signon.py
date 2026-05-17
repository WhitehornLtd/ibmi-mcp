"""Tests for auto-signon functionality.

Requirements:
1. Only fires if not already signed in (session tracks state)
2. Only on the INITIAL screen after connect (never on subsequent screens)
3. Only if screen text contains "password" AND one of "username"/"user name"/"login"
4. Conservative: better to never fire than to misfire on a non-sign-on screen
"""

import asyncio
from unittest.mock import AsyncMock

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


def _put_text(screen: ScreenBuffer, row: int, col: int, text: str) -> None:
    """Write text onto the screen at a given 0-based position."""
    start = row * screen.cols + col
    for i, ch in enumerate(text):
        screen.set_char(start + i, ch)


def _make_sign_on_screen() -> ScreenBuffer:
    """PUB400-style sign-on: 2 input fields + 'user name' and 'Password' text."""
    data = make_wtd_data(
        sba(5, 24),
        bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),  # username: monocase, len=10
        sba(6, 24),
        bytes([ORDER_SF, 0x40, 0x00, 0x27, 0x00, 0x80]),  # password: non-display, len=128
    )
    screen = ScreenBuffer()
    parse_write_to_display(data, screen)
    _put_text(screen, 4, 0, "Your user name:")
    _put_text(screen, 5, 0, "Password (max. 128):")
    return screen


def _make_standard_signon_screen() -> ScreenBuffer:
    """Standard IBM i QDSIGNON with 5 fields + 'User' and 'Password' labels."""
    data = make_wtd_data(
        sba(6, 54),
        bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),  # User, len=10
        sba(7, 54),
        bytes([ORDER_SF, 0x40, 0x00, 0x27, 0x00, 0x0A]),  # Password, len=10
        sba(8, 54),
        bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x0A]),  # Program/procedure, len=10
        sba(9, 54),
        bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x0A]),  # Menu, len=10
        sba(10, 54),
        bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x0A]),  # Current library, len=10
    )
    screen = ScreenBuffer()
    parse_write_to_display(data, screen)
    _put_text(screen, 0, 30, "Sign On")
    _put_text(screen, 5, 16, "User  . . . . . . . . . . . .")
    _put_text(screen, 6, 16, "Password  . . . . . . . . . .")
    _put_text(screen, 7, 16, "Program/procedure . . . . . .")
    _put_text(screen, 8, 16, "Menu  . . . . . . . . . . . .")
    _put_text(screen, 9, 16, "Current library . . . . . . .")
    return screen


def _make_main_menu_screen() -> ScreenBuffer:
    """Main Menu with 1 command-line field, no sign-on keywords."""
    data = make_wtd_data(
        sba(20, 7),
        bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x99]),  # command line, len=153
    )
    screen = ScreenBuffer()
    parse_write_to_display(data, screen)
    _put_text(screen, 0, 1, "MAIN                           IBM i Main Menu")
    _put_text(screen, 18, 1, "Selection or command")
    _put_text(screen, 19, 1, "===>")
    return screen


def _make_two_field_data_entry_screen() -> ScreenBuffer:
    """A custom 2-field data entry screen that is NOT a sign-on screen."""
    data = make_wtd_data(
        sba(5, 20),
        bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x14]),  # "Customer Name", len=20
        sba(7, 20),
        bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x0A]),  # "Phone Number", len=10
    )
    screen = ScreenBuffer()
    parse_write_to_display(data, screen)
    _put_text(screen, 0, 25, "Customer Entry")
    _put_text(screen, 4, 2, "Customer Name:")
    _put_text(screen, 6, 2, "Phone Number:")
    return screen


def _make_login_screen() -> ScreenBuffer:
    """Alternative sign-on screen using 'Login' instead of 'User name'."""
    data = make_wtd_data(
        sba(5, 24),
        bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),  # login field
        sba(6, 24),
        bytes([ORDER_SF, 0x40, 0x00, 0x27, 0x00, 0x80]),  # password field
    )
    screen = ScreenBuffer()
    parse_write_to_display(data, screen)
    _put_text(screen, 4, 0, "Login:")
    _put_text(screen, 5, 0, "Password:")
    return screen


def _make_username_screen() -> ScreenBuffer:
    """Sign-on screen using 'Username' (one word)."""
    data = make_wtd_data(
        sba(5, 24),
        bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),
        sba(6, 24),
        bytes([ORDER_SF, 0x40, 0x00, 0x27, 0x00, 0x80]),
    )
    screen = ScreenBuffer()
    parse_write_to_display(data, screen)
    _put_text(screen, 4, 0, "Username:")
    _put_text(screen, 5, 0, "Password:")
    return screen


class TestSignOnDetection:
    """Test _is_sign_on_screen: must require keywords AND credentials AND not already signed in."""

    def test_pub400_sign_on_detected(self):
        """PUB400 screen with 'user name' + 'Password' text is detected."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        session._screen = _make_sign_on_screen()
        assert session._is_sign_on_screen() is True

    def test_standard_ibmi_signon_detected(self):
        """Standard IBM i QDSIGNON with 5 fields + 'User'/'Password' text is detected."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        session._screen = _make_standard_signon_screen()
        assert session._is_sign_on_screen() is True

    def test_login_keyword_detected(self):
        """Screen with 'Login' + 'Password' is detected."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        session._screen = _make_login_screen()
        assert session._is_sign_on_screen() is True

    def test_username_keyword_detected(self):
        """Screen with 'Username' + 'Password' is detected."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        session._screen = _make_username_screen()
        assert session._is_sign_on_screen() is True

    def test_main_menu_not_detected(self):
        """Main menu has no sign-on keywords — must NOT trigger."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        session._screen = _make_main_menu_screen()
        assert session._is_sign_on_screen() is False

    def test_two_field_data_entry_not_detected(self):
        """A 2-field data entry screen without sign-on keywords must NOT trigger."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        session._screen = _make_two_field_data_entry_screen()
        assert session._is_sign_on_screen() is False

    def test_no_credentials_never_detects(self):
        """Without credentials configured, never returns True regardless of screen."""
        session = Tn5250Session(host="test")
        session._screen = _make_sign_on_screen()
        assert session._is_sign_on_screen() is False

    def test_no_username_never_detects(self):
        """With only password (no username), never returns True."""
        session = Tn5250Session(host="test", password="PASS")
        session._screen = _make_sign_on_screen()
        assert session._is_sign_on_screen() is False

    def test_no_password_never_detects(self):
        """With only username (no password), never returns True."""
        session = Tn5250Session(host="test", username="USER")
        session._screen = _make_sign_on_screen()
        assert session._is_sign_on_screen() is False

    def test_already_signed_in_never_detects(self):
        """Once signed in, _is_sign_on_screen always returns False."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        session._screen = _make_sign_on_screen()
        session._signed_in = True
        assert session._is_sign_on_screen() is False

    def test_case_insensitive_keyword_matching(self):
        """Keywords should match regardless of case (PASSWORD, Password, password)."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),
            sba(6, 24),
            bytes([ORDER_SF, 0x40, 0x00, 0x27, 0x00, 0x80]),
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        _put_text(screen, 4, 0, "USER NAME:")
        _put_text(screen, 5, 0, "PASSWORD:")
        session._screen = screen
        assert session._is_sign_on_screen() is True

    def test_no_input_fields_never_detects(self):
        """Screen with keywords but no input fields must NOT trigger."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        screen = ScreenBuffer()
        _put_text(screen, 4, 0, "User name:")
        _put_text(screen, 5, 0, "Password:")
        # No fields added
        session._screen = screen
        assert session._is_sign_on_screen() is False

    def test_password_keyword_required(self):
        """Screen with 'User name' but no 'Password' text must NOT trigger."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x20, 0x24, 0x00, 0x0A]),
            sba(6, 24),
            bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x0A]),
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        _put_text(screen, 4, 0, "User name:")
        _put_text(screen, 5, 0, "Account number:")
        session._screen = screen
        assert session._is_sign_on_screen() is False

    def test_user_keyword_required(self):
        """Screen with 'Password' but no user/login keyword must NOT trigger."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        data = make_wtd_data(
            sba(5, 24),
            bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x0A]),
            sba(6, 24),
            bytes([ORDER_SF, 0x40, 0x00, 0x27, 0x00, 0x80]),
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        _put_text(screen, 4, 0, "Account:")
        _put_text(screen, 5, 0, "Password:")
        session._screen = screen
        assert session._is_sign_on_screen() is False


class TestSignOnState:
    """Test that auto-signon only fires once and tracks signed-in state."""

    def test_signed_in_flag_starts_false(self):
        """Session starts with _signed_in = False."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        assert session._signed_in is False

    def test_auto_signon_sets_signed_in_flag(self):
        """After successful auto-signon, _signed_in is set to True."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        session._screen = _make_sign_on_screen()
        session.send_aid = AsyncMock()

        asyncio.get_event_loop().run_until_complete(session._auto_signon())

        assert session._signed_in is True

    def test_auto_signon_not_called_when_already_signed_in(self):
        """If _signed_in is True, _auto_signon does nothing."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        session._screen = _make_sign_on_screen()
        session._signed_in = True
        session.send_aid = AsyncMock()

        asyncio.get_event_loop().run_until_complete(session._auto_signon())

        session.send_aid.assert_not_called()


class TestSignOnExecution:
    """Test that auto-signon correctly fills fields and submits."""

    def test_fills_first_two_input_fields(self):
        """Types username into first input field, password into second."""
        session = Tn5250Session(host="test", username="testuser", password="testpassword123")
        session._screen = _make_sign_on_screen()
        session.send_aid = AsyncMock()

        asyncio.get_event_loop().run_until_complete(session._auto_signon())

        username_val = session._screen.get_field_value(session._screen.fields[0]).rstrip()
        password_val = session._screen.get_field_value(session._screen.fields[1]).rstrip()
        assert username_val == "TESTUSER"
        assert password_val == "testpassword123"

    def test_presses_enter(self):
        """Calls send_aid('enter') after filling fields."""
        session = Tn5250Session(host="test", username="USER", password="PASS")
        session._screen = _make_sign_on_screen()
        session.send_aid = AsyncMock()

        asyncio.get_event_loop().run_until_complete(session._auto_signon())

        session.send_aid.assert_called_once_with("enter")

    def test_works_with_5_field_signon(self):
        """Types into first 2 fields of a 5-field standard sign-on screen."""
        session = Tn5250Session(host="test", username="MYUSER", password="mypass")
        session._screen = _make_standard_signon_screen()
        session.send_aid = AsyncMock()

        asyncio.get_event_loop().run_until_complete(session._auto_signon())

        fields = session._screen.get_input_fields()
        username_val = session._screen.get_field_value(fields[0]).rstrip()
        password_val = session._screen.get_field_value(fields[1]).rstrip()
        assert username_val == "MYUSER"
        assert password_val == "mypass"
        # Other fields untouched
        assert session._screen.get_field_value(fields[2]).rstrip() == ""

    def test_skips_if_no_credentials(self):
        """Does nothing when credentials are not configured."""
        session = Tn5250Session(host="test")
        session._screen = _make_sign_on_screen()
        session.send_aid = AsyncMock()

        asyncio.get_event_loop().run_until_complete(session._auto_signon())

        session.send_aid.assert_not_called()
        assert session._signed_in is False
