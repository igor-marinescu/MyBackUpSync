"""Parsing and validation of the MyBackUpSync configuration file.

The configuration file (``mybackupsync.config``) lives in the root folder of the
backup hard drive and describes which directories of the computer's hard drive
have to be kept in sync with which directory of the backup drive, plus the
optional rules telling which files/directories must be ignored.

Format (see requirements.md)::

    # a comment
    [C:/users/igor/Documents/ -> Documents/]
    [D:/src/ -> src/]
    !*/build/        # ignore every 'build' directory, at any level
    !/test/          # ignore only 'D:/src/test/'
    !*/*.cmake       # ignore every '*.cmake' file, at any level
    !/cli/unused.h   # ignore only 'D:/src/cli/unused.h'
"""

from __future__ import annotations

import fnmatch
import os

CONFIG_NAME = "mybackupsync.config"


class ConfigError(Exception):
    """Raised when the configuration file is missing, malformed or invalid."""


def _split_parts(text):
    """Split a '/' separated path into its non empty components."""
    return tuple(p for p in text.replace("\\", "/").split("/") if p)


class IgnoreRule:
    """A single ``!`` rule attached to a :class:`SyncEntry`.

    ``anchored`` rules (``!/name``) are matched against the whole path relative
    to the synchronised directory, therefore they only ever match at one
    precise location.  Non anchored rules (``!*/name``) match the trailing
    components of the relative path, therefore they match at any level.
    """

    def __init__(self, raw, parts, is_dir, anchored, lineno):
        self.raw = raw
        self.parts = parts
        self.is_dir = is_dir
        self.anchored = anchored
        self.lineno = lineno

    def matches(self, rel_parts, is_dir):
        """Return True when the entry ``rel_parts`` is covered by this rule."""
        if self.is_dir != is_dir:
            return False
        n, m = len(rel_parts), len(self.parts)
        if self.anchored:
            if n != m:
                return False
            tail = rel_parts
        else:
            if n < m:
                return False
            tail = rel_parts[n - m:]
        # fnmatch normalises the case on Windows and is case sensitive on POSIX,
        # which is exactly how the underlying file systems behave.
        for name, pattern in zip(tail, self.parts):
            if not fnmatch.fnmatch(name, pattern):
                return False
        return True

    def __str__(self):
        return self.raw


class SyncEntry:
    """One ``[<computer_directory>/ -> <backup_directory>/]`` mapping."""

    def __init__(self, source, target_rel, backup_root, lineno):
        self.lineno = lineno
        self.source_raw = source
        self.target_raw = target_rel
        self.source = os.path.normpath(source.replace("/", os.sep))
        self.target_parts = _split_parts(target_rel)
        self.target = os.path.normpath(os.path.join(backup_root, *self.target_parts))
        self.rules = []

    @property
    def label(self):
        """Short name used as the root line of the difference tree."""
        return "/".join(self.target_parts) + "/" if self.target_parts else "/"

    def add_rule(self, rule):
        self.rules.append(rule)

    def is_ignored(self, rel_parts, is_dir):
        for rule in self.rules:
            if rule.matches(rel_parts, is_dir):
                return True
        return False

    def __str__(self):
        return "[%s -> %s]" % (self.source_raw, self.target_raw)


def _parse_rule(line, lineno):
    body = line[1:].strip()
    if not body:
        raise ConfigError("line %d: empty '!' rule" % lineno)
    is_dir = body.endswith("/")
    if is_dir:
        body = body[:-1]
    if body.startswith("*/"):
        anchored = False
        body = body[2:]
    elif body.startswith("/"):
        anchored = True
        body = body[1:]
    else:
        # Tolerated shorthand: '!name' behaves like '!*/name'.
        anchored = False
    parts = _split_parts(body)
    if not parts:
        raise ConfigError("line %d: rule '%s' does not name a file or directory"
                          % (lineno, line))
    return IgnoreRule(line, parts, is_dir, anchored, lineno)


def _parse_tag(line, lineno, backup_root):
    body = line[1:-1].strip()
    if "->" not in body:
        raise ConfigError("line %d: '%s' misses the '->' separator, expected "
                          "[<computer_directory>/ -> <backup_directory>/]"
                          % (lineno, line))
    source, target = body.split("->", 1)
    source = source.strip()
    target = target.strip()
    if not source or not target:
        raise ConfigError("line %d: '%s' has an empty directory name" % (lineno, line))
    if not source.endswith("/") and not source.endswith("\\"):
        raise ConfigError("line %d: computer directory '%s' must end with '/'"
                          % (lineno, source))
    if not target.endswith("/") and not target.endswith("\\"):
        raise ConfigError("line %d: backup directory '%s' must end with '/'"
                          % (lineno, target))
    normalised = target.replace("\\", "/")
    if normalised.startswith("/") or ":" in normalised:
        raise ConfigError("line %d: backup directory '%s' must be relative to the "
                          "backup drive (no mounting point)" % (lineno, target))
    if ".." in _split_parts(normalised):
        raise ConfigError("line %d: backup directory '%s' must not contain '..'"
                          % (lineno, target))
    return SyncEntry(source, target, backup_root, lineno)


def parse_text(text, backup_root):
    """Parse the content of a configuration file, return a list of entries."""
    entries = []
    current = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = _parse_tag(line, lineno, backup_root)
            entries.append(current)
        elif line.startswith("!"):
            if current is None:
                raise ConfigError("line %d: rule '%s' appears before any "
                                  "[<computer_directory>/ -> <backup_directory>/] tag"
                                  % (lineno, line))
            current.add_rule(_parse_rule(line, lineno))
        else:
            raise ConfigError("line %d: unexpected text '%s'" % (lineno, line))
    if not entries:
        raise ConfigError("no [<computer_directory>/ -> <backup_directory>/] "
                          "tag found in the configuration file")
    return entries


def load_config(backup_root):
    """Read ``<backup_root>/mybackupsync.config`` and validate it.

    Raises :class:`ConfigError` when the file is missing, malformed, or when a
    configured computer directory does not exist.
    """
    path = os.path.join(backup_root, CONFIG_NAME)
    if not os.path.isfile(path):
        raise ConfigError("configuration file '%s' not found on the backup drive"
                          % path)
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            text = handle.read()
    except OSError as exc:
        raise ConfigError("cannot read '%s': %s" % (path, exc))

    entries = parse_text(text, backup_root)
    for entry in entries:
        if not os.path.isdir(entry.source):
            raise ConfigError("line %d: the computer directory '%s' does not exist"
                              % (entry.lineno, entry.source_raw))
    return path, entries
