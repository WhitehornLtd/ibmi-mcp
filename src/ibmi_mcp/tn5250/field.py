# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

from pydantic import BaseModel

from ibmi_mcp.tn5250.constants import (
    FFW1_ALPHA_ONLY,
    FFW1_ALPHA_SHIFT,
    FFW1_BYPASS,
    FFW1_DIGITS_ONLY,
    FFW1_IO_ONLY,
    FFW1_KATA,
    FFW1_MDT,
    FFW1_NUMERIC_ONLY,
    FFW1_NUMERIC_SHIFT,
    FFW1_SHIFT_MASK,
    FFW1_SIGNED_NUMERIC,
)

SHIFT_NAMES = {
    FFW1_ALPHA_SHIFT: "alpha_shift",
    FFW1_ALPHA_ONLY: "alpha_only",
    FFW1_NUMERIC_SHIFT: "numeric_shift",
    FFW1_NUMERIC_ONLY: "numeric_only",
    FFW1_KATA: "katakana",
    FFW1_DIGITS_ONLY: "digits_only",
    FFW1_IO_ONLY: "io_only",
    FFW1_SIGNED_NUMERIC: "signed_numeric",
}


class ScreenField(BaseModel):
    row: int
    col: int
    length: int
    attr: int = 0
    ffw1: int = 0
    ffw2: int = 0
    fcw1: int = 0
    fcw2: int = 0
    modified: bool = False

    @property
    def is_bypass(self) -> bool:
        if not (self.ffw1 & 0x40):
            # No FFW present — output-only field
            return True
        return bool(self.ffw1 & FFW1_BYPASS)

    @property
    def is_input(self) -> bool:
        return not self.is_bypass

    @property
    def field_type(self) -> str:
        return SHIFT_NAMES.get(self.ffw1 & FFW1_SHIFT_MASK, "alpha_shift")

    def permits(self, char: str) -> bool:
        """Whether the field's keyboard shift allows this character to be keyed.

        A 5250 device refuses a disallowed character and inhibits the keyboard
        rather than transmitting it, so data the shift forbids can never reach
        the host from a real terminal.

        The sign of a signed-numeric field is not keyed into the field itself —
        it is set by a field-exit key — so only digits are accepted here.
        """
        shift = self.ffw1 & FFW1_SHIFT_MASK

        if shift in (FFW1_ALPHA_SHIFT, FFW1_NUMERIC_SHIFT, FFW1_KATA):
            return True
        if shift == FFW1_ALPHA_ONLY:
            return char.isalpha() or char in ",.- "
        if shift == FFW1_NUMERIC_ONLY:
            return char.isdigit() or char in ",.- "
        if shift in (FFW1_DIGITS_ONLY, FFW1_SIGNED_NUMERIC):
            return char.isdigit()
        # I/O-only fields are written by a device, never by the keyboard.
        return False

    def set_modified(self) -> None:
        self.modified = True
        self.ffw1 |= FFW1_MDT
