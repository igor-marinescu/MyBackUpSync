"""A very small, dependency free, cross platform text terminal.

Only what MyBackUpSync needs: raw key reading (Windows and Linux), the
alternate screen buffer, and ANSI colour attributes.  Opening the terminal also
picks the drawing glyphs, see :mod:`mbs.symbols`.
"""

from __future__ import annotations

import os
import shutil
import sys

from . import symbols

WINDOWS = os.name == "nt"

if WINDOWS:                                              # pragma: no cover
    import msvcrt
else:                                                    # pragma: no cover
    import select
    import termios
    import tty


# -- key names ---------------------------------------------------------------
UP = "UP"
DOWN = "DOWN"
LEFT = "LEFT"
RIGHT = "RIGHT"
PGUP = "PGUP"
PGDN = "PGDN"
HOME = "HOME"
END = "END"
ENTER = "ENTER"
ESC = "ESC"
TAB = "TAB"
SPACE = "SPACE"
BACKSPACE = "BACKSPACE"
DELETE = "DELETE"

_WIN_SPECIAL = {
    "H": UP, "P": DOWN, "K": LEFT, "M": RIGHT,
    "I": PGUP, "Q": PGDN, "G": HOME, "O": END, "S": DELETE,
    ";": "F1", "<": "F2", "=": "F3", ">": "F4", "?": "F5",
    "@": "F6", "A": "F7", "B": "F8", "C": "F9", "D": "F10",
    "\x85": "F11", "\x86": "F12",
}

_ANSI_FINAL = {
    "A": UP, "B": DOWN, "C": RIGHT, "D": LEFT,
    "H": HOME, "F": END,
    "P": "F1", "Q": "F2", "R": "F3", "S": "F4",
}

_ANSI_TILDE = {
    "1": HOME, "2": "INSERT", "3": DELETE, "4": END, "5": PGUP, "6": PGDN,
    "7": HOME, "8": END,
    "11": "F1", "12": "F2", "13": "F3", "14": "F4", "15": "F5",
    "17": "F6", "18": "F7", "19": "F8", "20": "F9", "21": "F10",
    "23": "F11", "24": "F12",
}


# -- colours -----------------------------------------------------------------
class Color:
    RESET = "\x1b[0m"
    # Main pane: FAR like, light grey on blue.
    PANE = "\x1b[0;37;44m"
    PANE_DIM = "\x1b[0;36;44m"
    PANE_BRIGHT = "\x1b[1;37;44m"
    SELECTED = "\x1b[1;33;44m"          # marked with [X]
    CURSOR = "\x1b[0;30;46m"            # the cursor line
    CURSOR_SELECTED = "\x1b[1;33;46m"
    FRAME = "\x1b[0;36;44m"
    TITLE = "\x1b[1;30;46m"
    BOTTOM = "\x1b[0;37;40m"
    BOTTOM_KEY = "\x1b[1;37;40m"
    BOTTOM_NAME = "\x1b[0;30;46m"
    DIALOG = "\x1b[0;37;40m"
    DIALOG_FRAME = "\x1b[1;37;40m"
    DIALOG_BUTTON = "\x1b[0;37;40m"
    DIALOG_ACTIVE = "\x1b[1;30;47m"
    WARNING = "\x1b[1;31;44m"


class Terminal:
    """Raw terminal input plus alternate screen output."""

    def __init__(self, stream=None, ascii_only=False):
        self.stream = stream or sys.stdout
        self.ascii_only = ascii_only
        self._saved = None
        self._win_mode = None
        self.width = 80
        self.height = 25

    # -- setup ----------------------------------------------------------
    def _enable_windows_vt(self):                        # pragma: no cover
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            self._win_mode = mode.value
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)

    def _restore_windows_vt(self):                       # pragma: no cover
        if self._win_mode is None:
            return
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), self._win_mode)

    def _setup_encoding(self):
        """Make sure the box drawing glyphs can reach the terminal."""
        try:
            self.stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
        return symbols.select(self.ascii_only, self.stream)

    def open(self):
        self._setup_encoding()
        if WINDOWS:                                      # pragma: no cover
            self._enable_windows_vt()
        else:                                            # pragma: no cover
            self._saved = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        self.write("\x1b[?1049h\x1b[?25l")
        self.refresh_size()

    def close(self):
        self.write("\x1b[?25h\x1b[?1049l" + Color.RESET)
        self.flush()
        if WINDOWS:                                      # pragma: no cover
            self._restore_windows_vt()
        elif self._saved is not None:                    # pragma: no cover
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._saved)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    # -- output ---------------------------------------------------------
    def refresh_size(self):
        size = shutil.get_terminal_size((80, 25))
        self.width = max(40, size.columns)
        self.height = max(10, size.lines)
        return self.width, self.height

    def write(self, text):
        self.stream.write(text)

    def flush(self):
        self.stream.flush()

    def draw(self, lines):
        """Paint the whole screen at once from a list of ready made lines."""
        out = ["\x1b[H"]
        for index, line in enumerate(lines):
            out.append("\x1b[%d;1H" % (index + 1))
            out.append("\x1b[K")
            out.append(line)
        out.append(Color.RESET)
        self.write("".join(out))
        self.flush()

    # -- input ----------------------------------------------------------
    if WINDOWS:                                          # pragma: no cover
        def read_key(self):
            char = msvcrt.getwch()
            if char in ("\x00", "\xe0"):
                return _WIN_SPECIAL.get(msvcrt.getwch(), "")
            return self._plain(char)
    else:                                                # pragma: no cover
        def read_key(self):
            char = sys.stdin.read(1)
            if char != "\x1b":
                return self._plain(char)
            sequence = ""
            while True:
                ready, _, _ = select.select([sys.stdin], [], [], 0.06)
                if not ready:
                    break
                sequence += sys.stdin.read(1)
                if len(sequence) == 1 and sequence not in ("[", "O"):
                    break
                if len(sequence) > 1 and (sequence[-1].isalpha()
                                          or sequence[-1] == "~"):
                    break
                if len(sequence) > 10:
                    break
            return self._escape(sequence)

    @staticmethod
    def _plain(char):
        if char in ("\r", "\n"):
            return ENTER
        if char == "\t":
            return TAB
        if char == " ":
            return SPACE
        if char in ("\x08", "\x7f"):
            return BACKSPACE
        if char == "\x1b":
            return ESC
        if char == "\x03":
            return "CTRL-C"
        return char

    @staticmethod
    def _escape(sequence):
        if not sequence:
            return ESC
        body = sequence[1:]
        final = sequence[-1]
        if final == "~":
            return _ANSI_TILDE.get(body[:-1].split(";")[0], "")
        if sequence[0] in ("[", "O"):
            # Strip any modifier parameters, keep the final letter.
            return _ANSI_FINAL.get(final, "")
        return ""
