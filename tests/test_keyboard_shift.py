"""Tests for 5250 keyboard-shift enforcement on typed input.

A conforming 5250 device refuses characters the field's shift does not permit
and inhibits the keyboard rather than transmitting them. Accepting them lets a
probe reach the host with data no real terminal could have sent — on NEXUS that
produced an MCH1202 decimal-data error from a screen a user could not have
keyed.

The permitted sets follow the field shift/edit specification in FFW1 bits 5-7,
as implemented by tn5250's tn5250_field_valid_char:

    alpha shift    every character
    alpha only     letters, comma, period, hyphen, space
    numeric shift  every character
    numeric only   digits, comma, period, hyphen, space
    katakana       not implemented — permissive
    digits only    digits
    I/O only       nothing may be keyed
    signed numeric digits (the sign is entered by a separate field-exit key)
"""

import pytest

from ibmi_mcp.tn5250.commands import parse_write_to_display
from ibmi_mcp.tn5250.constants import ORDER_SBA, ORDER_SF
from ibmi_mcp.tn5250.field import ScreenField
from ibmi_mcp.tn5250.screen import ScreenBuffer
from ibmi_mcp.tn5250.session import KeyboardInhibitedError, Tn5250Session


def field_with_shift(shift: int) -> ScreenField:
    # 0x40 marks the FFW as present (an input field); low 3 bits are the shift.
    return ScreenField(row=4, col=1, length=6, ffw1=0x40 | shift, attr=0x24)


class TestPermittedCharacters:
    @pytest.mark.parametrize("shift", [0x00, 0x02, 0x04])
    def test_permissive_shifts_accept_anything(self, shift):
        field = field_with_shift(shift)
        for ch in "aZ9 .,-+/":
            assert field.permits(ch) is True

    def test_signed_numeric_accepts_only_digits(self):
        field = field_with_shift(0x07)
        assert field.field_type == "signed_numeric"
        for ch in "0123456789":
            assert field.permits(ch) is True
        for ch in ".,-+ aZ":
            assert field.permits(ch) is False, f"{ch!r} is not keyable"

    def test_digits_only_accepts_only_digits(self):
        field = field_with_shift(0x05)
        assert field.field_type == "digits_only"
        assert field.permits("7") is True
        for ch in ".,- aZ":
            assert field.permits(ch) is False

    def test_numeric_only_allows_punctuation_but_not_letters(self):
        field = field_with_shift(0x03)
        assert field.field_type == "numeric_only"
        for ch in "0123456789,.- ":
            assert field.permits(ch) is True
        for ch in "aZ+/":
            assert field.permits(ch) is False

    def test_alpha_only_allows_letters_but_not_digits(self):
        field = field_with_shift(0x01)
        assert field.field_type == "alpha_only"
        for ch in "aZ,.- ":
            assert field.permits(ch) is True
        for ch in "0123456789":
            assert field.permits(ch) is False

    def test_io_only_accepts_nothing(self):
        field = field_with_shift(0x06)
        assert field.field_type == "io_only"
        for ch in "0aZ .,-":
            assert field.permits(ch) is False


class TestTypingIsRefused:
    """The reported defect: send_keys('1.2.3') into a signed-numeric field."""

    def make_session(self) -> Tn5250Session:
        data = b"\x00\x00" + bytes(
            [ORDER_SBA, 5, 1, ORDER_SF, 0x47, 0x00, 0x24, 0x00, 0x06]
        )
        session = Tn5250Session("testhost")
        parse_write_to_display(data, session.screen)
        session.screen.set_cursor(4, 1)
        return session

    @pytest.mark.asyncio
    async def test_a_period_is_refused_in_a_signed_numeric_field(self):
        session = self.make_session()
        assert session.screen.get_input_fields()[0].field_type == "signed_numeric"

        with pytest.raises(KeyboardInhibitedError):
            await session.type_keys("1.2.3")

    @pytest.mark.asyncio
    async def test_a_refused_keystroke_leaves_the_field_untouched(self):
        """A device inhibits before accepting anything — not partway through."""
        session = self.make_session()
        field = session.screen.get_input_fields()[0]

        with pytest.raises(KeyboardInhibitedError):
            await session.type_keys("1.2.3")

        assert session.screen.get_field_value(field).strip() == ""
        assert field.modified is False

    @pytest.mark.asyncio
    async def test_digits_are_still_accepted(self):
        session = self.make_session()
        field = session.screen.get_input_fields()[0]

        await session.type_keys("00099")

        assert session.screen.get_field_value(field).strip() == "00099"

    @pytest.mark.asyncio
    async def test_the_error_names_the_character_and_the_shift(self):
        session = self.make_session()

        with pytest.raises(KeyboardInhibitedError) as excinfo:
            await session.type_keys("1.2")

        message = str(excinfo.value)
        assert "." in message
        assert "signed_numeric" in message
