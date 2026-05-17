# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

import asyncio
import logging
from enum import Enum

from ibmi_mcp.tn5250.commands import (
    build_response,
    parse_clear,
    parse_roll,
    parse_write_to_display,
)
from ibmi_mcp.tn5250.constants import (
    CMD_CLEAR_FORMAT_TABLE,
    CMD_CLEAR_UNIT,
    CMD_ROLL,
    CMD_WRITE_ERROR_CODE,
    CMD_WRITE_STRUCTURED_FIELD,
    CMD_WRITE_TO_DISPLAY,
    ESC,
    GDS_FLAG_ATN,
    GDS_FLAG_SRQ,
    KEY_TO_AID,
    OP_CANCEL_INVITE,
    OP_INVITE,
    OP_MSG_LIGHT_OFF,
    OP_MSG_LIGHT_ON,
    OP_NO_OP,
    OP_OUTPUT_ONLY,
    OP_PUT_GET,
    OP_READ_IMMEDIATE,
    OP_READ_SCREEN,
    OP_RESTORE_SCREEN,
    OP_SAVE_SCREEN,
)
from ibmi_mcp.tn5250.protocol import TelnetNegotiator
from ibmi_mcp.tn5250.screen import ScreenBuffer
from ibmi_mcp.tn5250.stream import TelnetStream

logger = logging.getLogger(__name__)


class SessionState(Enum):
    DISCONNECTED = "disconnected"
    NEGOTIATING = "negotiating"
    CONNECTED = "connected"
    WAITING = "waiting"


class Tn5250Session:
    def __init__(
        self,
        host: str,
        port: int = 23,
        use_ssl: bool = False,
        terminal_type: str = "IBM-3179-2",
        device_name: str = "",
        codepage: str = "cp037",
        username: str = "",
        password: str = "",
    ):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.terminal_type = terminal_type
        self.device_name = device_name
        self.codepage = codepage
        self.username = username
        self.password = password

        self._stream = TelnetStream()
        self._screen = ScreenBuffer()
        self._state = SessionState.DISCONNECTED
        self._keyboard_locked = True
        self._unlock_event = asyncio.Event()
        self._message_light = False
        self._pending_query = False
        self._signed_in = False
        self._timed_out = False
        self.response_timeout = 30.0

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def screen(self) -> ScreenBuffer:
        return self._screen

    @property
    def keyboard_locked(self) -> bool:
        return self._keyboard_locked

    @property
    def timed_out(self) -> bool:
        return self._timed_out

    async def connect(self) -> None:
        await self._stream.connect(self.host, self.port, self.use_ssl)
        self._state = SessionState.NEGOTIATING

        negotiator = TelnetNegotiator(
            self._stream,
            terminal_type=self.terminal_type,
            device_name=self.device_name,
            codepage=self.codepage.replace("cp", ""),
            username=self.username,
        )
        await negotiator.run_initial_negotiation()
        self._state = SessionState.CONNECTED

        # Process initial screen data
        await self._process_until_unlocked()

        # Auto-signon if credentials are configured and we're on a sign-on screen
        if self._is_sign_on_screen():
            await self._auto_signon()

    async def disconnect(self) -> None:
        await self._stream.close()
        self._state = SessionState.DISCONNECTED
        self._screen.clear()

    async def send_aid(self, key_name: str) -> None:
        key_name_lower = key_name.lower().strip()
        aid = KEY_TO_AID.get(key_name_lower)
        if aid is None:
            raise ValueError(
                f"Unknown key: {key_name}. Valid keys: {', '.join(sorted(KEY_TO_AID.keys()))}"
            )

        response_data = build_response(self._screen, aid, self.codepage)
        frame = self._build_gds_frame(response_data, opcode=OP_PUT_GET)
        self._keyboard_locked = True
        self._unlock_event.clear()
        await self._stream.write_frame(frame)
        await self._process_until_unlocked(timeout=self.response_timeout)

    async def send_attention(self) -> None:
        frame = self._build_gds_frame(b"", opcode=OP_NO_OP, flags=GDS_FLAG_ATN)
        self._keyboard_locked = True
        self._unlock_event.clear()
        await self._stream.write_frame(frame)
        await self._process_until_unlocked(timeout=self.response_timeout)

    async def type_keys(self, text: str) -> None:
        """Type text at the current cursor position."""
        cursor = self._screen.cursor_pos()

        # Check if current field is monocase (FFW2 bit 0x20)
        field = self._screen.get_field_at_cursor()
        monocase = field is not None and bool(field.ffw2 & 0x20)

        for i, ch in enumerate(text):
            pos = cursor + i
            if pos >= self._screen.size:
                break
            if monocase:
                ch = ch.upper()
            self._screen.set_char(pos, ch)
            self._screen.modified_positions.add(pos)

        # Mark any field at cursor as modified
        field = self._screen.get_field_at_cursor()
        if field:
            field.set_modified()

        new_col = self._screen.cursor_col + len(text)
        new_row = self._screen.cursor_row
        while new_col >= self._screen.cols:
            new_col -= self._screen.cols
            new_row += 1
        self._screen.set_cursor(new_row, new_col)

    def move_cursor(self, row: int, col: int) -> None:
        """Move cursor to position (1-based row/col from user, 0-based internal)."""
        self._screen.set_cursor(row - 1, col - 1)

    def handle_local_key(self, key_name: str) -> bool:
        """Handle a local editing key. Returns True if handled, False if not a local key."""
        key = key_name.lower().strip()
        if key == "backspace":
            self.backspace()
            return True
        elif key in ("delete", "del"):
            self.delete()
            return True
        elif key in ("fieldexit", "field_exit", "field exit"):
            self.field_exit()
            return True
        elif key == "home":
            self.home()
            return True
        elif key == "end":
            self.end()
            return True
        return False

    def backspace(self) -> None:
        """Delete character to the left of cursor, shift field content left."""
        field = self._screen.get_field_at_cursor()
        if not field:
            return

        field_start = field.row * self._screen.cols + field.col
        cursor = self._screen.cursor_pos()

        if cursor <= field_start:
            return

        field_end = field_start + field.length
        # Shift everything from cursor to end of field one position left
        for pos in range(cursor - 1, field_end - 1):
            self._screen.set_char(pos, self._screen.get_char(pos + 1))
        # Blank the last position
        self._screen.set_char(field_end - 1, " ")
        # Move cursor back one
        self._screen.set_cursor(
            (cursor - 1) // self._screen.cols,
            (cursor - 1) % self._screen.cols,
        )
        field.set_modified()

    def delete(self) -> None:
        """Delete character at cursor, shift remaining field content left."""
        field = self._screen.get_field_at_cursor()
        if not field:
            return

        field_start = field.row * self._screen.cols + field.col
        field_end = field_start + field.length
        cursor = self._screen.cursor_pos()

        # Shift everything from cursor+1 to end of field one position left
        for pos in range(cursor, field_end - 1):
            self._screen.set_char(pos, self._screen.get_char(pos + 1))
        # Blank the last position
        self._screen.set_char(field_end - 1, " ")
        field.set_modified()

    def field_exit(self) -> None:
        """Clear from cursor to end of field, move cursor to next input field."""
        field = self._screen.get_field_at_cursor()
        if not field:
            return

        field_start = field.row * self._screen.cols + field.col
        field_end = field_start + field.length
        cursor = self._screen.cursor_pos()

        # Clear from cursor to end of field
        for pos in range(cursor, field_end):
            self._screen.set_char(pos, " ")
        field.set_modified()

        # Move to next input field (wrap around)
        input_fields = self._screen.get_input_fields()
        if not input_fields:
            return
        current_idx = None
        for i, f in enumerate(input_fields):
            if f.row == field.row and f.col == field.col:
                current_idx = i
                break
        if current_idx is not None:
            next_idx = (current_idx + 1) % len(input_fields)
            next_field = input_fields[next_idx]
            self._screen.set_cursor(next_field.row, next_field.col)

    def home(self) -> None:
        """Move cursor to first position of first input field."""
        input_fields = self._screen.get_input_fields()
        if not input_fields:
            return
        self._screen.set_cursor(input_fields[0].row, input_fields[0].col)

    def end(self) -> None:
        """Move cursor after last non-blank character in current field."""
        field = self._screen.get_field_at_cursor()
        if not field:
            return

        field_start = field.row * self._screen.cols + field.col
        field_end = field_start + field.length

        # Find last non-blank position
        last_nonblank = field_start - 1
        for pos in range(field_start, field_end):
            if self._screen.get_char(pos) != " ":
                last_nonblank = pos

        if last_nonblank < field_start:
            # Field is empty, stay at field start
            self._screen.set_cursor(field.row, field.col)
        elif last_nonblank >= field_end - 1:
            # Field is full, go to last position
            self._screen.set_cursor(
                (field_end - 1) // self._screen.cols,
                (field_end - 1) % self._screen.cols,
            )
        else:
            # Position after last non-blank
            target = last_nonblank + 1
            self._screen.set_cursor(
                target // self._screen.cols,
                target % self._screen.cols,
            )

    def _is_sign_on_screen(self) -> bool:
        """Detect if the current screen is a sign-on screen requiring credentials.

        Conservative: requires ALL of:
        - Credentials configured (username AND password)
        - Not already signed in
        - At least 2 input fields on screen
        - Screen text contains 'password' (case-insensitive)
        - Screen text contains one of: 'user name', 'username', 'login' (case-insensitive)
        """
        if self._signed_in:
            return False
        if not self.username or not self.password:
            return False
        input_fields = self._screen.get_input_fields()
        if len(input_fields) < 2:
            return False

        screen_text = " ".join(self._screen.get_text_rows()).lower()
        if "password" not in screen_text:
            return False
        if not any(kw in screen_text for kw in ("user name", "username", "login", "user  .")):
            return False
        return True

    async def _auto_signon(self) -> None:
        """Automatically fill credentials and press Enter on a sign-on screen."""
        if self._signed_in:
            return
        if not self.username or not self.password:
            return

        input_fields = self._screen.get_input_fields()
        if len(input_fields) < 2:
            return

        username_field = input_fields[0]
        password_field = input_fields[1]

        # Type username into first field
        self._screen.set_cursor(username_field.row, username_field.col)
        await self.type_keys(self.username)

        # Type password into second field
        self._screen.set_cursor(password_field.row, password_field.col)
        await self.type_keys(self.password)

        # Press Enter
        await self.send_aid("enter")
        self._signed_in = True

    async def _process_until_unlocked(self, timeout: float = 30.0) -> None:
        """Read and process frames from host until keyboard is unlocked."""
        self._timed_out = False
        frame_count = 0
        try:
            while self._keyboard_locked:
                frame = await asyncio.wait_for(
                    self._stream.read_frame(), timeout=timeout
                )
                frame_count += 1
                self._process_gds_frame(frame)
                if self._pending_query:
                    await self._send_query_reply()
                    self._pending_query = False
        except asyncio.TimeoutError:
            self._keyboard_locked = False
            self._timed_out = True

    def _process_gds_frame(self, frame: bytes) -> None:
        """Parse a GDS record and dispatch by opcode."""
        if len(frame) < 10:
            logger.warning(f"Short GDS frame: {len(frame)} bytes")
            return

        # GDS header: 2 bytes length, 2 bytes record type (0x12A0),
        # 2 bytes reserved, 1 byte var hdr len, 1 byte flags, 1 byte reserved, 1 byte opcode
        record_len = (frame[0] << 8) | frame[1]
        flags = frame[7]
        opcode = frame[9]

        # Variable header (skip past it)
        var_hdr_len = frame[6]
        data_start = 10 + (var_hdr_len - 4 if var_hdr_len > 4 else 0)
        data = frame[data_start:]

        logger.debug(f"GDS opcode={opcode:#x} flags={flags:#x} data_len={len(data)}")

        if opcode == OP_NO_OP:
            pass

        elif opcode == OP_INVITE:
            self._keyboard_locked = False
            self._unlock_event.set()

        elif opcode == OP_OUTPUT_ONLY:
            self._parse_commands(data)

        elif opcode == OP_PUT_GET:
            self._parse_commands(data)
            if not self._pending_query:
                self._keyboard_locked = False
                self._unlock_event.set()

        elif opcode == OP_SAVE_SCREEN:
            pass  # TODO: implement screen save stack

        elif opcode == OP_RESTORE_SCREEN:
            pass  # TODO: implement screen restore

        elif opcode == OP_READ_IMMEDIATE:
            self._keyboard_locked = False
            self._unlock_event.set()

        elif opcode == OP_READ_SCREEN:
            self._keyboard_locked = False
            self._unlock_event.set()

        elif opcode == OP_CANCEL_INVITE:
            pass

        elif opcode == OP_MSG_LIGHT_ON:
            self._message_light = True

        elif opcode == OP_MSG_LIGHT_OFF:
            self._message_light = False

        else:
            logger.debug(f"Unhandled opcode: {opcode:#x}")

    def _parse_commands(self, data: bytes) -> None:
        """Parse 5250 commands within the data portion of a GDS record."""
        pos = 0
        while pos < len(data):
            if data[pos] == ESC:
                pos += 1
                if pos >= len(data):
                    break
                cmd = data[pos]
                pos += 1

                if cmd == CMD_WRITE_TO_DISPLAY:
                    consumed = parse_write_to_display(data[pos:], self._screen, self.codepage)
                    pos += consumed

                elif cmd == CMD_CLEAR_UNIT:
                    parse_clear(self._screen)

                elif cmd == CMD_CLEAR_FORMAT_TABLE:
                    self._screen.fields.clear()

                elif cmd == CMD_ROLL:
                    parse_roll(data[pos:], self._screen)
                    pos += 2

                elif cmd == CMD_WRITE_ERROR_CODE:
                    consumed = parse_write_to_display(data[pos:], self._screen, self.codepage)
                    pos += consumed

                elif cmd == CMD_WRITE_STRUCTURED_FIELD:
                    if pos + 2 < len(data):
                        sf_len = (data[pos] << 8) | data[pos + 1]
                        if pos + 2 < len(data) and data[pos + 2] == 0xD9:
                            self._pending_query = True
                        pos += max(sf_len, 1)
                    else:
                        while pos < len(data) and data[pos] != ESC:
                            pos += 1

                else:
                    logger.debug(f"Unknown command: {cmd:#x}")
            else:
                pos += 1

    async def _send_query_reply(self) -> None:
        reply_data = self._build_query_reply()
        frame = self._build_gds_frame(reply_data, opcode=OP_PUT_GET)
        await self._stream.write_frame(frame)

    def _build_query_reply(self) -> bytes:
        """Build a 5250 Query Reply for an IBM-3179-2 (24x80) terminal."""
        buf = bytearray()
        buf.append(self._screen.cursor_row + 1)
        buf.append(self._screen.cursor_col + 1)
        buf.append(0x88)  # Structured Field AID

        sf_data = bytearray(58)
        sf_data[0] = 0x00  # SF length high
        sf_data[1] = 0x3A  # SF length low (58)
        sf_data[2] = 0xD9  # SF type (Query Reply)
        sf_data[3] = 0x70  # SF class
        sf_data[4] = 0x80  # Flags: workstation is a display
        sf_data[5] = 0x06  # Flags
        sf_data[6] = 0x00  # Reserved
        sf_data[11] = 0x01  # Machine type: display
        sf_data[12] = 0x01  # Model: 24x80

        buf.extend(sf_data)
        return bytes(buf)

    def _build_gds_frame(self, data: bytes, opcode: int, flags: int = 0) -> bytes:
        """Build a GDS frame with header."""
        var_hdr_len = 4
        total_len = 10 + len(data)
        header = bytearray(10)
        header[0] = (total_len >> 8) & 0xFF
        header[1] = total_len & 0xFF
        header[2] = 0x12  # Record type high
        header[3] = 0xA0  # Record type low
        header[4] = 0x00  # Reserved
        header[5] = 0x00  # Reserved
        header[6] = var_hdr_len
        header[7] = flags
        header[8] = 0x00  # Reserved
        header[9] = opcode
        return bytes(header) + data
