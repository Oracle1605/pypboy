"""Lightweight replacement for the ``pygcurse`` package.

This module implements just enough of the public interface used by the
Pypboy project so that the real dependency can be removed entirely.  It
renders characters onto a supplied ``pygame.Surface`` using the same font
that the real ``pygcurse`` would use.  The API exposed is intentionally
minimal and only covers the functions called by ``holotape_processor`` and
``passcode``.

The original project used ``pygcurse`` to obtain a terminal-like text
surface; this implementation mimics its behaviour on top of pygame so the
rest of the code need not change.
"""

import pygame


class PygcurseSurface:
    def __init__(
        self,
        cols,
        rows,
        font,
        fgcolor=None,
        bgcolor=None,
        windowSurface=None,
        autoupdate=True,
        autodisplayupdate=1,
    ):
        # basic configuration
        self.cols = cols
        self.rows = rows
        self.font = font
        self.fgcolor = fgcolor if fgcolor is not None else (255, 255, 255)
        self.bgcolor = bgcolor if bgcolor is not None else (0, 0, 0)
        self.windowSurface = windowSurface or pygame.Surface(
            (cols * font.size("X")[0], rows * font.size("X")[1])
        )
        self.surface = self.windowSurface
        self.char_width, self.char_height = font.size("X")

        # character grid stored as list of lists of single characters
        self._chars = [[" "] * cols for _ in range(rows)]

        # cursor state
        self.cursorx = 0
        self.cursory = 0
        self.cursor = (0, 0)

        # attributes used by callers
        self._autoupdate = autoupdate
        self._autodisplayupdate = autodisplayupdate

    # cursor helpers -------------------------------------------------------
    def pushcursor(self):
        # real pygcurse stores a stack; our stub does nothing because
        # nothing in the code relies on popping the cursor back.
        pass

    # drawing primitives --------------------------------------------------
    def write(self, text, x=None, y=None):
        """Write a string starting at the current cursor or explicit coords."""
        if x is not None and y is not None:
            self.cursorx = x
            self.cursory = y
        for ch in str(text):
            if ch == "\n":
                self.cursorx = 0
                self.cursory += 1
                continue
            if 0 <= self.cursorx < self.cols and 0 <= self.cursory < self.rows:
                self._chars[self.cursory][self.cursorx] = ch
                self._render_char(ch, self.cursorx, self.cursory)
            self.cursorx += 1
            if self.cursorx >= self.cols:
                self.cursorx = 0
                self.cursory += 1

    def putchar(self, ch, x, y):
        if 0 <= y < self.rows and 0 <= x < self.cols:
            self._chars[y][x] = ch
            self._render_char(ch, x, y)

    def erase(self, rect):
        x, y, w, h = rect
        for j in range(y, y + h):
            for i in range(x, x + w):
                if 0 <= i < self.cols and 0 <= j < self.rows:
                    self._chars[j][i] = " "
                    self._render_char(" ", i, j)

    def getchars(self, rect):
        x, y, w, h = rect
        out = []
        for j in range(y, y + h):
            row = "".join(self._chars[j][x : x + w])
            out.append(row)
        return out

    # rendering -----------------------------------------------------------
    def _render_char(self, ch, x, y):
        if self.windowSurface is None:
            return
        rect = pygame.Rect(
            x * self.char_width,
            y * self.char_height,
            self.char_width,
            self.char_height,
        )
        self.windowSurface.fill(self.bgcolor, rect)
        if ch != " ":
            text_surf = self.font.render(ch, True, self.fgcolor)
            self.windowSurface.blit(text_surf, (x * self.char_width, y * self.char_height))

    # compatibility stubs -------------------------------------------------
    def update(self, *args, **kwargs):
        # noop; caller will blit the underlying surface themselves
        pass

    def sendToScreen(self, *args, **kwargs):
        pass


# mimic the old module-level names so "from pygcurse import PygcurseSurface" still works
PygcurseSurface = PygcurseSurface
