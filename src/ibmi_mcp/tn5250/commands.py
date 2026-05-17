# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

import logging

from ibmi_mcp.tn5250.constants import (
    ORDER_EA,
    ORDER_IC,
    ORDER_MC,
    ORDER_RA,
    ORDER_SBA,
    ORDER_SF,
    ORDER_SOH,
    ORDER_TD,
    ORDER_WEA,
    ORDER_WDSF,
)
from ibmi_mcp.tn5250.ebcdic import to_unicode
from ibmi_mcp.tn5250.field import ScreenField
from ibmi_mcp.tn5250.screen import ScreenBuffer

logger = logging.getLogger(__name__)

ORDERS = {ORDER_SBA, ORDER_IC, ORDER_MC, ORDER_RA, ORDER_EA, ORDER_SOH,
          ORDER_TD, ORDER_WEA, ORDER_SF, ORDER_WDSF}


def _is_order(byte: int) -> bool:
    return byte in ORDERS


def parse_write_to_display(data: bytes, screen: ScreenBuffer, codepage: str = "cp037") -> int:
    """Parse WTD command data. Returns number of bytes consumed.

    Stops when it encounters ESC (0x04) at the top level, which signals
    the start of the next 5250 command.
    """
    pos = 0
    length = len(data)
    current_addr = 0
    ic_set = False

    if length < 2:
        return 0
    cc1 = data[0]
    pos = 2

    if cc1 & 0x20:
        for f in screen.fields:
            f.modified = False
    if cc1 & 0x40:
        screen.clear()

    # Track the last field added so we can compute its length later
    pending_field: ScreenField | None = None
    pending_field_start: int = 0

    def _finalize_field(end_addr: int) -> None:
        nonlocal pending_field
        if pending_field is not None and pending_field.length == 0:
            pending_field.length = max(1, end_addr - pending_field_start)
        pending_field = None

    while pos < length:
        byte = data[pos]

        if byte == 0x04:
            # ESC — next 5250 command starts here; stop WTD parsing
            break

        if byte == ORDER_SBA:
            if pos + 2 >= length:
                break
            row = data[pos + 1]
            col = data[pos + 2]
            current_addr = (row - 1) * screen.cols + (col - 1)
            pos += 3

        elif byte == ORDER_IC:
            r = current_addr // screen.cols
            c = current_addr % screen.cols
            screen.set_cursor(r, c)
            ic_set = True
            pos += 1

        elif byte == ORDER_MC:
            if pos + 2 >= length:
                break
            screen.set_cursor(data[pos + 1] - 1, data[pos + 2] - 1)
            ic_set = True
            pos += 3

        elif byte == ORDER_RA:
            if pos + 3 >= length:
                break
            target_addr = (data[pos + 1] - 1) * screen.cols + (data[pos + 2] - 1)
            fill_byte = data[pos + 3]
            fill_char = to_unicode(bytes([fill_byte]), codepage) if fill_byte >= 0x40 else " "
            while current_addr < target_addr and current_addr < screen.size:
                screen.set_char(current_addr, fill_char)
                current_addr += 1
            pos += 4

        elif byte == ORDER_EA:
            if pos + 2 >= length:
                break
            target_addr = (data[pos + 1] - 1) * screen.cols + (data[pos + 2] - 1)
            while current_addr < target_addr and current_addr < screen.size:
                screen.set_char(current_addr, " ")
                current_addr += 1
            pos += 3

        elif byte == ORDER_SF:
            _finalize_field(current_addr)

            pos += 1
            if pos >= length:
                break

            first_byte = data[pos]
            pos += 1

            ffw1 = ffw2 = 0
            fcw1 = fcw2 = 0
            attr = 0

            if (first_byte & 0xE0) != 0x20:
                # FFW is present — first byte is FFW1, not attribute
                ffw1 = first_byte
                if pos >= length:
                    break
                ffw2 = data[pos]
                pos += 1

                # Read FCW pairs until we hit an attribute byte (0x20-0x3F range)
                while pos + 1 < length and (data[pos] & 0xE0) != 0x20:
                    fcw1 = data[pos]
                    fcw2 = data[pos + 1]
                    pos += 2

                # Current byte is the attribute
                if pos >= length:
                    break
                attr = data[pos]
                pos += 1
            else:
                # No FFW — first byte IS the attribute (output-only field)
                attr = first_byte

            # Read 2-byte field length
            field_length = 0
            if pos + 1 < length:
                field_length = (data[pos] << 8) | data[pos + 1]
                pos += 2

            # Attribute byte occupies one screen position
            if current_addr < screen.size:
                screen.set_char(current_addr, " ")
            current_addr += 1

            field_row = current_addr // screen.cols
            field_col = current_addr % screen.cols

            field = ScreenField(
                row=field_row,
                col=field_col,
                length=field_length,
                attr=attr,
                ffw1=ffw1,
                ffw2=ffw2,
                fcw1=fcw1,
                fcw2=fcw2,
            )
            screen.add_field(field)
            pending_field = field
            pending_field_start = current_addr

        elif byte == ORDER_SOH:
            if pos + 1 >= length:
                break
            header_len = data[pos + 1]
            pos += 2 + header_len

        elif byte == ORDER_TD:
            if pos + 1 >= length:
                break
            td_len = data[pos + 1]
            pos += 2
            for i in range(td_len):
                if pos + i < length and current_addr < screen.size:
                    ch = to_unicode(bytes([data[pos + i]]), codepage)
                    screen.set_char(current_addr, ch)
                    current_addr += 1
            pos += td_len

        elif byte == ORDER_WEA:
            pos += 3

        elif byte == ORDER_WDSF:
            if pos + 1 >= length:
                break
            wdsf_len = data[pos + 1]
            pos += wdsf_len

        elif 0x20 <= byte <= 0x3F:
            # Attribute byte — occupies one screen position as a space,
            # and marks the end of any preceding field
            _finalize_field(current_addr)
            if current_addr < screen.size:
                screen.set_char(current_addr, " ")
            current_addr += 1
            pos += 1

        elif byte >= 0x40:
            ch = to_unicode(bytes([byte]), codepage)
            if current_addr < screen.size:
                screen.set_char(current_addr, ch)
            current_addr += 1
            pos += 1

        elif byte == 0x00:
            if current_addr < screen.size:
                screen.set_char(current_addr, " ")
            current_addr += 1
            pos += 1

        else:
            # Bytes 0x01-0x1F not recognized as orders —
            # treat as null characters occupying a screen position
            if current_addr < screen.size:
                screen.set_char(current_addr, " ")
            current_addr += 1
            pos += 1

    # Finalize any trailing field
    _finalize_field(current_addr)

    # Per 5250 spec: if no IC/MC order was present, default cursor to first input field
    if not ic_set:
        input_fields = screen.get_input_fields()
        if input_fields:
            screen.set_cursor(input_fields[0].row, input_fields[0].col)

    return pos


def parse_clear(screen: ScreenBuffer) -> None:
    screen.clear()


def parse_roll(data: bytes, screen: ScreenBuffer) -> None:
    if len(data) < 2:
        return
    direction_up = bool(data[0] & 0x80)
    lines = data[0] & 0x1F
    top_line = (data[1] >> 4) & 0x0F
    bottom_line = data[1] & 0x0F

    if direction_up:
        for _ in range(lines):
            for row in range(top_line, bottom_line):
                src_start = (row + 1) * screen.cols
                dst_start = row * screen.cols
                for c in range(screen.cols):
                    screen.buffer[dst_start + c] = screen.buffer[src_start + c]
            blank_start = bottom_line * screen.cols
            for c in range(screen.cols):
                screen.buffer[blank_start + c] = " "


def build_response(screen: ScreenBuffer, aid: int, codepage: str = "cp037") -> bytes:
    from ibmi_mcp.tn5250.ebcdic import to_ebcdic

    buf = bytearray()
    buf.append(screen.cursor_row + 1)
    buf.append(screen.cursor_col + 1)
    buf.append(aid)

    for field in screen.fields:
        if field.ffw1 & 0x08:  # MDT bit set
            buf.append(ORDER_SBA)
            buf.append(field.row + 1)
            buf.append(field.col + 1)
            value = screen.get_field_value(field).rstrip(" \x00")
            buf.extend(to_ebcdic(value, codepage))

    screen.modified_positions.clear()
    return bytes(buf)
