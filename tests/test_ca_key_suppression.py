"""Tests for command-attention key data suppression.

A 5250 device does not transmit changed field data when the operator presses a
command-attention (CA) key, and it bypasses field editing for those keys. It
learns which keys those are from the command-key switch mask in the Start of
Header order, not from the DDS — the device never sees the display file.

tn5250's tn5250_dbuffer_send_data_for_aid_key is the reference: keys F1-F8 are
held in header byte 6, F9-F16 in byte 5, F17-F24 in byte 4, and a **set** bit
means suppress. A header shorter than 7 bytes carries no mask, so data is sent.

The mapping is confirmed against real hardware. RPGC/QDDSSRC(CAKEY) binds
CA03 to F3 and CF05 to F5, and the SOH header NEXUS sends for it is

    00 00 00 18 00 00 04
                ^^     ^^
                |      byte 6 = 0x04 — the F3 bit, i.e. suppress for CA03
                byte 3 = 0x18 = 24, the operator error line

so F3 suppresses and F5 transmits, exactly as the DDS declares.
"""

import pytest

from ibmi_mcp.tn5250.commands import build_response, parse_write_to_display
from ibmi_mcp.tn5250.constants import (
    AID_ENTER,
    AID_F3,
    AID_F5,
    AID_F9,
    AID_F17,
    ORDER_SBA,
    ORDER_SF,
    ORDER_SOH,
)
from ibmi_mcp.tn5250.screen import ScreenBuffer

# The WTD NEXUS sends for RPGC/CAKEYP: SOH with the command-key mask, then the
# label, the signed-numeric input field, and the key legend.
CAKEYP_WTD = bytes.fromhex(
    "00280107000000180000"
    "0411040120d5a494859989837a201105011d47002400060000"
    "0000000011080120c6f37ec3c14085a789a34040c6f57ec3c6"
    "40a385a2a32020"
)


def screen_with_mask(*mask_bytes: int) -> ScreenBuffer:
    """A screen whose SOH carries the given 3-byte command-key mask."""
    header = bytes([0x00, 0x00, 0x00, 0x18, *mask_bytes])
    data = (
        b"\x00\x00"
        + bytes([ORDER_SOH, len(header)])
        + header
        + bytes([ORDER_SBA, 5, 1, ORDER_SF, 0x47, 0x00, 0x24, 0x00, 0x06])
    )
    screen = ScreenBuffer()
    parse_write_to_display(data, screen)
    field = screen.fields[0]
    screen.set_field_value(field, "10")
    return screen


def field_data_sent(screen: ScreenBuffer, aid: int) -> bool:
    """A response carries field data when it is longer than cursor + AID."""
    return len(build_response(screen, aid)) > 3


class TestHeaderIsCaptured:
    def test_the_soh_header_is_retained(self):
        screen = ScreenBuffer()
        parse_write_to_display(CAKEYP_WTD, screen)

        assert bytes(screen.header_data) == bytes.fromhex("00000018000004"), (
            "the command-key mask lives in the SOH header and must be kept"
        )

    def test_a_screen_with_no_soh_has_no_header(self):
        screen = ScreenBuffer()
        parse_write_to_display(
            b"\x00\x00" + bytes([ORDER_SBA, 5, 1]), screen
        )
        assert not screen.header_data


class TestSuppressionAgainstRealHardware:
    """CAKEY binds CA03 to F3 and CF05 to F5."""

    def real_screen(self) -> ScreenBuffer:
        screen = ScreenBuffer()
        parse_write_to_display(CAKEYP_WTD, screen)
        screen.set_field_value(screen.fields[0], "10")
        return screen

    def test_the_command_attention_key_withholds_the_typed_data(self):
        assert field_data_sent(self.real_screen(), AID_F3) is False

    def test_the_command_function_key_sends_the_typed_data(self):
        assert field_data_sent(self.real_screen(), AID_F5) is True

    def test_enter_always_sends_the_typed_data(self):
        assert field_data_sent(self.real_screen(), AID_ENTER) is True

    def test_a_suppressed_response_still_reports_cursor_and_aid(self):
        response = build_response(self.real_screen(), AID_F3)
        assert len(response) == 3
        assert response[2] == AID_F3


class TestBitMapping:
    """Each group of eight keys lives in its own header byte."""

    def test_f1_to_f8_live_in_byte_6(self):
        # 0x10 is the F5 bit within its byte.
        screen = screen_with_mask(0x00, 0x00, 0x10)
        assert field_data_sent(screen, AID_F5) is False
        assert field_data_sent(screen, AID_F3) is True

    def test_f9_to_f16_live_in_byte_5(self):
        # F9 is the first key of the second group.
        screen = screen_with_mask(0x00, 0x01, 0x00)
        assert field_data_sent(screen, AID_F9) is False
        assert field_data_sent(screen, AID_F5) is True

    def test_f17_to_f24_live_in_byte_4(self):
        screen = screen_with_mask(0x01, 0x00, 0x00)
        assert field_data_sent(screen, AID_F17) is False
        assert field_data_sent(screen, AID_F9) is True

    def test_an_all_clear_mask_sends_data_for_every_key(self):
        screen = screen_with_mask(0x00, 0x00, 0x00)
        for aid in (AID_F3, AID_F5, AID_F9, AID_F17, AID_ENTER):
            assert field_data_sent(screen, aid) is True


class TestNoMaskMeansSend:
    def test_a_short_header_carries_no_mask(self):
        """tn5250 sends data whenever the header is 6 bytes or fewer."""
        data = (
            b"\x00\x00"
            + bytes([ORDER_SOH, 4, 0x00, 0x00, 0x00, 0x18])
            + bytes([ORDER_SBA, 5, 1, ORDER_SF, 0x47, 0x00, 0x24, 0x00, 0x06])
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        screen.set_field_value(screen.fields[0], "10")

        assert field_data_sent(screen, AID_F3) is True

    def test_no_header_at_all_sends_data(self):
        data = b"\x00\x00" + bytes(
            [ORDER_SBA, 5, 1, ORDER_SF, 0x47, 0x00, 0x24, 0x00, 0x06]
        )
        screen = ScreenBuffer()
        parse_write_to_display(data, screen)
        screen.set_field_value(screen.fields[0], "10")

        assert field_data_sent(screen, AID_F3) is True
