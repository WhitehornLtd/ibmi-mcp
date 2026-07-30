# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

from ibmi_mcp.tn5250.constants import COLS_24x80, ROWS_24x80
from ibmi_mcp.tn5250.field import ScreenField


def _function_key_number(aid: int) -> int | None:
    """The function-key number an AID code stands for, or None if it is not one.

    Only the 24 function keys carry a command-key switch; Enter and the rest
    always transmit.
    """
    if 0x31 <= aid <= 0x3C:      # F1-F12
        return aid - 0x30
    if 0xB1 <= aid <= 0xBC:      # F13-F24
        return aid - 0xB0 + 12
    return None


class ScreenBuffer:
    def __init__(self, rows: int = ROWS_24x80, cols: int = COLS_24x80):
        self.rows = rows
        self.cols = cols
        self.size = rows * cols
        self.buffer: list[str] = [" "] * self.size
        self.attrs: list[int] = [0] * self.size
        self.fields: list[ScreenField] = []
        self.modified_positions: set[int] = set()
        self.cursor_row = 0
        self.cursor_col = 0
        # Start of Header data. Bytes 4-6 hold the command-key switch mask that
        # says which keys must not transmit field data.
        self.header_data: bytes = b""

    def clear(self) -> None:
        self.buffer = [" "] * self.size
        self.attrs = [0] * self.size
        self.fields.clear()
        self.modified_positions.clear()
        self.cursor_row = 0
        self.cursor_col = 0
        self.header_data = b""

    def sends_data_for_aid(self, aid: int) -> bool:
        """Whether a device would transmit field data for this AID key.

        Command-attention keys are marked by a set bit in the SOH command-key
        switch mask: F1-F8 in header byte 6, F9-F16 in byte 5, F17-F24 in byte
        4, least-significant bit first within each group. A header too short to
        hold the mask means every key transmits.
        """
        if len(self.header_data) <= 6:
            return True

        key = _function_key_number(aid)
        if key is None:
            return True

        group, offset = divmod(key - 1, 8)
        return (self.header_data[6 - group] & (1 << offset)) == 0

    def set_char(self, pos: int, char: str, attr: int = 0) -> None:
        if 0 <= pos < self.size:
            self.buffer[pos] = char
            if attr:
                self.attrs[pos] = attr

    def get_char(self, pos: int) -> str:
        if 0 <= pos < self.size:
            return self.buffer[pos]
        return " "

    def set_cursor(self, row: int, col: int) -> None:
        self.cursor_row = max(0, min(row, self.rows - 1))
        self.cursor_col = max(0, min(col, self.cols - 1))

    def cursor_pos(self) -> int:
        return self.cursor_row * self.cols + self.cursor_col

    def add_field(self, field: ScreenField) -> None:
        self.fields.append(field)

    def get_field_at(self, row: int, col: int) -> ScreenField | None:
        for f in self.fields:
            if f.row == row and f.col == col:
                return f
        return None

    def get_field_at_cursor(self) -> ScreenField | None:
        for f in self.fields:
            start = f.row * self.cols + f.col
            end = start + f.length
            cursor = self.cursor_pos()
            if start <= cursor < end:
                return f
        return None

    def get_input_fields(self) -> list[ScreenField]:
        return [f for f in self.fields if f.is_input]

    def get_field_value(self, field: ScreenField) -> str:
        start = field.row * self.cols + field.col
        end = start + field.length
        return "".join(self.buffer[start:end])

    def set_field_value(self, field: ScreenField, value: str) -> None:
        start = field.row * self.cols + field.col
        for i, ch in enumerate(value):
            if i >= field.length:
                break
            self.buffer[start + i] = ch
        for i in range(len(value), field.length):
            self.buffer[start + i] = " "
        field.set_modified()

    def get_text_rows(self) -> list[str]:
        rows = []
        for r in range(self.rows):
            start = r * self.cols
            end = start + self.cols
            rows.append("".join(self.buffer[start:end]))
        return rows

    def get_screen_data(self) -> dict:
        input_fields = []
        for f in self.fields:
            if f.is_input:
                input_fields.append({
                    "row": f.row + 1,
                    "col": f.col + 1,
                    "length": f.length,
                    "value": self.get_field_value(f).rstrip(),
                    "field_type": f.field_type,
                })
        return {
            "screen": self.get_text_rows(),
            "cursor": {"row": self.cursor_row + 1, "col": self.cursor_col + 1},
            "fields": input_fields,
            "dimensions": {"rows": self.rows, "cols": self.cols},
        }
