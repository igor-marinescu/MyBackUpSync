"""The FAR like text mode user interface of MyBackUpSync."""

from __future__ import annotations

import os
import tempfile
import time

from . import __version__, actions, model, scanner, symbols, terminal
from .screen import Screen
from .terminal import Color, Terminal

#: The 'F9' label follows the state of the tree, see App._bottom_keys().
#: The names are kept FAR short ('RefrDir') so that the whole bar still fits
#: on an 80 column terminal.
BOTTOM_KEYS = (
    ("F1", "Refresh"),
    ("F2", "RefrDir"),
    ("F4", "List"),
    ("F5", "Copy"),
    ("F8", "Delete"),
    ("F9", "Collapse All"),
    ("F10", "Quit"),
)

HINTS = ("Enter:open/close  Space:mark  Tab:direction  "
         "Left/BkSp:parent  Home/End")

LIST_MIN_WIDTH = 100      # minimum width used for the F4 text file

KEEP_HEAD = 12            # characters of an elided line kept on the left


def _elide(text, width):
    """Shorten a long line while keeping its beginning and its end.

    Operation lines start with the action ('COPY  C->B') and end with the file
    name, so both ends have to survive.
    """
    if len(text) <= width or width < KEEP_HEAD + 6:
        return text[:width]
    tail = width - KEEP_HEAD - 3
    return text[:KEEP_HEAD] + "..." + text[-tail:]


class App:
    """Owns the difference tree, the screen and the key loop."""

    def __init__(self, backup_root, config_path, entries, check_dir_times=False,
                 ascii_only=False, ignore_date_time=False):
        self.backup_root = backup_root
        self.config_path = config_path
        self.entries = entries
        self.check_dir_times = check_dir_times
        self.ignore_date_time = ignore_date_time

        self.term = Terminal(ascii_only=ascii_only)
        self.roots = []
        self.rows = []            # list of (node, tree prefix)
        self.cursor = 0
        self.top = 0
        self.status = ""
        self.warnings = []

    # ------------------------------------------------------------------
    # data
    # ------------------------------------------------------------------
    def rescan(self, keep_position=True):
        """Re-read both drives and rebuild the list of differences."""
        marked = self._current_path() if keep_position else None
        opened = model.expanded_paths(self.roots) if keep_position else set()
        self.roots, self.warnings = scanner.scan(self.entries,
                                                 self.check_dir_times,
                                                 self.ignore_date_time)
        model.restore_expanded(self.roots, opened)
        self.rebuild()
        self.cursor = 0
        if marked:
            for index, (node, _) in enumerate(self.rows):
                if (node.src, node.dst) == marked:
                    self.cursor = index
                    break
        self._clamp()

    def rebuild(self):
        """Recompute the visible lines after an expand/collapse."""
        self.rows = model.flatten(self.roots)

    def _current_path(self):
        node = self.current_node()
        return (node.src, node.dst) if node is not None else None

    def _focus(self, node):
        """Put the cursor back on ``node`` after the list has been rebuilt."""
        if node is not None:
            for index, (candidate, _) in enumerate(self.rows):
                if candidate is node:
                    self.cursor = index
                    break
        self._clamp()

    def current_node(self):
        if not self.rows:
            return None
        return self.rows[self.cursor][0]

    def _clamp(self):
        if not self.rows:
            self.cursor = 0
            self.top = 0
            return
        self.cursor = max(0, min(self.cursor, len(self.rows) - 1))
        view = self.view_height
        if self.cursor < self.top:
            self.top = self.cursor
        if self.cursor >= self.top + view:
            self.top = self.cursor - view + 1
        self.top = max(0, min(self.top, max(0, len(self.rows) - view)))

    @property
    def view_height(self):
        return max(1, self.term.height - 4)

    @property
    def text_width(self):
        return max(10, self.term.width - 3)

    # ------------------------------------------------------------------
    # drawing
    # ------------------------------------------------------------------
    def _base_screen(self):
        width, height = self.term.width, self.term.height
        screen = Screen(width, height, Color.PANE)

        # --- title -----------------------------------------------------
        total = model.count_differences(self.roots)
        marked = sum(1 for root in self.roots for node in root.walk()
                     if node.selected and not node.is_root)
        title = " MyBackUpSync %s   backup: %s   differences: %d   marked: %d " % (
            __version__, self.backup_root, total, marked)
        screen.put(0, 0, " " * width, Color.TITLE)
        screen.put(0, 0, title[:width], Color.TITLE)

        # --- main pane frame -------------------------------------------
        # rows: 0 title, 1 top border, 2..height-3 content,
        #       height-2 bottom border, height-1 bottom pane.
        body_height = height - 2
        screen.fill(1, 0, width, body_height, Color.PANE)
        screen.frame(1, 0, width, body_height, Color.FRAME,
                     title=HINTS, footer=self._footer())

        # --- content ---------------------------------------------------
        view = self.view_height
        if not self.rows:
            text = ("No differences found - both drives are synchronised."
                    if not self.warnings else
                    "No differences found (see the warnings below).")
            screen.put(2 + view // 2, max(1, (width - len(text)) // 2),
                       text, Color.PANE_BRIGHT)
        else:
            for offset in range(view):
                index = self.top + offset
                if index >= len(self.rows):
                    break
                node, prefix = self.rows[index]
                text = model.render_line(node, prefix, self.text_width)
                if index == self.cursor:
                    color = (Color.CURSOR_SELECTED if node.selected
                             else Color.CURSOR)
                elif node.selected:
                    color = Color.SELECTED
                elif node.is_root:
                    color = Color.PANE_BRIGHT
                else:
                    color = Color.PANE
                screen.put(2 + offset, 1, text, color)
            self._draw_scrollbar(screen, view)

        # --- bottom pane -----------------------------------------------
        self._draw_bottom(screen, height - 1, width)
        return screen

    def _footer(self):
        if self.status:
            return self.status[:self.term.width - 8]
        node = self.current_node()
        if node is None:
            return "%d/%d" % (0, 0)
        path = node.src if node.src_exists else node.dst
        room = self.term.width - 20
        if len(path) > room > 4:
            path = "..." + path[-(room - 3):]
        return "%s   [%d/%d]" % (path, self.cursor + 1, len(self.rows))

    def _draw_scrollbar(self, screen, view):
        """FAR like scroll box: the arrows, the track and the thumb."""
        glyphs = symbols.S
        column = self.term.width - 2
        total = len(self.rows)
        screen.put(2, column, glyphs.SB_UP, Color.FRAME)
        screen.put(2 + view - 1, column, glyphs.SB_DOWN, Color.FRAME)
        track = view - 2
        if track < 1:
            return
        if total <= view:
            for offset in range(track):
                screen.put(3 + offset, column, glyphs.SB_THUMB, Color.PANE_BRIGHT)
            return
        size = max(1, int(track * view / float(total)))
        start = int(round(self.top * (track - size) / float(total - view)))
        for offset in range(track):
            inside = start <= offset < start + size
            screen.put(3 + offset, column,
                       glyphs.SB_THUMB if inside else glyphs.SB_TRACK,
                       Color.PANE_BRIGHT if inside else Color.FRAME)

    def _bottom_keys(self):
        """The commands, with the F9 label following the state of the tree."""
        expanded = model.any_expanded(self.roots)
        return tuple((key, "Collapse All" if expanded else "Expand All")
                     if key == "F9" else (key, name)
                     for key, name in BOTTOM_KEYS)

    def _draw_bottom(self, screen, row, width):
        screen.put(row, 0, " " * width, Color.BOTTOM)
        column = 0
        for key, name in self._bottom_keys():
            if column >= width:
                break
            screen.put(row, column, "[", Color.BOTTOM)
            column += 1
            screen.put(row, column, key, Color.BOTTOM_KEY)
            column += len(key)
            screen.put(row, column, " " + name, Color.BOTTOM_NAME)
            column += len(name) + 1
            screen.put(row, column, "]", Color.BOTTOM)
            column += 1

    def draw(self):
        self.term.refresh_size()
        self._clamp()
        self._paint(self._base_screen())

    def _paint(self, screen):
        self.term.draw(screen.lines())

    # ------------------------------------------------------------------
    # dialogs
    # ------------------------------------------------------------------
    def _dialog_box(self, screen, title, body, buttons, active, top):
        width = self.term.width
        height = self.term.height
        longest = max([len(title)] + [len(line) for line in body] + [20])
        box_width = min(width - 4, max(40, longest + 6))
        room = height - 8
        shown = min(len(body), max(1, room))
        box_height = shown + 6
        box_row = max(1, (height - box_height) // 2)
        box_col = max(0, (width - box_width) // 2)

        screen.fill(box_row, box_col, box_width, box_height, Color.DIALOG)
        footer = ""
        if len(body) > shown:
            footer = "%d-%d of %d" % (top + 1, top + shown, len(body))
        screen.frame(box_row, box_col, box_width, box_height,
                     Color.DIALOG_FRAME, title=title, footer=footer, double=True)

        for offset in range(shown):
            index = top + offset
            if index >= len(body):
                break
            screen.put(box_row + 1 + offset, box_col + 2,
                       _elide(body[index], box_width - 4), Color.DIALOG)

        button_row = box_row + box_height - 3
        labels = ["[ %s ]" % text for text in buttons]
        total = sum(len(label) for label in labels) + 2 * (len(labels) - 1)
        column = box_col + max(2, (box_width - total) // 2)
        for index, label in enumerate(labels):
            color = Color.DIALOG_ACTIVE if index == active else Color.DIALOG_BUTTON
            screen.put(button_row, column, label, color)
            column += len(label) + 2
        return shown

    def _run_dialog(self, title, body, buttons, default=0):
        """Modal list + buttons; returns the index of the chosen button."""
        active = default
        top = 0
        while True:
            self.term.refresh_size()
            screen = self._base_screen()
            shown = self._dialog_box(screen, title, body, buttons, active, top)
            self._paint(screen)

            key = self.term.read_key()
            if key in (terminal.LEFT, terminal.UP):
                if key == terminal.UP and len(body) > shown:
                    top = max(0, top - 1)
                else:
                    active = (active - 1) % len(buttons)
            elif key in (terminal.RIGHT, terminal.DOWN):
                if key == terminal.DOWN and len(body) > shown:
                    top = min(max(0, len(body) - shown), top + 1)
                else:
                    active = (active + 1) % len(buttons)
            elif key == terminal.TAB:
                active = (active + 1) % len(buttons)
            elif key == terminal.PGUP:
                top = max(0, top - shown)
            elif key == terminal.PGDN:
                top = min(max(0, len(body) - shown), top + shown)
            elif key == terminal.HOME:
                top = 0
            elif key == terminal.END:
                top = max(0, len(body) - shown)
            elif key == terminal.ENTER:
                return active
            elif key == terminal.ESC:
                return len(buttons) - 1
            elif key in ("o", "O"):
                return 0
            elif key in ("c", "C", "q", "Q"):
                return len(buttons) - 1

    def confirm(self, title, body):
        return self._run_dialog(title, body, ("Ok", "Cancel"), default=0) == 0

    def message(self, title, body):
        self._run_dialog(title, body, ("Ok",), default=0)

    def progress(self, title, done, total, text):
        screen = self._base_screen()
        width = min(self.term.width - 4, 70)
        height = 7
        row = max(1, (self.term.height - height) // 2)
        col = max(0, (self.term.width - width) // 2)
        screen.fill(row, col, width, height, Color.DIALOG)
        screen.frame(row, col, width, height, Color.DIALOG_FRAME, title=title,
                     double=True)
        percent = int(100 * done / total) if total else 100
        bar_width = width - 6
        filled = int(bar_width * percent / 100)
        screen.put(row + 1, col + 2, ("%d/%d  %d%%" % (done, total, percent)),
                   Color.DIALOG)
        screen.put(row + 2, col + 2,
                   symbols.S.BAR_FULL * filled
                   + symbols.S.BAR_EMPTY * (bar_width - filled), Color.DIALOG)
        screen.put(row + 4, col + 2, text[:width - 4], Color.DIALOG)
        self._paint(screen)

    # ------------------------------------------------------------------
    # commands
    # ------------------------------------------------------------------
    def _targets(self):
        """The nodes an action applies to: the marked ones, or the cursor."""
        marked = actions.selected_nodes(self.roots)
        if marked:
            return marked, True
        node = self.current_node()
        if node is None or node.is_root:
            return ([] if node is None else [node]), False
        return [node], False

    def _run_plan(self, plan, title, verb):
        if not plan:
            self.status = "Nothing to %s." % verb
            return
        body = [operation.describe() for operation in plan]
        header = ["%d operation(s):" % len(plan), ""]
        if not self.confirm(title, header + body):
            self.status = "%s aborted." % verb.capitalize()
            return

        state = {"last": -1}

        def report(done, total, text):
            step = max(1, total // 200)
            if done - state["last"] >= step or done >= total:
                state["last"] = done
                self.progress(title, done, total, text)

        errors = actions.execute(plan, report)
        actions.clear_selection(self.roots)
        self.rescan()
        if errors:
            self.message("Finished with %d problem(s)" % len(errors), errors)
            self.status = "%s finished, %d problem(s)." % (verb.capitalize(),
                                                           len(errors))
        else:
            self.status = "%s finished: %d operation(s)." % (verb.capitalize(),
                                                             len(plan))

    def do_copy(self):
        nodes, _ = self._targets()
        if not nodes:
            self.status = "Nothing selected."
            return
        self._run_plan(actions.build_copy_plan(nodes), "Copy", "copy")

    def do_delete(self):
        nodes, _ = self._targets()
        if not nodes:
            self.status = "Nothing selected."
            return
        self._run_plan(actions.build_delete_plan(nodes), "Delete", "delete")

    def do_list(self):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(tempfile.gettempdir(),
                            "mybackupsync_%s.txt" % stamp)
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("MyBackUpSync %s - list of differences\n" % __version__)
                handle.write("date          : %s\n"
                             % time.strftime("%Y-%m-%d %H:%M:%S"))
                handle.write("backup drive  : %s\n" % self.backup_root)
                handle.write("configuration : %s\n" % self.config_path)
                handle.write("differences   : %d\n\n"
                             % model.count_differences(self.roots))
                rows = model.flatten(self.roots, visible_only=False)
                width = model.list_width(rows, LIST_MIN_WIDTH)
                for node, prefix in rows:
                    handle.write(model.render_line(node, prefix,
                                                   width).rstrip() + "\n")
                for warning in self.warnings:
                    handle.write("\n! %s" % warning)
                handle.write("\n")
        except OSError as exc:
            self.message("List", ["Cannot write the list file:", str(exc)])
            return
        self.message("List", ["The list of differences has been saved to:", "",
                              path])
        self.status = "List saved to %s" % path

    def do_rescan_dir(self):
        """F2: re-read both drives for the directory under the cursor only.

        The rest of the list is left untouched, which makes it cheap to check
        one directory again after having worked on it outside MyBackUpSync.
        When the cursor sits on a file, its parent directory is re-read.
        """
        node = self.current_node()
        if node is None:
            return
        target = node if node.is_dir else node.parent
        if target is None:
            self.status = "This entry has no directory to refresh."
            return

        owner = target
        while owner.parent is not None:
            owner = owner.parent
        label = target.display_name

        state = model.subtree_state(target)
        fresh, warnings = scanner.rescan_node(target, self.check_dir_times,
                                              self.ignore_date_time)
        for warning in warnings:
            if warning not in self.warnings:
                self.warnings.append(warning)
        if fresh is not None:
            model.restore_subtree_state(fresh, state)

        parent = target.parent
        if parent is None:                          # a configured root line
            index = self.roots.index(target)
            if fresh is None:
                del self.roots[index]
                kept = None
            else:
                self.roots[index] = fresh
                kept = fresh
        else:
            index = parent.children.index(target)
            if fresh is None:
                del parent.children[index]
                kept = model.prune(parent)
            else:
                fresh.parent = parent
                parent.children[index] = fresh
                kept = fresh
            if kept is None and owner in self.roots:
                self.roots.remove(owner)

        ancestor = kept.parent if kept is not None else None
        while ancestor is not None:
            ancestor.refresh_direction()
            ancestor = ancestor.parent

        self.rebuild()
        self._focus(kept)
        self.status = ("'%s' is synchronised." % label if fresh is None
                       else "'%s' refreshed." % label)

    def do_toggle(self):
        node = self.current_node()
        if node is None:
            return
        node.set_selected(not node.selected)

    def do_open(self):
        """Enter: show or hide the content of the directory under the cursor."""
        node = self.current_node()
        if node is None:
            return
        if not node.toggle():
            self.status = "This entry has no content to show."
            return
        self.rebuild()
        for index, (candidate, _) in enumerate(self.rows):
            if candidate is node:
                self.cursor = index
                break

    def do_open_all(self):
        """F9: hide, or show, the content of every directory at once."""
        collapse = model.any_expanded(self.roots)
        node = self.current_node()
        model.expand_all(self.roots, not collapse)
        self.rebuild()
        self.cursor = 0
        for index, (candidate, _) in enumerate(self.rows):
            if candidate is node:
                self.cursor = index
                break
        self.status = ("All directories collapsed." if collapse
                       else "All directories expanded.")

    def do_flip(self):
        node = self.current_node()
        if node is None or node.is_root:
            return
        if not node.flip():
            self.status = "The direction of this entry cannot be changed."
            return
        parent = node.parent
        while parent is not None:
            parent.refresh_direction()
            parent = parent.parent
        self.status = ""

    def go_parent(self):
        node = self.current_node()
        if node is None or node.parent is None:
            return
        parent = node.parent
        for index, (candidate, _) in enumerate(self.rows):
            if candidate is parent:
                self.cursor = index
                return

    # ------------------------------------------------------------------
    # main loop
    # ------------------------------------------------------------------
    def run(self):
        with self.term:
            self.rescan(keep_position=False)
            if self.warnings:
                self.status = "%d warning(s) - see F4 List." % len(self.warnings)
            while True:
                self.draw()
                key = self.term.read_key()
                if key in ("F10", "q", "Q", "CTRL-C"):
                    if self.confirm("Quit", ["Leave MyBackUpSync?"]):
                        return 0
                    continue
                self.status = ""
                if key == terminal.UP:
                    self.cursor -= 1
                elif key == terminal.DOWN:
                    self.cursor += 1
                elif key == terminal.PGUP:
                    self.cursor -= self.view_height
                elif key == terminal.PGDN:
                    self.cursor += self.view_height
                elif key == terminal.HOME:
                    self.cursor = 0
                elif key == terminal.END:
                    self.cursor = len(self.rows) - 1
                elif key in (terminal.LEFT, terminal.BACKSPACE):
                    self.go_parent()
                elif key == terminal.SPACE:
                    self.do_toggle()
                elif key == terminal.TAB:
                    self.do_flip()
                elif key == terminal.ENTER:
                    self.do_open()
                elif key == "F1":
                    self.rescan()
                    self.status = "List of differences refreshed."
                elif key == "F2":
                    self.do_rescan_dir()
                elif key == "F4":
                    self.do_list()
                elif key == "F5":
                    self.do_copy()
                elif key == "F8":
                    self.do_delete()
                elif key == "F9":
                    self.do_open_all()
