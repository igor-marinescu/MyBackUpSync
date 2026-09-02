"""The glyphs used to draw the user interface.

The default set uses the Unicode box drawing and block elements
(U+2500..U+259F) that the FAR file manager keeps in its own BOX_DEF_SYMBOLS
table.  A plain ASCII set is kept as a fall back for terminals (or redirected
output) that cannot encode them; see :func:`select`.
"""

from __future__ import annotations

# Every glyph that has to be encodable for the Unicode set to be usable.
PROBE = "─│┌┐└┘├┤═║" \
        "╔╗╚╝░▒█▲▼"


class SymbolSet:
    """One complete set of drawing characters."""

    def __init__(self, name, **glyphs):
        self.name = name
        self.__dict__.update(glyphs)


#: FAR like glyphs: single line frames, double line dialogs, block scrollbar.
UNICODE = SymbolSet(
    "unicode",
    # single line frame - Main Pane
    H="─", V="│",
    TL="┌", TR="┐", BL="└", BR="┘",
    LT="├", RT="┤", TT="┬", BT="┴",
    # double line frame - dialogs
    DH="═", DV="║",
    DTL="╔", DTR="╗", DBL="╚", DBR="╝",
    # tree drawing, three characters per level
    TREE_BRANCH=" ├─",     # a child with siblings below it
    TREE_LAST=" └─",       # the last child
    TREE_PIPE=" │ ",            # a parent that still has siblings
    TREE_BLANK="   ",
    # scroll box
    SB_UP="▲", SB_DOWN="▼",
    SB_TRACK="░", SB_THUMB="█",
    # progress bar
    BAR_FULL="█", BAR_EMPTY="░",
    # collapsed / expanded directory
    COLLAPSED="+", EXPANDED="-", LEAF=" ",
)

#: Plain 7 bit fall back, used when the Unicode glyphs cannot be written.
ASCII = SymbolSet(
    "ascii",
    H="-", V="|",
    TL="+", TR="+", BL="+", BR="+",
    LT="+", RT="+", TT="+", BT="+",
    DH="=", DV="|",
    DTL="+", DTR="+", DBL="+", DBR="+",
    TREE_BRANCH=" |-",
    TREE_LAST=" +-",
    TREE_PIPE=" | ",
    TREE_BLANK="   ",
    SB_UP="^", SB_DOWN="v",
    SB_TRACK="|", SB_THUMB="#",
    BAR_FULL="#", BAR_EMPTY=".",
    COLLAPSED="+", EXPANDED="-", LEAF=" ",
)

#: The set currently in use; always read it as ``symbols.S``.
S = UNICODE


def supported(stream):
    """True when ``stream`` is able to encode the Unicode glyphs."""
    encoding = getattr(stream, "encoding", None)
    if not encoding:
        return False
    try:
        PROBE.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def select(ascii_only=False, stream=None):
    """Choose the symbol set and return it.

    ``ascii_only`` forces the plain set; otherwise the Unicode set is used as
    soon as ``stream`` can encode it.
    """
    global S
    if ascii_only or (stream is not None and not supported(stream)):
        S = ASCII
    else:
        S = UNICODE
    return S
