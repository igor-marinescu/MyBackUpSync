# MyBackUpSync

A Python tool for synchronising a computer's hard drive with a backup hard
drive, driven from a FAR-like terminal interface.

MyBackUpSync never decides anything on its own: it shows every difference
between the two drives and the user resolves each one by hand, by copying in
either direction or by deleting.

* Python 3.8 or newer, standard library only - no third party package.
* Runs on Windows and Linux.

## Usage

```
python mybackupsync.py <drive>
```

```
python mybackupsync.py E:\                  (Windows)
python mybackupsync.py /mnt/backupmedia/    (Linux)
```

`<drive>` is the root of the backup hard drive. It must contain the
configuration file `mybackupsync.config`; without it MyBackUpSync stops with an
error message.

Additional options:

| Option               | Effect                                                                  |
|----------------------|-------------------------------------------------------------------------|
| `--list`             | print the list of differences to the standard output and exit (no UI)    |
| `--ascii`            | draw with plain 7 bit characters instead of the box drawing glyphs       |
| `--check-dir-times`  | also report directories whose date differs while their content is equal  |
| `--ignore-date-time` | do not report an entry when only its date and time differ                |
| `--version`          | print the version and exit                                              |

With `--ignore-date-time` two entries carrying the same name are compared by
size alone: a file that exists on both drives with the same size is considered
synchronised however old the two copies are. Missing entries, differing sizes
and `type!` conflicts are still reported. Because a directory date is a date
too, `--ignore-date-time` also silences `--check-dir-times` when both are
given. Use it for a backup drive whose file system does not keep the
modification times of the computer's drive - a FAT stick that stores local
times, or a copy made by a tool that stamps the target with the copy date.

## Configuration file

`mybackupsync.config` lives in the root folder of the backup drive.

* Empty lines, and lines containing only spaces or tabs, are ignored.
* Everything from a `#` up to the end of the line is a comment.
* A name ending with `/` is a directory, otherwise it is a file.
* `*` in a name matches any sequence of characters.

### Directories to synchronise

```
[<computer_directory>/ -> <backup_directory>/]
```

`<computer_directory>/` is an absolute path on the computer's hard drive,
mounting point included. `<backup_directory>/` is relative to the root of the
backup drive, without mounting point. If `<computer_directory>/` does not
exist, MyBackUpSync stops with an error message.

Only the directories named in a `[]` tag - and their subdirectories - are ever
looked at.

### Rules

The `!` lines following a `[]` tag apply to that directory only.

| Rule                    | Meaning                                                        |
|-------------------------|----------------------------------------------------------------|
| `!/<sub_directory>/`    | ignore that one subdirectory, at that exact place               |
| `!*/<directory>/`       | ignore every directory with that name, at any level             |
| `!/<file>`              | ignore that one file, at that exact place                       |
| `!*/<file>`             | ignore every file with that name, at any level                  |

Example:

```
[C:/users/igor/Documents/ -> Documents/]

[D:/src/ -> src/]
!*/build/       # ignore every 'build' directory, at any level
!/test/         # ignore 'D:/src/test/' but keep 'D:/src/cli/test/'
!*/*.cmake      # ignore every '*.cmake' file, at any level
!/cli/unused.h  # ignore only 'D:/src/cli/unused.h'
```

An anchored rule (`!/...`) matches at one single place: `!/tmp*/` hides
`D:/src/tmp123/` but not `D:/src/other/tmp123/`. A `!*/...` rule matches the
trailing part of the path and therefore applies at every level.

## User interface

```
 MyBackUpSync 1.0.0   backup: E:\   differences: 10   marked: 1
┌─ Enter:open/close  Space:mark  Tab:direction  Left/BkSp:parent  Home/En ─┐
│[ ] -- - src/   (D:\src)                                                 ▲│
│ ├─[ ] <> - Sub-Directory1/                                              █│
│ │  ├─[X] ->   File11                                  absent-B     123Kb█│
│ │  ├─[ ] <-   File12                                  absent-C      234b█│
│ │  └─[ ] ->   File13                                  absent-B      23Kb█│
│ ├─[ ] <> - Sub-Directory2/                                              █│
│ │  ├─[ ] <- + Sub-Directory21/                        absent-C          █│
│ │  ├─[ ] ->   File22                                  absent-B       3Mb█│
│ │  └─[ ] <-   File23                                  absent-C       1Gb█│
│ └─[ ] ->   main.c                                         size       4Kb█│
│                                                                         ▼│
└─ D:\src\Sub-Directory1\File12   [5/11] ──────────────────────────────────┘
[F1 Refresh][F2 RefrDir][F4 List][F5 Copy][F8 Delete][F9 Collapse All][F10 Quit]
```

The frames, the tree, the scroll box and the progress bar use the Unicode box
drawing and block glyphs (U+2500..U+259F) that FAR keeps in its
`BOX_DEF_SYMBOLS` table. When the terminal cannot encode them - or with
`--ascii` - the same drawing is made out of `+`, `-`, `|` and `#`.

**Main Pane** - the tree of differences. Each line is
`[ ] <arrow> <mark> <name> <reason> <size>`:

* `[ ]` / `[X]` - the check box, toggled with the space bar. Marking a
  directory marks its whole content, unmarking it unmarks the whole content.
* the arrow tells where the entry would be copied:
  * `->` towards the backup drive (different, or missing on the backup drive),
  * `<-` towards the computer (missing on the computer),
  * `<>` a directory holding differences in both directions,
  * `--` a configured root, which is never copied or deleted itself.
* the mark tells whether the content of a directory is shown: `+` hidden,
  `-` shown, a space for a file or for a directory with nothing to show.
* the name; directories end with `/`.
* the reason of the difference: `absent-B`, `absent-C`, `size`, `newer-C`,
  `newer-B`, `type!`.
* the size of the copy that would be made; directories have no size.

A directory disappears from the list as soon as it - and everything below it -
is synchronised; a configured directory with nothing left to do is not listed
at all, so the list shrinks as the work gets done.

The content of every directory starts hidden: only the configured directories
that still hold a difference are shown. Enter opens or closes the directory
under the cursor, F9 opens or closes all of them at once.

`F1 Refresh` reads both drives again from top to bottom. `F2 RefrDir` reads
only the directory the cursor points to - a cheap way to check one directory
again after having worked on it outside MyBackUpSync, without paying for a
walk over every configured directory.

A scroll box on the right shows the visible part of the whole list. The bottom
border shows the full path of the entry under the cursor and its position.

**Bottom Pane** - the available commands.

### Keys

| Key                | Action                                                     |
|--------------------|------------------------------------------------------------|
| Up / Down          | move the cursor one line                                    |
| PageUp / PageDown  | move the cursor one screen                                  |
| Left / Backspace   | move the cursor to the parent directory                     |
| Pos1 / End         | move the cursor to the beginning / to the end               |
| Space              | mark or unmark the entry (a directory takes its content)    |
| Enter              | show or hide the content of the directory under the cursor  |
| Tab                | reverse the copy direction of the entry                     |
| F1                 | re-read both drives and rebuild the whole list              |
| F2                 | re-read the directory under the cursor only                 |
| F4                 | write the list of differences into a temporary text file    |
| F5                 | copy                                                        |
| F8                 | delete                                                      |
| F9                 | hide, or show, the content of every directory at once       |
| F10 / Q            | quit                                                        |

F5 and F8 work on every marked entry; when nothing is marked they work on the
entry under the cursor. A hidden entry keeps its mark and its direction, so
collapsing a directory never changes what an action does, and `F4 List` always
writes every difference whether it is shown or not. Both always show the complete list of operations first,
with `[ Ok ]` and `[ Cancel ]` - nothing is written before `[ Ok ]` is chosen.
In a dialog, Left/Right or Tab change the button, Enter validates, Esc cancels.

`F8 Delete` removes the entry from the drive the arrow points *away from*: `->`
deletes the computer's copy, `<-` deletes the backup copy. Use Tab first if you
want the other side.

`F2 RefrDir` re-reads one directory and replaces that branch of the tree:

* when the cursor is on a file, its parent directory is re-read;
* the open directories and the marks inside the branch are kept, so the list
  looks the same apart from what really changed on the drives;
* a directory that turns out to be synchronised leaves the list, and so does a
  parent left with nothing else to report;
* everything outside the branch is left exactly as it was - including a parent
  that is itself a difference, for instance a directory still missing on the
  backup drive. Only `F1 Refresh` rebuilds those.

## How differences are found

For every configured directory pair, both sides are listed and compared by
name, type, size and modification date. Binary content is never read.

* different size, or modification date differing by more than 2 seconds
  (the resolution of FAT file systems), makes a file different - with
  `--ignore-date-time` the size alone decides;
* a name existing on one side only is a difference;
* a name that is a file on one side and a directory on the other is reported
  as `type!`;
* ignored entries are neither compared nor listed, and a directory that is
  ignored is never entered;
* a directory whose whole content matches is not a difference and is not
  listed.

A directory that exists on one side only is listed with its whole content, so
individual files inside it can still be marked separately.

### Notes and assumptions

* **Directory dates.** By default a directory alone is never reported as
  different because of its date: writing anything inside a directory changes
  its date, which would make every copy produce a new difference. Pass
  `--check-dir-times` to get the strict behaviour. Directories that are created
  by a copy do receive the date of their original.
* **Dates in general.** `--ignore-date-time` drops the date from the
  comparison altogether. It makes MyBackUpSync blind to a file that was edited
  without changing its length, so keep it for the drives that cannot carry the
  modification times faithfully rather than using it by default.
* **Creation dates.** Only the modification date is compared. A creation date
  is not preserved by a file copy (and on Linux `st_ctime` is not a creation
  date at all), so comparing it would report every copied file as different.
* **Deleting a directory.** The files are removed one by one and the directory
  itself with `rmdir`. A directory still holding entries that the configuration
  file ignores is therefore kept, and reported, instead of being destroyed.
* **Symbolic links** are treated as ordinary entries and are never followed.
* **Upper/lower case** follows the file system: case insensitive on Windows,
  case sensitive on Linux - for the names as well as for the `!` rules.

## Layout

```
mybackupsync.py     command line entry point
mbs/config.py       configuration file parsing and validation
mbs/model.py        the difference tree and its ASCII representation
mbs/scanner.py      comparison of the two drives
mbs/actions.py      building and executing the copy / delete operations
mbs/screen.py       character and colour buffer
mbs/symbols.py      the FAR drawing glyphs, with their ASCII fall back
mbs/terminal.py     raw keyboard and ANSI screen, Windows and Linux
mbs/ui.py           the panes, the dialogs and the key loop
tests/              unit tests
Test/               example of a computer drive and a backup drive
```

## Tests

```
python -m unittest discover -s tests
```
