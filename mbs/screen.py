"""A tiny character/colour screen buffer.

Working on a buffer (instead of writing escape sequences straight away) keeps
the drawing code simple and makes it possible to paint dialogs on top of the
Main Pane without having to care about the colours underneath.
"""

from __future__ import annotations

from . import symbols
from .terminal import Color


class Screen:
    """A rectangular grid of characters, each one with its own colour."""

    def __init__(self, width, height, color=Color.PANE, fill=" "):
        self.width = width
        self.height = height
        self.chars = [[fill] * width for _ in range(height)]
        self.colors = [[color] * width for _ in range(height)]

    def put(self, row, col, text, color):
        """Write ``text`` at (row, col), clipped to the screen."""
        if row < 0 or row >= self.height or not text:
            return
        chars = self.chars[row]
        colors = self.colors[row]
        for offset, char in enumerate(text):
            position = col + offset
            if position < 0:
                continue
            if position >= self.width:
                break
            chars[position] = char
            colors[position] = color

    def fill(self, row, col, width, height, color, char=" "):
        for line in range(row, min(row + height, self.height)):
            self.put(line, col, char * width, color)

    def frame(self, row, col, width, height, color, title="", footer="",
              double=False):
        """Draw a box, optionally with a caption on its borders.

        ``double`` selects the double line glyphs that FAR uses for its
        dialogs; the single line ones are used for the panels.
        """
        glyphs = symbols.S
        if double:
            horizontal, vertical = glyphs.DH, glyphs.DV
            corners = (glyphs.DTL, glyphs.DTR, glyphs.DBL, glyphs.DBR)
        else:
            horizontal, vertical = glyphs.H, glyphs.V
            corners = (glyphs.TL, glyphs.TR, glyphs.BL, glyphs.BR)
        bar = horizontal * (width - 2)
        self.put(row, col, corners[0] + bar + corners[1], color)
        for line in range(row + 1, row + height - 1):
            self.put(line, col, vertical, color)
            self.put(line, col + width - 1, vertical, color)
        self.put(row + height - 1, col, corners[2] + bar + corners[3], color)
        if title:
            text = " " + title[:width - 6] + " "
            self.put(row, col + 2, text, color)
        if footer:
            text = " " + footer[:width - 6] + " "
            self.put(row + height - 1, col + 2, text, color)

    def lines(self, trim_last=True):
        """Encode the buffer into one ANSI string per row.

        The very last cell of the screen is left untouched by default: writing
        it makes several terminals scroll the whole picture up by one line.
        """
        result = []
        for row in range(self.height):
            last_row = trim_last and row == self.height - 1
            width = self.width - 1 if last_row else self.width
            chars = self.chars[row]
            colors = self.colors[row]
            parts = []
            current = None
            run = []
            for index in range(width):
                if colors[index] != current:
                    if run:
                        parts.append(current + "".join(run))
                    current = colors[index]
                    run = []
                run.append(chars[index])
            if run:
                parts.append(current + "".join(run))
            result.append("".join(parts) + Color.RESET)
        return result
