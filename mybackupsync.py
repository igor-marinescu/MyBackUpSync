#!/usr/bin/env python3
"""MyBackUpSync - synchronise a computer's hard drive with a backup hard drive.

Usage::

    python mybackupsync.py <drive>

    python mybackupsync.py E:\\                  (Windows)
    python mybackupsync.py /mnt/backupmedia/     (Linux)

The backup drive must hold a 'mybackupsync.config' file in its root folder.
"""

from __future__ import annotations

import argparse
import os
import sys

from mbs import APP_NAME, __version__
from mbs.config import CONFIG_NAME, ConfigError, load_config
from mbs.ui import App

USAGE = "python mybackupsync.py <drive>"


def fail(message):
    sys.stderr.write("%s: error: %s\n" % (APP_NAME, message))
    return 2


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mybackupsync.py",
        description="%s %s - synchronise a computer's hard drive with a "
                    "backup hard drive." % (APP_NAME, __version__),
        epilog="The backup drive must contain the configuration file '%s' "
               "in its root folder." % CONFIG_NAME)
    parser.add_argument("drive",
                        help="root of the backup hard drive, "
                             "for example 'E:\\' or '/mnt/backupmedia/'")
    parser.add_argument("--check-dir-times", action="store_true",
                        help="also report directories whose modification date "
                             "differs while their content is identical "
                             "(off by default: a directory date changes on its "
                             "own whenever its content is written)")
    parser.add_argument("--ascii", action="store_true",
                        help="draw the interface with plain 7 bit characters "
                             "instead of the Unicode box drawing glyphs")
    parser.add_argument("--list", action="store_true", dest="plain_list",
                        help="print the differences to the standard output and "
                             "exit, without starting the user interface")
    parser.add_argument("--version", action="version",
                        version="%s %s" % (APP_NAME, __version__))
    return parser


def print_list(backup_root, config_path, entries, check_dir_times,
               ascii_only=False):
    """Non interactive output, same format as the Main Pane."""
    from mbs import model, scanner, symbols

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    symbols.select(ascii_only, sys.stdout)

    roots, warnings = scanner.scan(entries, check_dir_times)
    print("%s %s - list of differences" % (APP_NAME, __version__))
    print("backup drive  : %s" % backup_root)
    print("configuration : %s" % config_path)
    print("differences   : %d" % model.count_differences(roots))
    print("")
    rows = model.flatten(roots, visible_only=False)
    width = model.list_width(rows)
    for node, prefix in rows:
        print(model.render_line(node, prefix, width).rstrip())
    for warning in warnings:
        print("! %s" % warning)
    return 0


def main(argv=None):
    parser = build_parser()
    options = parser.parse_args(argv)

    backup_root = os.path.abspath(os.path.expanduser(options.drive))
    if not os.path.isdir(backup_root):
        return fail("the backup drive '%s' does not exist or is not a directory"
                    % options.drive)

    try:
        config_path, entries = load_config(backup_root)
    except ConfigError as exc:
        return fail(str(exc))

    if options.plain_list:
        return print_list(backup_root, config_path, entries,
                          options.check_dir_times, options.ascii)

    application = App(backup_root, config_path, entries,
                      options.check_dir_times, options.ascii)
    try:
        return application.run()
    except KeyboardInterrupt:
        return 1


if __name__ == "__main__":
    sys.exit(main())
