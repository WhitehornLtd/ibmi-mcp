# ========================================================================
#   Copyright (c) 2026 Whitehorn Ltd. Co.
#   https://whitehorn.ltd
# ========================================================================

# Telnet protocol bytes
IAC = 0xFF
DONT = 0xFE
DO = 0xFD
WONT = 0xFC
WILL = 0xFB
SB = 0xFA
SE = 0xF0
EOR = 0xEF

# Telnet options
OPT_BINARY = 0x00
OPT_ECHO = 0x01
OPT_TERMINAL_TYPE = 0x18
OPT_END_OF_RECORD = 0x19
OPT_NEW_ENVIRON = 0x27

# Terminal type subnegotiation
TT_IS = 0x00
TT_SEND = 0x01

# New environment subnegotiation
NE_IS = 0x00
NE_SEND = 0x01
NE_INFO = 0x02
NE_VAR = 0x00
NE_VALUE = 0x01
NE_ESC = 0x02
NE_USERVAR = 0x03

# GDS header
GDS_RECORD_TYPE = 0x12A0

# GDS flags
GDS_FLAG_ERR = 0x02
GDS_FLAG_ATN = 0x40
GDS_FLAG_SRQ = 0x04

# 5250 opcodes (in GDS header)
OP_NO_OP = 0x00
OP_INVITE = 0x01
OP_OUTPUT_ONLY = 0x02
OP_PUT_GET = 0x03
OP_SAVE_SCREEN = 0x04
OP_RESTORE_SCREEN = 0x05
OP_READ_IMMEDIATE = 0x06
OP_READ_SCREEN = 0x08
OP_CANCEL_INVITE = 0x0A
OP_MSG_LIGHT_ON = 0x0B
OP_MSG_LIGHT_OFF = 0x0C

# 5250 escape byte
ESC = 0x04

# 5250 commands (after ESC)
CMD_CLEAR_UNIT = 0x40
CMD_CLEAR_FORMAT_TABLE = 0x50
CMD_WRITE_TO_DISPLAY = 0x11
CMD_WRITE_ERROR_CODE = 0x21
CMD_WRITE_ERROR_CODE_WINDOW = 0x22
CMD_READ_INPUT_FIELDS = 0x42
CMD_READ_MDT_FIELDS = 0x52
CMD_READ_IMMEDIATE = 0x72
CMD_ROLL = 0x23
CMD_WRITE_STRUCTURED_FIELD = 0xF3
CMD_SAVE_SCREEN = 0x02
CMD_RESTORE_SCREEN = 0x12

# 5250 orders (within WTD data)
ORDER_SBA = 0x11       # Set Buffer Address
ORDER_IC = 0x13        # Insert Cursor
ORDER_MC = 0x14        # Move Cursor
ORDER_RA = 0x02        # Repeat to Address
ORDER_EA = 0x03        # Erase to Address
ORDER_SOH = 0x01       # Start of Header
ORDER_TD = 0x10        # Transparent Data
ORDER_WEA = 0x12       # Write Extended Attribute
ORDER_SF = 0x1D        # Start of Field
ORDER_WDSF = 0x15      # Write to Display Structured Field

# AID codes (attention identifier)
AID_ENTER = 0xF1
AID_F1 = 0x31
AID_F2 = 0x32
AID_F3 = 0x33
AID_F4 = 0x34
AID_F5 = 0x35
AID_F6 = 0x36
AID_F7 = 0x37
AID_F8 = 0x38
AID_F9 = 0x39
AID_F10 = 0x3A
AID_F11 = 0x3B
AID_F12 = 0x3C
AID_F13 = 0xB1
AID_F14 = 0xB2
AID_F15 = 0xB3
AID_F16 = 0xB4
AID_F17 = 0xB5
AID_F18 = 0xB6
AID_F19 = 0xB7
AID_F20 = 0xB8
AID_F21 = 0xB9
AID_F22 = 0xBA
AID_F23 = 0xBB
AID_F24 = 0xBC
AID_CLEAR = 0xBD
AID_HELP = 0xF3
AID_PAGE_UP = 0xF4
AID_PAGE_DOWN = 0xF5
AID_PRINT = 0xF6
AID_RECORD_BACKSPACE = 0xF8
AID_AUTO_ENTER = 0x3F
AID_ATTN = 0x70  # special - sent as SRQ flag, not in data

# Map of friendly key names to AID codes
KEY_TO_AID: dict[str, int] = {
    "enter": AID_ENTER,
    "f1": AID_F1, "f2": AID_F2, "f3": AID_F3, "f4": AID_F4,
    "f5": AID_F5, "f6": AID_F6, "f7": AID_F7, "f8": AID_F8,
    "f9": AID_F9, "f10": AID_F10, "f11": AID_F11, "f12": AID_F12,
    "f13": AID_F13, "f14": AID_F14, "f15": AID_F15, "f16": AID_F16,
    "f17": AID_F17, "f18": AID_F18, "f19": AID_F19, "f20": AID_F20,
    "f21": AID_F21, "f22": AID_F22, "f23": AID_F23, "f24": AID_F24,
    "clear": AID_CLEAR,
    "help": AID_HELP,
    "pageup": AID_PAGE_UP, "page_up": AID_PAGE_UP, "pgup": AID_PAGE_UP,
    "pagedown": AID_PAGE_DOWN, "page_down": AID_PAGE_DOWN, "pgdn": AID_PAGE_DOWN,
    "print": AID_PRINT,
    "record_backspace": AID_RECORD_BACKSPACE,
}

# Field attribute bits (first attribute byte)
ATTR_DISPLAY_MASK = 0x07
ATTR_NON_DISPLAY = 0x07
ATTR_NORMAL = 0x00
ATTR_HIGH_INTENSITY = 0x02
ATTR_UNDERSCORE = 0x04

# Field Format Word 1 (FFW1) bits
FFW1_BYPASS = 0x20
FFW1_DUP_ENABLE = 0x10
FFW1_MDT = 0x08
FFW1_SHIFT_MASK = 0x07
FFW1_ALPHA_SHIFT = 0x00
FFW1_ALPHA_ONLY = 0x01
FFW1_NUMERIC_SHIFT = 0x02
FFW1_NUMERIC_ONLY = 0x03
FFW1_KATA = 0x04
FFW1_DIGITS_ONLY = 0x05
FFW1_IO_ONLY = 0x06
FFW1_SIGNED_NUMERIC = 0x07

# Field Format Word 2 (FFW2) bits
FFW2_AUTO_ENTER = 0x80
FFW2_FER = 0x40
FFW2_MONOCASE = 0x20
FFW2_MANDATORY_ENTRY = 0x08
FFW2_MANDATORY_FILL = 0x04

# Screen dimensions
ROWS_24x80 = 24
COLS_24x80 = 80
ROWS_27x132 = 27
COLS_27x132 = 132
