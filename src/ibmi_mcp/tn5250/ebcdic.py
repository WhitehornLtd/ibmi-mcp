# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

DEFAULT_CODEPAGE = "cp037"


def to_unicode(data: bytes, codepage: str = DEFAULT_CODEPAGE) -> str:
    return data.decode(codepage)


def to_ebcdic(text: str, codepage: str = DEFAULT_CODEPAGE) -> bytes:
    return text.encode(codepage)


def addr_to_row_col(addr: int, cols: int) -> tuple[int, int]:
    row = addr // cols
    col = addr % cols
    return row, col


def row_col_to_addr(row: int, col: int, cols: int) -> int:
    return row * cols + col
