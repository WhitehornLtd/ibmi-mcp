"""Tests for local editing keys: Backspace, Delete, Field Exit, Home, End."""

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


def _make_session_with_field(value: str = "", field_length: int = 10) -> Tn5250Session:
    """Create a session with one input field pre-filled with value."""
    data = make_wtd_data(
        sba(5, 10),
        bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, field_length]),
    )
    session = Tn5250Session(host="test")
    session._screen = ScreenBuffer()
    parse_write_to_display(data, session._screen)

    if value:
        field = session._screen.fields[0]
        start = field.row * session._screen.cols + field.col
        for i, ch in enumerate(value):
            session._screen.set_char(start + i, ch)

    return session


def _make_session_with_two_fields(val1: str = "", val2: str = "") -> Tn5250Session:
    """Create a session with two input fields."""
    data = make_wtd_data(
        sba(5, 10),
        bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x0A]),  # field 1, len=10
        sba(7, 10),
        bytes([ORDER_SF, 0x40, 0x00, 0x24, 0x00, 0x0A]),  # field 2, len=10
    )
    session = Tn5250Session(host="test")
    session._screen = ScreenBuffer()
    parse_write_to_display(data, session._screen)

    fields = session._screen.get_input_fields()
    if val1:
        start = fields[0].row * session._screen.cols + fields[0].col
        for i, ch in enumerate(val1):
            session._screen.set_char(start + i, ch)
    if val2:
        start = fields[1].row * session._screen.cols + fields[1].col
        for i, ch in enumerate(val2):
            session._screen.set_char(start + i, ch)

    return session


def _get_field_value(session: Tn5250Session, field_idx: int = 0) -> str:
    fields = session._screen.get_input_fields()
    return session._screen.get_field_value(fields[field_idx])


class TestBackspace:
    """Backspace: delete char left of cursor, shift field content left, blank at end."""

    def test_backspace_middle_of_field(self):
        """Backspace in middle shifts content left."""
        session = _make_session_with_field("HELLO")
        # Cursor after the 'L' (position 3 in field, 0-indexed)
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col + 3)

        session.backspace()

        # "HELLO" with cursor at pos 3 → delete 'L' at pos 2 → "HELO "
        assert _get_field_value(session).rstrip() == "HELO"
        assert session._screen.cursor_col == field.col + 2

    def test_backspace_end_of_text(self):
        """Backspace at end of typed text removes last character."""
        session = _make_session_with_field("TEST")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col + 4)

        session.backspace()

        assert _get_field_value(session).rstrip() == "TES"
        assert session._screen.cursor_col == field.col + 3

    def test_backspace_at_field_start_does_nothing(self):
        """Backspace at the start of a field is a no-op."""
        session = _make_session_with_field("HELLO")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col)

        session.backspace()

        assert _get_field_value(session).rstrip() == "HELLO"
        assert session._screen.cursor_col == field.col

    def test_backspace_marks_field_modified(self):
        """Backspace sets the MDT bit on the field."""
        session = _make_session_with_field("AB")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col + 1)

        session.backspace()

        assert field.ffw1 & 0x08  # MDT bit


class TestDelete:
    """Delete: remove char at cursor, shift remaining content left, blank at end."""

    def test_delete_at_start(self):
        """Delete at start removes first char, shifts rest left."""
        session = _make_session_with_field("HELLO")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col)

        session.delete()

        assert _get_field_value(session).rstrip() == "ELLO"
        # Cursor stays at same position
        assert session._screen.cursor_col == field.col

    def test_delete_in_middle(self):
        """Delete in middle removes char at cursor, shifts rest left."""
        session = _make_session_with_field("ABCDE")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col + 2)  # on 'C'

        session.delete()

        assert _get_field_value(session).rstrip() == "ABDE"
        assert session._screen.cursor_col == field.col + 2

    def test_delete_at_end_clears_last_char(self):
        """Delete at last character of content clears it."""
        session = _make_session_with_field("AB")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col + 1)  # on 'B'

        session.delete()

        assert _get_field_value(session).rstrip() == "A"

    def test_delete_on_empty_field_does_nothing(self):
        """Delete on a blank field position is a no-op."""
        session = _make_session_with_field("")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col)

        session.delete()

        assert _get_field_value(session).rstrip() == ""

    def test_delete_marks_field_modified(self):
        """Delete sets the MDT bit on the field."""
        session = _make_session_with_field("X")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col)

        session.delete()

        assert field.ffw1 & 0x08  # MDT bit


class TestFieldExit:
    """Field Exit: clear from cursor to end of field, advance to next field."""

    def test_field_exit_clears_to_end(self):
        """Field Exit clears from cursor position to end of field."""
        session = _make_session_with_two_fields("SOMEWHERE", "OTHER")
        fields = session._screen.get_input_fields()
        # Position cursor in middle of first field
        session._screen.set_cursor(fields[0].row, fields[0].col + 4)

        session.field_exit()

        # "SOMEWHERE" → "SOME      " (cleared from pos 4 onward)
        assert _get_field_value(session, 0).rstrip() == "SOME"

    def test_field_exit_moves_to_next_field(self):
        """After clearing, cursor moves to next input field."""
        session = _make_session_with_two_fields("SOMEWHERE", "OTHER")
        fields = session._screen.get_input_fields()
        session._screen.set_cursor(fields[0].row, fields[0].col + 4)

        session.field_exit()

        assert session._screen.cursor_row == fields[1].row
        assert session._screen.cursor_col == fields[1].col

    def test_field_exit_at_start_clears_entire_field(self):
        """Field Exit at start of field clears entire field content."""
        session = _make_session_with_two_fields("HELLO", "WORLD")
        fields = session._screen.get_input_fields()
        session._screen.set_cursor(fields[0].row, fields[0].col)

        session.field_exit()

        assert _get_field_value(session, 0).rstrip() == ""

    def test_field_exit_wraps_to_first_field(self):
        """Field Exit on last field wraps cursor to first field."""
        session = _make_session_with_two_fields("AAA", "BBB")
        fields = session._screen.get_input_fields()
        # Cursor on second (last) field
        session._screen.set_cursor(fields[1].row, fields[1].col + 1)

        session.field_exit()

        assert session._screen.cursor_row == fields[0].row
        assert session._screen.cursor_col == fields[0].col

    def test_field_exit_marks_field_modified(self):
        """Field Exit sets the MDT bit."""
        session = _make_session_with_field("DATA")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col)

        session.field_exit()

        assert field.ffw1 & 0x08  # MDT bit

    def test_field_exit_second_field_untouched(self):
        """Field Exit only clears the current field, not others."""
        session = _make_session_with_two_fields("FIRST", "SECOND")
        fields = session._screen.get_input_fields()
        session._screen.set_cursor(fields[0].row, fields[0].col)

        session.field_exit()

        assert _get_field_value(session, 1).rstrip() == "SECOND"


class TestHome:
    """Home: move cursor to first position of first input field."""

    def test_home_moves_to_first_field(self):
        """Home moves cursor to start of first input field."""
        session = _make_session_with_two_fields("AAA", "BBB")
        fields = session._screen.get_input_fields()
        # Cursor somewhere else
        session._screen.set_cursor(fields[1].row, fields[1].col + 5)

        session.home()

        assert session._screen.cursor_row == fields[0].row
        assert session._screen.cursor_col == fields[0].col

    def test_home_already_at_first_field(self):
        """Home when already at first field stays there."""
        session = _make_session_with_two_fields()
        fields = session._screen.get_input_fields()
        session._screen.set_cursor(fields[0].row, fields[0].col)

        session.home()

        assert session._screen.cursor_row == fields[0].row
        assert session._screen.cursor_col == fields[0].col

    def test_home_no_fields_does_nothing(self):
        """Home with no input fields is a no-op."""
        session = Tn5250Session(host="test")
        session._screen = ScreenBuffer()
        session._screen.set_cursor(5, 10)

        session.home()

        assert session._screen.cursor_row == 5
        assert session._screen.cursor_col == 10


class TestEnd:
    """End: move cursor to position after last non-blank char in current field."""

    def test_end_moves_past_content(self):
        """End moves cursor to position after last non-blank character."""
        session = _make_session_with_field("HELLO")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col)  # at start

        session.end()

        # "HELLO" is 5 chars, cursor should be at col+5
        assert session._screen.cursor_row == field.row
        assert session._screen.cursor_col == field.col + 5

    def test_end_on_empty_field_stays_at_start(self):
        """End on empty field leaves cursor at field start."""
        session = _make_session_with_field("")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col)

        session.end()

        assert session._screen.cursor_col == field.col

    def test_end_on_full_field_goes_to_last_position(self):
        """End on a completely filled field puts cursor at last position."""
        session = _make_session_with_field("ABCDEFGHIJ")  # exactly 10 chars = full field
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col)

        session.end()

        # Field is full, cursor at the last valid position (field_length - 1 offset)
        assert session._screen.cursor_col == field.col + 9

    def test_end_not_in_field_does_nothing(self):
        """End when cursor is not in any field is a no-op."""
        session = _make_session_with_field("DATA")
        session._screen.set_cursor(0, 0)  # not in the field

        session.end()

        assert session._screen.cursor_row == 0
        assert session._screen.cursor_col == 0


class TestLocalKeysViaSendKey:
    """Test that local editing keys are accessible through the send_key tool interface."""

    def test_backspace_via_send_key_name(self):
        """The key name 'Backspace' should trigger local backspace handling."""
        session = _make_session_with_field("AB")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col + 2)

        # This tests that session.handle_local_key recognizes these names
        assert session.handle_local_key("backspace") is True

    def test_delete_via_send_key_name(self):
        assert _make_session_with_field("X").handle_local_key("delete") is True

    def test_field_exit_via_send_key_name(self):
        assert _make_session_with_field("X").handle_local_key("fieldexit") is True

    def test_home_via_send_key_name(self):
        assert _make_session_with_field("X").handle_local_key("home") is True

    def test_end_via_send_key_name(self):
        session = _make_session_with_field("X")
        field = session._screen.fields[0]
        session._screen.set_cursor(field.row, field.col)
        assert session.handle_local_key("end") is True

    def test_unknown_key_returns_false(self):
        """Non-local keys return False (should be sent to host)."""
        session = _make_session_with_field("X")
        assert session.handle_local_key("enter") is False
        assert session.handle_local_key("f3") is False
