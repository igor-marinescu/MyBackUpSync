"""Building and executing the copy / delete operations chosen by the user."""

from __future__ import annotations

import os
import shutil
import stat

from . import model

COPY = "copy"
MKDIR = "mkdir"
DELETE = "delete"

COMPUTER = "C"
BACKUP = "B"


class Operation:
    """A single elementary action on the file system."""

    def __init__(self, kind, source, target, is_dir, side, node):
        self.kind = kind
        self.source = source
        self.target = target
        self.is_dir = is_dir
        self.side = side          # the drive that is modified: COMPUTER/BACKUP
        self.node = node

    @property
    def path(self):
        """The path that is created, overwritten or removed."""
        return self.target

    def describe(self):
        if self.kind == DELETE:
            what = "DELETE  " + self.side
        elif self.kind == MKDIR:
            what = "MKDIR   " + self.side
        else:
            what = "COPY  " + ("C->B" if self.side == BACKUP else "B->C")
        return "%-11s %s" % (what, self.target)

    def __repr__(self):
        return "<Operation %s>" % self.describe()


# -- selection ---------------------------------------------------------------
def selected_nodes(roots):
    """Top most selected nodes; a selected directory hides its content."""
    found = []

    def walk(node):
        if node.selected and not node.is_root:
            found.append(node)
            return
        for child in node.children:
            walk(child)

    for root in roots:
        walk(root)
    return found


def has_selection(roots):
    for root in roots:
        for node in root.walk():
            if node.selected and not node.is_root:
                return True
    return False


def clear_selection(roots):
    for root in roots:
        for node in root.walk():
            node.selected = False


# -- copy --------------------------------------------------------------------
def _copy_node(node, ops):
    if node.is_root:
        if not node.dst_exists:
            ops.append(Operation(MKDIR, node.src, node.dst, True, BACKUP, node))
        for child in node.children:
            _copy_node(child, ops)
        return

    if node.is_dir:
        if node.direction in (model.RIGHT, model.NONE, model.BOTH):
            if not node.dst_exists:
                ops.append(Operation(MKDIR, node.src, node.dst, True, BACKUP, node))
        if node.direction in (model.LEFT, model.NONE, model.BOTH):
            if not node.src_exists:
                ops.append(Operation(MKDIR, node.dst, node.src, True, COMPUTER, node))
        for child in node.children:
            _copy_node(child, ops)
        return

    if node.direction == model.LEFT:
        ops.append(Operation(COPY, node.dst, node.src, False, COMPUTER, node))
    else:
        ops.append(Operation(COPY, node.src, node.dst, False, BACKUP, node))


def build_copy_plan(nodes):
    """Return the ordered list of operations copying the given nodes."""
    ops = []
    for node in nodes:
        _copy_node(node, ops)
    return ops


# -- delete ------------------------------------------------------------------
def _delete_node(node, ops):
    if node.is_root:
        for child in node.children:
            _delete_node(child, ops)
        return

    if node.is_dir:
        for child in node.children:
            _delete_node(child, ops)
        # The directory itself is only removed when it exists on one side only;
        # a directory present on both drives just loses its differing content.
        if node.direction == model.RIGHT and not node.dst_exists:
            ops.append(Operation(DELETE, node.src, node.src, True, COMPUTER, node))
        elif node.direction == model.LEFT and not node.src_exists:
            ops.append(Operation(DELETE, node.dst, node.dst, True, BACKUP, node))
        return

    if node.direction == model.LEFT:
        ops.append(Operation(DELETE, node.dst, node.dst, False, BACKUP, node))
    else:
        ops.append(Operation(DELETE, node.src, node.src, False, COMPUTER, node))


def build_delete_plan(nodes):
    """Return the ordered list of operations deleting the given nodes.

    Files are removed one by one and a directory is removed only after its
    content, using rmdir: a directory still holding files that are not part of
    the synchronisation (because they are ignored by the configuration file) is
    therefore never destroyed silently.
    """
    ops = []
    for node in nodes:
        _delete_node(node, ops)
    return ops


# -- execution ---------------------------------------------------------------
def _force_remove_file(path):
    try:
        os.remove(path)
    except PermissionError:
        os.chmod(path, stat.S_IWRITE)
        os.remove(path)


def _prepare_target(target, want_dir):
    """Remove a target of the wrong type so that the copy can take place."""
    if not os.path.lexists(target):
        return
    if os.path.isdir(target) and not os.path.islink(target):
        if not want_dir:
            shutil.rmtree(target)
    elif want_dir:
        _force_remove_file(target)


def execute(operations, progress=None):
    """Run every operation, return the list of error messages.

    ``progress`` is called as ``progress(done, total, text)`` before each step.
    """
    errors = []
    created_dirs = []
    total = len(operations)

    for index, operation in enumerate(operations):
        if progress is not None:
            progress(index, total, operation.describe())
        try:
            if operation.kind == MKDIR:
                _prepare_target(operation.target, True)
                os.makedirs(operation.target, exist_ok=True)
                created_dirs.append(operation)
            elif operation.kind == COPY:
                parent = os.path.dirname(operation.target)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                _prepare_target(operation.target, False)
                if os.path.lexists(operation.target):
                    try:
                        os.chmod(operation.target, stat.S_IWRITE)
                    except OSError:
                        pass
                shutil.copy2(operation.source, operation.target)
            elif operation.kind == DELETE:
                if operation.is_dir:
                    try:
                        os.rmdir(operation.target)
                    except OSError:
                        errors.append("not empty, kept: %s" % operation.target)
                else:
                    _force_remove_file(operation.target)
        except OSError as exc:
            errors.append("%s: %s" % (operation.describe(), exc))

    # Give the freshly created directories the date of their original.
    for operation in reversed(created_dirs):
        try:
            shutil.copystat(operation.source, operation.target)
        except OSError:
            pass

    if progress is not None:
        progress(total, total, "")
    return errors
