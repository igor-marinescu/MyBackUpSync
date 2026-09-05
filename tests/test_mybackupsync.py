"""Unit tests for MyBackUpSync.

Run them with::

    python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mbs import actions, model, scanner, symbols, terminal  # noqa: E402
from mbs.config import ConfigError, parse_text             # noqa: E402
from mbs.screen import Screen                              # noqa: E402
from mbs.terminal import Terminal                           # noqa: E402
from mbs.ui import App                                      # noqa: E402


def write(path, text="x", mtime=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


class ConfigTest(unittest.TestCase):

    def parse(self, text, root="/backup"):
        return parse_text(text, root)

    def test_comments_and_empty_lines(self):
        entries = self.parse("# a comment\n\n   \t \n"
                             "[/home/igor/doc/ -> doc/]   # trailing comment\n")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].target_parts, ("doc",))

    def test_missing_arrow(self):
        self.assertRaises(ConfigError, self.parse, "[/home/igor/doc/]\n")

    def test_directory_must_end_with_slash(self):
        self.assertRaises(ConfigError, self.parse, "[/home/igor/doc -> doc/]\n")
        self.assertRaises(ConfigError, self.parse, "[/home/igor/doc/ -> doc]\n")

    def test_backup_directory_must_be_relative(self):
        self.assertRaises(ConfigError, self.parse, "[/home/a/ -> /doc/]\n")
        self.assertRaises(ConfigError, self.parse, "[/home/a/ -> E:/doc/]\n")

    def test_rule_before_any_tag(self):
        self.assertRaises(ConfigError, self.parse, "!/build/\n")

    def test_no_tag_at_all(self):
        self.assertRaises(ConfigError, self.parse, "# nothing here\n")

    def test_unexpected_text(self):
        self.assertRaises(ConfigError, self.parse, "[/a/ -> a/]\nhello\n")

    # -- the examples of requirements.md ---------------------------------
    def rules(self, *lines):
        text = "[/src/ -> src/]\n" + "\n".join(lines) + "\n"
        return self.parse(text)[0]

    def test_anchored_directory(self):
        entry = self.rules("!/build/")
        self.assertTrue(entry.is_ignored(("build",), True))
        self.assertFalse(entry.is_ignored(("build",), False))
        self.assertFalse(entry.is_ignored(("other", "build"), True))

    def test_anchored_directory_pattern(self):
        entry = self.rules("!/tmp*/")
        self.assertTrue(entry.is_ignored(("tmp123",), True))
        self.assertTrue(entry.is_ignored(("tmp",), True))
        self.assertFalse(entry.is_ignored(("other", "tmp123"), True))

    def test_any_level_directory(self):
        entry = self.rules("!*/build/")
        self.assertTrue(entry.is_ignored(("build",), True))
        self.assertTrue(entry.is_ignored(("a", "b", "build"), True))
        self.assertFalse(entry.is_ignored(("a", "build", "c"), True))

    def test_any_level_directory_pattern(self):
        entry = self.rules("!*/build*/")
        self.assertTrue(entry.is_ignored(("a", "build_x86"), True))
        self.assertFalse(entry.is_ignored(("a", "rebuild"), True))

    def test_anchored_file(self):
        entry = self.rules("!/cli/unused.h")
        self.assertTrue(entry.is_ignored(("cli", "unused.h"), False))
        self.assertFalse(entry.is_ignored(("cli", "unused.h"), True))
        self.assertFalse(entry.is_ignored(("x", "cli", "unused.h"), False))

    def test_anchored_file_pattern(self):
        entry = self.rules("!/cli/unused*")
        self.assertTrue(entry.is_ignored(("cli", "unused123"), False))
        self.assertFalse(entry.is_ignored(("other", "cli", "unused1"), False))

    def test_any_level_file(self):
        entry = self.rules("!*/make.cmake")
        self.assertTrue(entry.is_ignored(("make.cmake",), False))
        self.assertTrue(entry.is_ignored(("a", "b", "make.cmake"), False))

    def test_any_level_file_pattern(self):
        entry = self.rules("!*/*.cmake")
        self.assertTrue(entry.is_ignored(("a", "example_auto.cmake"), False))
        self.assertFalse(entry.is_ignored(("a", "CMakeLists.txt"), False))

    def test_several_rules(self):
        entry = self.rules("!*/build/", "!/test/", "!*/*.cmake")
        self.assertTrue(entry.is_ignored(("cli", "build"), True))
        self.assertTrue(entry.is_ignored(("test",), True))
        self.assertFalse(entry.is_ignored(("cli", "test"), True))


class FormatTest(unittest.TestCase):

    def test_sizes(self):
        self.assertEqual(model.format_size(0), "0b")
        self.assertEqual(model.format_size(234), "234b")
        self.assertEqual(model.format_size(23 * 1024), "23Kb")
        self.assertEqual(model.format_size(123 * 1024), "123Kb")
        self.assertEqual(model.format_size(678 * 1024 ** 2), "678Mb")
        self.assertEqual(model.format_size(1024 ** 3), "1Gb")
        self.assertEqual(model.format_size(1536 * 1024 ** 2), "1.5Gb")

    def tree(self):
        root = model.Node("d", True, "s", "t", model.NONE, "", True, True,
                          is_root=True)
        first = model.Node("Sub1", True, "s", "t", model.BOTH, "", True, True)
        root.add(first)
        for name, direction in (("File11", model.RIGHT), ("File12", model.LEFT),
                                ("File13", model.RIGHT)):
            first.add(model.Node(name, False, "s", "t", direction, "",
                                 True, True, src_size=10))
        return root

    def test_tree_prefixes(self):
        root = self.tree()
        glyphs = symbols.S
        model.expand_all([root])
        prefixes = [prefix for _, prefix in model.flatten([root])]
        self.assertEqual(prefixes, [
            "",
            glyphs.TREE_LAST,
            glyphs.TREE_BLANK + glyphs.TREE_BRANCH,
            glyphs.TREE_BLANK + glyphs.TREE_BRANCH,
            glyphs.TREE_BLANK + glyphs.TREE_LAST,
        ])

    def test_render_line(self):
        node = model.Node("File11", False, "s", "t", model.RIGHT,
                          model.R_MISSING_BACKUP, True, False,
                          src_size=123 * 1024)
        line = model.render_line(node, " |-", 60)
        self.assertTrue(line.startswith(" |-[ ] ->   File11"), line)
        self.assertTrue(line.rstrip().endswith("123Kb"))
        self.assertEqual(len(line), 60)

    def test_render_selected(self):
        node = model.Node("d", True, "s", "t", model.LEFT, "", False, True)
        node.selected = True
        self.assertTrue(
            model.render_line(node, "", 40).startswith("[X] <-   d/"))


class CollapseTest(unittest.TestCase):
    """Requirement: the content of a directory starts hidden."""

    def setUp(self):
        self.root = model.Node("d", True, "s", "t", model.NONE, "", True, True,
                               is_root=True)
        self.sub = model.Node("Sub", True, "s2", "t2", model.RIGHT, "",
                              True, False)
        self.root.add(self.sub)
        self.leaf = model.Node("f.txt", False, "s3", "t3", model.RIGHT, "",
                               True, False, src_size=5)
        self.sub.add(self.leaf)

    def rows(self):
        return [node for node, _ in model.flatten([self.root])]

    def test_everything_is_collapsed_by_default(self):
        self.assertFalse(self.root.expanded)
        self.assertEqual(self.rows(), [self.root])

    def test_enter_opens_one_level(self):
        self.assertTrue(self.root.toggle())
        self.assertEqual(self.rows(), [self.root, self.sub])
        self.assertTrue(self.sub.toggle())
        self.assertEqual(self.rows(), [self.root, self.sub, self.leaf])

    def test_enter_closes_again(self):
        self.root.toggle()
        self.root.toggle()
        self.assertEqual(self.rows(), [self.root])

    def test_a_file_cannot_be_opened(self):
        self.assertFalse(self.leaf.toggle())
        self.assertFalse(self.leaf.collapsible)

    def test_an_empty_directory_cannot_be_opened(self):
        empty = model.Node("e", True, "s", "t", model.RIGHT, "", True, False)
        self.assertFalse(empty.collapsible)
        self.assertEqual(empty.marker, symbols.S.LEAF)

    def test_expand_all_and_collapse_all(self):
        self.assertFalse(model.any_expanded([self.root]))
        model.expand_all([self.root])
        self.assertTrue(model.any_expanded([self.root]))
        self.assertEqual(len(self.rows()), 3)
        model.expand_all([self.root], False)
        self.assertFalse(model.any_expanded([self.root]))
        self.assertEqual(len(self.rows()), 1)

    def test_markers(self):
        self.assertEqual(self.root.marker, symbols.S.COLLAPSED)
        self.root.toggle()
        self.assertEqual(self.root.marker, symbols.S.EXPANDED)
        self.assertEqual(self.leaf.marker, symbols.S.LEAF)

    def test_flatten_can_ignore_the_collapsed_state(self):
        rows = model.flatten([self.root], visible_only=False)
        self.assertEqual(len(rows), 3)

    def test_open_directories_survive_a_rescan(self):
        self.root.toggle()
        paths = model.expanded_paths([self.root])
        self.assertEqual(paths, {"s"})
        fresh = model.Node("d", True, "s", "t", model.NONE, "", True, True,
                           is_root=True)
        fresh.add(model.Node("Sub", True, "s2", "t2", model.RIGHT, "",
                             True, False))
        model.restore_expanded([fresh], paths)
        self.assertTrue(fresh.expanded)


class SymbolTest(unittest.TestCase):

    class Stream:
        def __init__(self, encoding):
            self.encoding = encoding

    def tearDown(self):
        symbols.select(False)

    def test_unicode_is_used_when_the_stream_can_encode_it(self):
        chosen = symbols.select(False, self.Stream("utf-8"))
        self.assertIs(chosen, symbols.UNICODE)
        self.assertEqual(chosen.V, "│")

    def test_ascii_fallback_on_a_narrow_encoding(self):
        chosen = symbols.select(False, self.Stream("cp1252"))
        self.assertIs(chosen, symbols.ASCII)
        self.assertEqual(chosen.V, "|")

    def test_ascii_can_be_forced(self):
        self.assertIs(symbols.select(True, self.Stream("utf-8")), symbols.ASCII)

    def test_both_sets_define_the_same_glyphs(self):
        self.assertEqual(set(symbols.UNICODE.__dict__),
                         set(symbols.ASCII.__dict__))

    def test_the_tree_glyphs_all_have_the_same_width(self):
        for glyph_set in (symbols.UNICODE, symbols.ASCII):
            widths = {len(glyph_set.TREE_BRANCH), len(glyph_set.TREE_LAST),
                      len(glyph_set.TREE_PIPE), len(glyph_set.TREE_BLANK)}
            self.assertEqual(widths, {3}, glyph_set.name)


class TerminalTest(unittest.TestCase):
    """The key decoding is pure logic and can be checked on any platform."""

    def test_plain_keys(self):
        self.assertEqual(Terminal._plain("\r"), terminal.ENTER)
        self.assertEqual(Terminal._plain("\n"), terminal.ENTER)
        self.assertEqual(Terminal._plain("\t"), terminal.TAB)
        self.assertEqual(Terminal._plain(" "), terminal.SPACE)
        self.assertEqual(Terminal._plain("\x7f"), terminal.BACKSPACE)
        self.assertEqual(Terminal._plain("\x08"), terminal.BACKSPACE)
        self.assertEqual(Terminal._plain("\x1b"), terminal.ESC)
        self.assertEqual(Terminal._plain("q"), "q")

    def test_ansi_sequences(self):
        cases = {
            "[A": terminal.UP, "[B": terminal.DOWN,
            "[C": terminal.RIGHT, "[D": terminal.LEFT,
            "[H": terminal.HOME, "[F": terminal.END,
            "[5~": terminal.PGUP, "[6~": terminal.PGDN,
            "[1~": terminal.HOME, "[4~": terminal.END,
            "OP": "F1", "OS": "F4", "[15~": "F5", "[21~": "F10",
        }
        for sequence, expected in cases.items():
            self.assertEqual(Terminal._escape(sequence), expected, sequence)

    def test_lone_escape(self):
        self.assertEqual(Terminal._escape(""), terminal.ESC)

    def test_windows_special_keys(self):
        special = terminal._WIN_SPECIAL
        self.assertEqual(special["H"], terminal.UP)
        self.assertEqual(special["P"], terminal.DOWN)
        self.assertEqual(special[";"], "F1")
        self.assertEqual(special["?"], "F5")
        self.assertEqual(special["B"], "F8")
        self.assertEqual(special["D"], "F10")


class ScreenTest(unittest.TestCase):

    def test_put_and_frame(self):
        glyphs = symbols.S
        screen = Screen(12, 4, color="A")
        screen.frame(0, 0, 12, 4, "F", title="Hi")
        screen.put(1, 1, "text", "T")
        rendered = ["".join(row) for row in screen.chars]
        self.assertEqual(rendered[0],
                         glyphs.TL + glyphs.H + " Hi " + glyphs.H * 5 + glyphs.TR)
        self.assertEqual(rendered[1], glyphs.V + "text      " + glyphs.V)
        self.assertEqual(rendered[3],
                         glyphs.BL + glyphs.H * 10 + glyphs.BR)

    def test_double_frame_uses_the_dialog_glyphs(self):
        glyphs = symbols.S
        screen = Screen(6, 3, color="A")
        screen.frame(0, 0, 6, 3, "F", double=True)
        rendered = ["".join(row) for row in screen.chars]
        self.assertEqual(rendered[0], glyphs.DTL + glyphs.DH * 4 + glyphs.DTR)
        self.assertEqual(rendered[1], glyphs.DV + "    " + glyphs.DV)
        self.assertEqual(rendered[2], glyphs.DBL + glyphs.DH * 4 + glyphs.DBR)

    def test_put_is_clipped(self):
        screen = Screen(5, 1)
        screen.put(0, 3, "abcdef", "T")
        self.assertEqual("".join(screen.chars[0]), "   ab")
        screen.put(9, 0, "nope", "T")          # outside, must not raise

    def test_lines_group_the_colours(self):
        screen = Screen(4, 1, color="A")
        screen.put(0, 2, "xy", "B")
        self.assertEqual(screen.lines(trim_last=False)[0],
                         "A  Bxy" + terminal.Color.RESET)


class DriveTestCase(unittest.TestCase):
    """Base class building a computer drive and a backup drive on disk."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="mbs_test_")
        self.computer = os.path.join(self.root, "DriveC")
        self.backup = os.path.join(self.root, "DriveE")
        os.makedirs(os.path.join(self.computer, "src"))
        os.makedirs(os.path.join(self.backup, "src"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def config(self, *rules):
        text = "[%s/ -> src/]\n" % os.path.join(self.computer, "src").replace(
            os.sep, "/")
        text += "".join(rule + "\n" for rule in rules)
        return parse_text(text, self.backup)

    def scan(self, *rules):
        roots, warnings = scanner.scan(self.config(*rules))
        self.assertEqual(warnings, [])
        return roots

    def names(self, roots):
        """Every difference below the root, collapsed or not."""
        rows = model.flatten(roots, visible_only=False)
        return [node.display_name for node, _ in rows][1:]

    def c(self, *parts):
        return os.path.join(self.computer, "src", *parts)

    def b(self, *parts):
        return os.path.join(self.backup, "src", *parts)


class ScanTest(DriveTestCase):

    def test_identical_drives_have_no_difference(self):
        write(self.c("main.c"), "hello", mtime=1000)
        write(self.b("main.c"), "hello", mtime=1000)
        roots = self.scan()
        self.assertEqual(model.count_differences(roots), 0)

    def test_a_synchronised_directory_is_not_listed_at_all(self):
        """Requirement: once in sync, a directory leaves the Main Pane."""
        write(self.c("main.c"), "hello", mtime=1000)
        write(self.b("main.c"), "hello", mtime=1000)
        self.assertEqual(self.scan(), [])

    def test_a_root_stays_while_it_still_differs(self):
        write(self.c("main.c"), "hello")
        self.assertEqual(len(self.scan()), 1)

    def test_a_root_stays_when_the_backup_directory_is_missing(self):
        shutil.rmtree(self.b())
        roots = self.scan()
        self.assertEqual(len(roots), 1)
        self.assertFalse(roots[0].dst_exists)

    def test_a_missing_backup_directory_is_created(self):
        shutil.rmtree(self.b())
        roots = self.scan()
        self.assertEqual(actions.execute(actions.build_copy_plan(roots)), [])
        self.assertTrue(os.path.isdir(self.b()))
        self.assertEqual(self.scan(), [])

    def test_missing_on_backup(self):
        write(self.c("main.c"), "hello")
        node = self.scan()[0].children[0]
        self.assertEqual(node.direction, model.RIGHT)
        self.assertEqual(node.reason, model.R_MISSING_BACKUP)

    def test_missing_on_computer(self):
        write(self.b("old.c"), "hello")
        node = self.scan()[0].children[0]
        self.assertEqual(node.direction, model.LEFT)
        self.assertEqual(node.reason, model.R_MISSING_COMPUTER)

    def test_different_size(self):
        write(self.c("main.c"), "hello world", mtime=1000)
        write(self.b("main.c"), "hello", mtime=1000)
        node = self.scan()[0].children[0]
        self.assertEqual(node.reason, model.R_SIZE)
        self.assertEqual(node.direction, model.RIGHT)

    def test_different_date(self):
        write(self.c("main.c"), "hello", mtime=2000)
        write(self.b("main.c"), "hello", mtime=1000)
        node = self.scan()[0].children[0]
        self.assertEqual(node.reason, model.R_NEWER_C)

    def test_date_tolerance(self):
        write(self.c("main.c"), "hello", mtime=1001)
        write(self.b("main.c"), "hello", mtime=1000)
        self.assertEqual(model.count_differences(self.scan()), 0)

    def test_binary_content_is_not_compared(self):
        write(self.c("main.c"), "aaaaa", mtime=1000)
        write(self.b("main.c"), "bbbbb", mtime=1000)
        self.assertEqual(model.count_differences(self.scan()), 0)

    def test_file_against_directory(self):
        write(self.c("thing"), "hello")
        os.makedirs(self.b("thing"))
        node = self.scan()[0].children[0]
        self.assertEqual(node.reason, model.R_TYPE)

    def test_missing_directory_is_listed_recursively(self):
        write(self.c("cli", "cli.c"), "hello")
        write(self.c("cli", "cli.h"), "hello")
        self.assertEqual(self.names(self.scan()), ["cli/", "cli.c", "cli.h"])

    def test_directory_with_both_directions(self):
        write(self.c("cli", "new.c"), "hello")
        write(self.b("cli", "old.c"), "hello")
        root = self.scan()[0]
        self.assertEqual(root.children[0].direction, model.BOTH)

    def test_directories_are_listed_before_files(self):
        write(self.c("zzz.c"), "hello")
        write(self.c("aaa", "a.c"), "hello")
        self.assertEqual(self.names(self.scan())[0], "aaa/")

    def test_ignored_entries_are_not_listed(self):
        write(self.c("build", "out.hex"), "hello")
        write(self.c("cli", "build", "out.hex"), "hello")
        write(self.c("cli", "cli.c"), "hello")
        write(self.c("example.cmake"), "hello")
        write(self.c("cli", "unused.h"), "hello")
        names = self.names(self.scan("!*/build/", "!*/*.cmake", "!/cli/unused.h"))
        self.assertEqual(names, ["cli/", "cli.c"])

    def test_directory_dates_are_ignored_by_default(self):
        os.makedirs(self.c("cli"))
        os.makedirs(self.b("cli"))
        os.utime(self.c("cli"), (5000, 5000))
        os.utime(self.b("cli"), (1000, 1000))
        self.assertEqual(model.count_differences(self.scan()), 0)
        roots, _ = scanner.scan(self.config(), check_dir_times=True)
        self.assertEqual(model.count_differences(roots), 1)


class ActionTest(DriveTestCase):

    def resolve(self, *rules):
        """Copy everything and return the freshly computed differences."""
        roots = self.scan(*rules)
        plan = actions.build_copy_plan(roots)
        errors = actions.execute(plan)
        self.assertEqual(errors, [])
        return self.scan(*rules)

    def test_copy_to_backup(self):
        write(self.c("main.c"), "hello")
        self.assertEqual(model.count_differences(self.resolve()), 0)
        self.assertTrue(os.path.isfile(self.b("main.c")))

    def test_copy_to_computer(self):
        write(self.b("old.c"), "hello")
        self.assertEqual(model.count_differences(self.resolve()), 0)
        self.assertTrue(os.path.isfile(self.c("old.c")))

    def test_copy_whole_directory_tree(self):
        write(self.c("cli", "sub", "deep.c"), "hello")
        write(self.c("cli", "cli.c"), "hello")
        self.assertEqual(model.count_differences(self.resolve()), 0)
        self.assertTrue(os.path.isfile(self.b("cli", "sub", "deep.c")))

    def test_copy_keeps_the_modification_date(self):
        write(self.c("main.c"), "hello", mtime=1000)
        self.resolve()
        self.assertAlmostEqual(os.path.getmtime(self.b("main.c")), 1000, delta=2)

    def test_copy_both_directions_at_once(self):
        write(self.c("new.c"), "hello")
        write(self.b("old.c"), "hello")
        self.assertEqual(model.count_differences(self.resolve()), 0)
        self.assertTrue(os.path.isfile(self.b("new.c")))
        self.assertTrue(os.path.isfile(self.c("old.c")))

    def test_copy_replaces_a_target_of_the_wrong_type(self):
        write(self.c("thing"), "hello")
        os.makedirs(self.b("thing"))
        write(self.b("thing", "inside.txt"), "hello")
        roots = self.scan()
        self.assertEqual(actions.execute(actions.build_copy_plan(roots)), [])
        self.assertTrue(os.path.isfile(self.b("thing")))

    def test_empty_directory_is_created(self):
        os.makedirs(self.c("empty"))
        self.assertEqual(model.count_differences(self.resolve()), 0)
        self.assertTrue(os.path.isdir(self.b("empty")))

    def test_delete_from_computer(self):
        write(self.c("main.c"), "hello")
        roots = self.scan()
        plan = actions.build_delete_plan(roots)
        self.assertEqual([op.side for op in plan], [actions.COMPUTER])
        self.assertEqual(actions.execute(plan), [])
        self.assertFalse(os.path.exists(self.c("main.c")))

    def test_delete_from_backup(self):
        write(self.b("old.c"), "hello")
        plan = actions.build_delete_plan(self.scan())
        self.assertEqual([op.side for op in plan], [actions.BACKUP])
        self.assertEqual(actions.execute(plan), [])
        self.assertFalse(os.path.exists(self.b("old.c")))

    def test_delete_a_whole_directory(self):
        write(self.c("cli", "sub", "deep.c"), "hello")
        self.assertEqual(actions.execute(actions.build_delete_plan(self.scan())),
                         [])
        self.assertFalse(os.path.exists(self.c("cli")))

    def test_delete_keeps_a_directory_holding_ignored_files(self):
        write(self.c("cli", "cli.c"), "hello")
        write(self.c("cli", "keep.cmake"), "hello")
        roots = self.scan("!*/*.cmake")
        errors = actions.execute(actions.build_delete_plan(roots))
        self.assertEqual(len(errors), 1)
        self.assertTrue(os.path.isfile(self.c("cli", "keep.cmake")))
        self.assertFalse(os.path.exists(self.c("cli", "cli.c")))

    def test_delete_does_not_touch_a_shared_directory(self):
        write(self.c("cli", "new.c"), "hello")
        write(self.c("cli", "same.c"), "hello", mtime=1000)
        write(self.b("cli", "same.c"), "hello", mtime=1000)
        self.assertEqual(actions.execute(actions.build_delete_plan(self.scan())),
                         [])
        self.assertTrue(os.path.isdir(self.c("cli")))
        self.assertTrue(os.path.isfile(self.c("cli", "same.c")))

    def test_selection_of_a_directory_covers_its_content(self):
        write(self.c("cli", "a.c"), "hello")
        write(self.c("cli", "b.c"), "hello")
        write(self.c("other.c"), "hello")
        roots = self.scan()
        directory = roots[0].children[0]
        directory.set_selected(True)
        self.assertTrue(all(node.selected for node in directory.walk()))
        self.assertEqual(actions.selected_nodes(roots), [directory])
        plan = actions.build_copy_plan(actions.selected_nodes(roots))
        self.assertEqual(actions.execute(plan), [])
        self.assertTrue(os.path.isfile(self.b("cli", "a.c")))
        self.assertFalse(os.path.exists(self.b("other.c")))
        directory.set_selected(False)
        self.assertFalse(actions.has_selection(roots))

    def test_flip_changes_the_copy_direction(self):
        write(self.c("main.c"), "hello world", mtime=2000)
        write(self.b("main.c"), "hello", mtime=1000)
        roots = self.scan()
        node = roots[0].children[0]
        self.assertEqual(node.direction, model.RIGHT)
        self.assertTrue(node.flip())
        self.assertEqual(node.direction, model.LEFT)
        self.assertEqual(actions.execute(actions.build_copy_plan([node])), [])
        self.assertEqual(os.path.getsize(self.c("main.c")), 5)

    def test_a_missing_file_cannot_be_flipped(self):
        write(self.c("main.c"), "hello")
        node = self.scan()[0].children[0]
        self.assertFalse(node.can_flip)
        self.assertFalse(node.flip())


class IgnoreDateTimeTest(DriveTestCase):
    """'--ignore-date-time': only the size decides between two same names."""

    def ignoring(self, *rules):
        roots, warnings = scanner.scan(self.config(*rules), ignore_date_time=True)
        self.assertEqual(warnings, [])
        return roots

    def test_a_different_date_alone_is_not_a_difference(self):
        write(self.c("main.c"), "hello", mtime=5000)
        write(self.b("main.c"), "hello", mtime=1000)
        self.assertEqual(model.count_differences(self.scan()), 1)
        self.assertEqual(self.ignoring(), [])

    def test_a_different_size_is_still_a_difference(self):
        write(self.c("main.c"), "hello world", mtime=1000)
        write(self.b("main.c"), "hello", mtime=1000)
        node = self.ignoring()[0].children[0]
        self.assertEqual(node.reason, model.R_SIZE)

    def test_a_missing_entry_is_still_a_difference(self):
        write(self.c("main.c"), "hello")
        node = self.ignoring()[0].children[0]
        self.assertEqual(node.reason, model.R_MISSING_BACKUP)

    def test_it_also_silences_the_directory_dates(self):
        """A directory date is a date too: '--check-dir-times' gives way."""
        os.makedirs(self.c("cli"))
        os.makedirs(self.b("cli"))
        os.utime(self.c("cli"), (5000, 5000))
        os.utime(self.b("cli"), (1000, 1000))
        roots, _ = scanner.scan(self.config(), check_dir_times=True,
                                ignore_date_time=True)
        self.assertEqual(model.count_differences(roots), 0)


class RescanNodeTest(DriveTestCase):
    """'F2': one single directory is read again, the rest is left alone."""

    def test_a_resolved_directory_disappears(self):
        write(self.c("cli", "a.c"), "hello", mtime=1000)
        node = self.scan()[0].children[0]
        self.assertEqual(node.display_name, "cli/")
        write(self.b("cli", "a.c"), "hello", mtime=1000)
        fresh, warnings = scanner.rescan_node(node)
        self.assertIsNone(fresh)
        self.assertEqual(warnings, [])

    def test_a_new_file_shows_up(self):
        write(self.c("cli", "a.c"), "hello", mtime=1000)
        write(self.b("cli", "a.c"), "hello", mtime=1000)
        write(self.c("cli", "b.c"), "hello")
        roots = self.scan()
        node = roots[0].children[0]
        self.assertEqual(node.display_name, "cli/")
        write(self.c("cli", "c.c"), "hello")
        fresh, _ = scanner.rescan_node(node)
        self.assertEqual([child.name for child in fresh.children],
                         ["b.c", "c.c"])

    def test_a_configured_root_can_be_read_again(self):
        write(self.c("main.c"), "hello", mtime=1000)
        root = self.scan()[0]
        write(self.b("main.c"), "hello", mtime=1000)
        self.assertIsNone(scanner.rescan_node(root)[0])

    def test_the_rules_of_the_entry_still_apply(self):
        write(self.c("cli", "cli.c"), "hello")
        node = self.scan("!*/*.cmake")[0].children[0]
        write(self.c("cli", "make.cmake"), "hello")
        fresh, _ = scanner.rescan_node(node)
        self.assertEqual([child.name for child in fresh.children], ["cli.c"])

    def test_it_honours_ignore_date_time(self):
        write(self.c("cli", "a.c"), "hello", mtime=5000)
        write(self.b("cli", "a.c"), "hello", mtime=1000)
        node = self.scan()[0].children[0]
        self.assertIsNotNone(scanner.rescan_node(node)[0])
        self.assertIsNone(scanner.rescan_node(node, ignore_date_time=True)[0])


class RescanDirCommandTest(DriveTestCase):
    """The 'F2' command of the user interface, tree surgery included."""

    def app(self, *rules):
        application = App(self.backup, "config", self.config(*rules))
        application.rescan(keep_position=False)
        application.roots[0].set_expanded(True)
        application.rebuild()
        return application

    def shown(self, application):
        return [node.display_name for node, _ in application.rows][1:]

    def move_to(self, application, name):
        for index, (node, _) in enumerate(application.rows):
            if node.display_name == name:
                application.cursor = index
                return node
        self.fail("'%s' is not listed: %s" % (name, self.shown(application)))

    def test_only_the_chosen_directory_is_read_again(self):
        write(self.c("aaa", "a.c"), "hello")
        write(self.c("bbb", "b.c"), "hello")
        application = self.app()
        self.move_to(application, "aaa/")
        # Resolve both directories behind the back of the application.
        write(self.b("aaa", "a.c"), "hello")
        write(self.b("bbb", "b.c"), "hello")
        application.do_rescan_dir()
        # 'aaa/' is gone; 'bbb/' stays, it has not been looked at.
        self.assertEqual(self.shown(application), ["bbb/", "b.c"])

    def test_a_file_refreshes_its_parent_directory(self):
        write(self.c("cli", "a.c"), "hello")
        write(self.c("cli", "b.c"), "hello")
        application = self.app()
        self.move_to(application, "a.c")
        write(self.b("cli", "a.c"), "hello")
        application.do_rescan_dir()
        self.assertEqual(self.shown(application), ["cli/", "b.c"])

    def test_an_emptied_parent_leaves_the_list_too(self):
        os.makedirs(self.c("cli"))
        os.makedirs(self.b("cli"))
        write(self.c("cli", "sub", "a.c"), "hello")
        application = self.app()
        self.move_to(application, "sub/")
        write(self.b("cli", "sub", "a.c"), "hello")
        application.do_rescan_dir()
        # 'sub/' was the only reason 'cli/' and the root were listed.
        self.assertEqual(application.roots, [])
        self.assertEqual(application.rows, [])

    def test_a_parent_that_is_a_difference_of_its_own_stays(self):
        """'cli/' is missing on the backup drive: only 'F1' can clear it."""
        write(self.c("cli", "sub", "a.c"), "hello")
        application = self.app()
        self.move_to(application, "sub/")
        write(self.b("cli", "sub", "a.c"), "hello")
        application.do_rescan_dir()
        self.assertEqual(self.shown(application), ["cli/"])
        application.rescan()
        self.assertEqual(application.roots, [])

    def test_open_directories_and_marks_survive(self):
        write(self.c("cli", "sub", "a.c"), "hello")
        write(self.c("cli", "b.c"), "hello")
        application = self.app()
        self.move_to(application, "b.c").set_selected(True)
        self.move_to(application, "cli/")
        write(self.c("cli", "c.c"), "hello")
        application.do_rescan_dir()
        self.assertEqual(self.shown(application),
                         ["cli/", "sub/", "a.c", "b.c", "c.c"])
        marked = [node.display_name for node in application.roots[0].walk()
                  if node.selected]
        self.assertEqual(marked, ["b.c"])

    def test_the_cursor_stays_on_the_refreshed_directory(self):
        write(self.c("aaa", "a.c"), "hello")
        write(self.c("bbb", "b.c"), "hello")
        application = self.app()
        self.move_to(application, "bbb/")
        write(self.c("bbb", "c.c"), "hello")
        application.do_rescan_dir()
        self.assertEqual(application.current_node().display_name, "bbb/")

    def test_the_direction_of_the_parents_is_recomputed(self):
        write(self.c("cli", "a.c"), "hello")
        application = self.app()
        self.assertEqual(application.roots[0].children[0].direction, model.RIGHT)
        self.move_to(application, "cli/")
        write(self.b("cli", "b.c"), "hello")
        application.do_rescan_dir()
        self.assertEqual(application.roots[0].children[0].direction, model.BOTH)


if __name__ == "__main__":
    unittest.main()
