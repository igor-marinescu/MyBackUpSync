"""Comparison of the computer's hard drive with the backup hard drive.

Only names, types, sizes and modification times are compared - the binary
content of the files is never read.
"""

from __future__ import annotations

import os
import stat

from . import model
from .model import Node

# Some file systems (FAT/exFAT) store the modification time with a 2 second
# resolution, therefore two files are considered equally old within that range.
MTIME_TOLERANCE = 2.0


class Scanner:
    """Builds the difference forest for a list of SyncEntry objects."""

    def __init__(self, entries, check_dir_times=False):
        self.entries = entries
        self.check_dir_times = check_dir_times
        self.warnings = []

    # -- helpers ------------------------------------------------------------
    def _listdir(self, path):
        """Return {name: (is_dir, stat_result)}; empty when unreadable."""
        result = {}
        try:
            with os.scandir(path) as iterator:
                for item in iterator:
                    try:
                        info = item.stat(follow_symlinks=False)
                    except OSError as exc:
                        self.warnings.append("cannot read '%s': %s" % (item.path, exc))
                        continue
                    result[item.name] = (stat.S_ISDIR(info.st_mode), info)
        except (FileNotFoundError, NotADirectoryError):
            pass
        except OSError as exc:
            self.warnings.append("cannot list '%s': %s" % (path, exc))
        return result

    @staticmethod
    def _same_time(left, right):
        return abs(left - right) <= MTIME_TOLERANCE

    @staticmethod
    def _sort_key(item):
        """Directories first, then files, both sorted case insensitively."""
        name, (left, right) = item
        is_dir = (left or right)[0]
        return (not is_dir, name.lower())

    # -- full subtree listing (used when one side is completely missing) ----
    def _list_subtree(self, entry, parent, src_dir, dst_dir, rel, direction):
        """Add every child of a directory that exists on one side only."""
        to_backup = direction == model.RIGHT
        base = src_dir if to_backup else dst_dir
        listing = sorted(self._listdir(base).items(),
                         key=lambda item: (not item[1][0], item[0].lower()))
        for name, (is_dir, info) in listing:
            child_rel = rel + (name,)
            if entry.is_ignored(child_rel, is_dir):
                continue
            src = os.path.join(src_dir, name)
            dst = os.path.join(dst_dir, name)
            node = Node(
                name=name,
                is_dir=is_dir,
                src=src,
                dst=dst,
                direction=direction,
                reason=model.R_MISSING_BACKUP if to_backup else model.R_MISSING_COMPUTER,
                src_exists=to_backup,
                dst_exists=not to_backup,
                src_size=None if is_dir or not to_backup else info.st_size,
                dst_size=None if is_dir or to_backup else info.st_size,
                src_mtime=info.st_mtime if to_backup else None,
                dst_mtime=None if to_backup else info.st_mtime,
            )
            parent.add(node)
            if is_dir:
                self._list_subtree(entry, node, src, dst, child_rel, direction)

    # -- comparison ---------------------------------------------------------
    def _compare_dir(self, entry, parent, src_dir, dst_dir, rel):
        """Compare two directories, attach every difference to parent.

        Returns True when at least one difference has been attached.
        """
        on_computer = self._listdir(src_dir)
        on_backup = self._listdir(dst_dir)

        merged = {}
        for name, value in on_computer.items():
            merged.setdefault(name, [None, None])[0] = value
        for name, value in on_backup.items():
            merged.setdefault(name, [None, None])[1] = value

        found = False
        for name, (left, right) in sorted(merged.items(), key=self._sort_key):
            child_rel = rel + (name,)
            is_dir = (left or right)[0]
            if entry.is_ignored(child_rel, is_dir):
                continue
            src = os.path.join(src_dir, name)
            dst = os.path.join(dst_dir, name)

            if left is not None and right is not None:
                node = self._compare_pair(entry, name, src, dst, child_rel, left, right)
            elif left is not None:
                node = self._only_on_one_side(entry, name, src, dst, child_rel,
                                              left, model.RIGHT)
            else:
                node = self._only_on_one_side(entry, name, src, dst, child_rel,
                                              right, model.LEFT)
            if node is not None:
                parent.add(node)
                found = True
        return found

    def _only_on_one_side(self, entry, name, src, dst, rel, side, direction):
        is_dir, info = side
        to_backup = direction == model.RIGHT
        node = Node(
            name=name,
            is_dir=is_dir,
            src=src,
            dst=dst,
            direction=direction,
            reason=model.R_MISSING_BACKUP if to_backup else model.R_MISSING_COMPUTER,
            src_exists=to_backup,
            dst_exists=not to_backup,
            src_size=None if is_dir or not to_backup else info.st_size,
            dst_size=None if is_dir or to_backup else info.st_size,
            src_mtime=info.st_mtime if to_backup else None,
            dst_mtime=None if to_backup else info.st_mtime,
        )
        if is_dir:
            self._list_subtree(entry, node, src, dst, rel, direction)
        return node

    def _compare_pair(self, entry, name, src, dst, rel, left, right):
        left_dir, left_info = left
        right_dir, right_info = right

        # A file on one side and a directory on the other.
        if left_dir != right_dir:
            return Node(
                name=name, is_dir=left_dir, src=src, dst=dst,
                direction=model.RIGHT, reason=model.R_TYPE,
                src_exists=True, dst_exists=True,
                src_size=None if left_dir else left_info.st_size,
                dst_size=None if right_dir else right_info.st_size,
                src_mtime=left_info.st_mtime, dst_mtime=right_info.st_mtime,
            )

        if left_dir:
            node = Node(
                name=name, is_dir=True, src=src, dst=dst,
                direction=model.NONE, reason=model.R_CONTAINER,
                src_exists=True, dst_exists=True,
                src_mtime=left_info.st_mtime, dst_mtime=right_info.st_mtime,
            )
            if self._compare_dir(entry, node, src, dst, rel):
                node.refresh_direction()
                return node
            if self.check_dir_times and not self._same_time(left_info.st_mtime,
                                                            right_info.st_mtime):
                node.direction = model.RIGHT
                node.reason = (model.R_NEWER_C
                               if left_info.st_mtime > right_info.st_mtime
                               else model.R_NEWER_B)
                return node
            return None

        # Two regular files: compare the size first, then the modification time.
        if left_info.st_size != right_info.st_size:
            reason = model.R_SIZE
        elif not self._same_time(left_info.st_mtime, right_info.st_mtime):
            reason = (model.R_NEWER_C if left_info.st_mtime > right_info.st_mtime
                      else model.R_NEWER_B)
        else:
            return None
        return Node(
            name=name, is_dir=False, src=src, dst=dst,
            direction=model.RIGHT, reason=reason,
            src_exists=True, dst_exists=True,
            src_size=left_info.st_size, dst_size=right_info.st_size,
            src_mtime=left_info.st_mtime, dst_mtime=right_info.st_mtime,
        )

    # -- entry point --------------------------------------------------------
    def scan(self):
        """Return the list of root nodes, one per configured directory.

        A configured directory whose content is completely synchronised is left
        out: only the directories that still hold a difference are returned.
        """
        self.warnings = []
        roots = []
        for entry in self.entries:
            root = Node(
                name=entry.label.rstrip("/"),
                is_dir=True,
                src=entry.source,
                dst=entry.target,
                direction=model.NONE,
                reason=model.R_CONTAINER,
                src_exists=os.path.isdir(entry.source),
                dst_exists=os.path.isdir(entry.target),
                is_root=True,
                detail=entry.source,
            )
            self._compare_dir(entry, root, entry.source, entry.target, ())
            # Nothing differs and the backup directory is there: fully in sync.
            if root.children or not root.dst_exists:
                roots.append(root)
        return roots


def scan(entries, check_dir_times=False):
    """Convenience wrapper: returns (roots, warnings)."""
    scanner = Scanner(entries, check_dir_times)
    roots = scanner.scan()
    return roots, scanner.warnings
