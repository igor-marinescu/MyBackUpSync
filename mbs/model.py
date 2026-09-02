"""The difference tree: nodes, directions and their textual representation."""

from __future__ import annotations

from . import symbols

# Copy directions -------------------------------------------------------------
RIGHT = "->"   # computer's hard drive  ->  backup hard drive
LEFT = "<-"    # backup hard drive      ->  computer's hard drive
BOTH = "<>"    # a directory holding differences in both directions
NONE = "--"    # a container line, nothing to copy for the line itself

# Why a node is part of the difference list ------------------------------------
R_MISSING_BACKUP = "absent-B"    # exists on the computer only
R_MISSING_COMPUTER = "absent-C"  # exists on the backup only
R_SIZE = "size"                  # same name, different size
R_NEWER_C = "newer-C"            # same size, computer's copy is more recent
R_NEWER_B = "newer-B"            # same size, backup copy is more recent
R_TYPE = "type!"                 # file on one side, directory on the other
R_CONTAINER = ""                 # only holds differing children

_UNITS = ((1 << 40, "Tb"), (1 << 30, "Gb"), (1 << 20, "Mb"), (1 << 10, "Kb"))


def format_size(size):
    """Format a byte count the way the Main Pane shows it (``123Kb``, ``1Gb``)."""
    if size is None:
        return ""
    if size < 1024:
        return "%db" % size
    for factor, unit in _UNITS:
        if size >= factor:
            value = size / float(factor)
            if value < 10:
                text = "%.1f" % value
                if text.endswith(".0"):
                    text = text[:-2]
            else:
                text = "%.0f" % value
            return text + unit
    return "%db" % size


class Node:
    """One line of the Main Pane: a file or a directory that is different."""

    def __init__(self, name, is_dir, src, dst, direction, reason,
                 src_exists, dst_exists, src_size=None, dst_size=None,
                 src_mtime=None, dst_mtime=None, is_root=False, detail=""):
        self.name = name
        self.is_dir = is_dir
        self.src = src                  # absolute path on the computer's drive
        self.dst = dst                  # absolute path on the backup drive
        self.direction = direction
        self.reason = reason
        self.src_exists = src_exists
        self.dst_exists = dst_exists
        self.src_size = src_size
        self.dst_size = dst_size
        self.src_mtime = src_mtime
        self.dst_mtime = dst_mtime
        self.is_root = is_root
        self.detail = detail            # extra text shown for root lines
        self.children = []
        self.parent = None
        self.selected = False
        self.expanded = False           # the content starts hidden

    # -- tree ---------------------------------------------------------------
    def add(self, child):
        child.parent = self
        self.children.append(child)

    def walk(self):
        """Yield this node and every descendant, depth first."""
        yield self
        for child in self.children:
            for node in child.walk():
                yield node

    def depth(self):
        level, node = 0, self.parent
        while node is not None:
            level += 1
            node = node.parent
        return level

    # -- collapsing ---------------------------------------------------------
    @property
    def collapsible(self):
        """True for a directory that actually has something to hide."""
        return self.is_dir and bool(self.children)

    def toggle(self):
        """Show or hide the content of a directory."""
        if not self.collapsible:
            return False
        self.expanded = not self.expanded
        return True

    def set_expanded(self, value):
        """Expand/collapse this node and every directory below it."""
        for node in self.walk():
            if node.collapsible:
                node.expanded = value

    # -- display ------------------------------------------------------------
    @property
    def marker(self):
        """The glyph telling whether the content of a directory is shown."""
        if not self.collapsible:
            return symbols.S.LEAF
        return symbols.S.EXPANDED if self.expanded else symbols.S.COLLAPSED

    @property
    def display_name(self):
        name = self.name + "/" if self.is_dir else self.name
        if self.is_root and self.detail:
            name += "   (" + self.detail + ")"
        return name

    @property
    def display_size(self):
        """Size of the copy that would be transferred, files only."""
        if self.is_dir:
            return None
        if self.direction == LEFT:
            return self.dst_size if self.dst_exists else self.src_size
        return self.src_size if self.src_exists else self.dst_size

    # -- selection ----------------------------------------------------------
    def set_selected(self, value):
        """Select/unselect this node and, for a directory, all its content."""
        self.selected = value
        for child in self.children:
            child.set_selected(value)

    # -- direction ----------------------------------------------------------
    @property
    def can_flip(self):
        """A direction may only be flipped when both copies exist."""
        return self.src_exists and self.dst_exists and not self.is_root

    def flip(self):
        """Flip the copy direction of this node (and of its content)."""
        flipped = False
        if self.children:
            for child in self.children:
                flipped = child.flip() or flipped
            if flipped:
                self.refresh_direction()
        elif self.can_flip:
            self.direction = LEFT if self.direction == RIGHT else RIGHT
            flipped = True
        return flipped

    def refresh_direction(self):
        """Recompute a directory arrow out of the arrows of its content."""
        if self.is_root:
            self.direction = NONE
            return
        if not self.children:
            return
        directions = set()
        for child in self.children:
            if child.direction in (RIGHT, LEFT):
                directions.add(child.direction)
            elif child.direction == BOTH:
                directions.update((RIGHT, LEFT))
        if len(directions) == 1:
            self.direction = directions.pop()
        elif directions:
            self.direction = BOTH

    def __repr__(self):
        return "<Node %s %s %s>" % (self.direction, self.display_name, self.reason)


def flatten(roots, visible_only=True):
    """Flatten the forest into the display order.

    Returns a list of ``(node, prefix)`` pairs where ``prefix`` is the tree
    drawing that has to be printed in front of the check box.  The content of a
    collapsed directory is left out unless ``visible_only`` is False.
    """
    lines = []
    glyphs = symbols.S

    def walk(node, prefix, is_last, depth):
        if depth == 0:
            own, child_prefix = "", ""
        else:
            own = prefix + (glyphs.TREE_LAST if is_last else glyphs.TREE_BRANCH)
            child_prefix = prefix + (glyphs.TREE_BLANK if is_last
                                     else glyphs.TREE_PIPE)
        lines.append((node, own))
        if visible_only and not node.expanded:
            return
        last = len(node.children) - 1
        for index, child in enumerate(node.children):
            walk(child, child_prefix, index == last, depth + 1)

    for root in roots:
        walk(root, "", True, 0)
    return lines


def expand_all(roots, value=True):
    """Show (or hide) the content of every directory of the forest."""
    for root in roots:
        root.set_expanded(value)


def any_expanded(roots):
    """True as soon as one directory shows its content."""
    for root in roots:
        for node in root.walk():
            if node.collapsible and node.expanded:
                return True
    return False


def expanded_paths(roots):
    """The identity of every expanded directory, to survive a re-scan."""
    return set(node.src for root in roots for node in root.walk()
               if node.collapsible and node.expanded)


def restore_expanded(roots, paths):
    """Re-open the directories that were open before a re-scan."""
    for root in roots:
        for node in root.walk():
            if node.collapsible and node.src in paths:
                node.expanded = True


INFO_WIDTH = 8
SIZE_WIDTH = 9


def render_line(node, prefix, width, info=True):
    """Render one Main Pane line, padded/truncated to ``width`` characters."""
    box = "[X]" if node.selected else "[ ]"
    left = "%s%s %s %s %s" % (prefix, box, node.direction, node.marker,
                              node.display_name)
    right = ""
    if info and not node.is_root:
        tag = node.reason
        size = format_size(node.display_size)
        if tag or size:
            right = "%*s %*s" % (INFO_WIDTH, tag, SIZE_WIDTH, size)
    if not right:
        return _fit(left, width)
    space = width - len(right) - 1
    if space < 8:                       # very narrow terminal: drop the columns
        return _fit(left, width)
    return _fit(left, space) + " " + right


def _fit(text, width):
    """Pad with spaces, or cut with an ellipsis, to exactly ``width``."""
    if len(text) <= width:
        return text.ljust(width)
    if width <= 3:
        return text[:width]
    return text[:width - 3] + "..."


def list_width(rows, minimum=100):
    """Width giving every line of ``rows`` enough room, used by 'F4 List'."""
    widest = 0
    for node, prefix in rows:
        widest = max(widest, len(prefix) + 4 + len(node.direction) + 3
                     + len(node.display_name))
    return max(minimum, widest + INFO_WIDTH + SIZE_WIDTH + 2)


def count_differences(roots):
    """Number of differing files and directories, root containers excluded."""
    total = 0
    for root in roots:
        for node in root.walk():
            if not node.is_root:
                total += 1
    return total
