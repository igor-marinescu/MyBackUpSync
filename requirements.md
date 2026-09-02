# MyBackUpSync

## Description

"MyBackUpSync" (My BackUp Synchronisation) - a Python tool for synchronising a computer's hard drive with a backup hard drive.

## Terms

The following terms are used:

- 'directory' ('directories') and 'folder' ('folders') mean the same.
- 'sync' and 'synchronise' mean the same: the process of modifying the content of two hard drives (computer's hard drive and backup hard drive) so that they have the same files and directories (except for files and directories to be ignored).
- a `*` inside of a file or directory name means many files or directories that have that filename pattern. Fort example `file*` can indicate `file1`, `fileaha`, `file any`...

## Requirements

The following requirements must be implemented:

- MyBackUpSync must be able to work on Windows and Linux.

- MyBackUpSync is invoked from command line: `python mybackupsync.py <drive>`.

    - Where `<drive>` is the backup hard drive to sync with. Example `python mybackupsync.py E:\` for Windows or `python mybackupsync.py /mnt/backupmedia/` for Linux.

- MyBackUpSync expects a [Configuration File](#configuration-file) in the root directory of the backup hard drive. If the Configuration File is missing, MyBackUpSync exits with error message.

- MyBackUpSync has a User Interface (UI) described in [UI](#ui).

### Synchronising Files

Synchronising a computer's hard drive with a backup hard drive means following:

- Check if there are differences between computer's hard drive and backup hard drive:

    - Check files/directories exists: check if directories and files from computer's hard drive exist on backup hard drive and vice versa.

    - Check files/directories creation/modification date: check if directories and files from computer's hard drive has the same creation/modification date as the ones on backup hard drive.

    - Check files/directories size: check if files from computer's hard drive has the same size as the ones on backup hard drive.

    - Do not check if files have the same binary content.

- If there are differences between computer's hard drive and backup hard drive, show the differences to the User.

- If a directory does not contain any sub-directory or file that is different (it is completely synchronised), the directory itself must not be shown to the User. This applies to every directory, including the directories listed inside of a `[]` tag in the Configuration File: as soon as such a directory is completely synchronised, it disappears from the list of differences.

- User manually resolves every difference between computer's hard drive and backup hard drive using following functionality:

    - Copy one or many files/directories from computer's hard drive to backup hard drive (`->`).

    - Copy one or many files/directories from backup hard drive to computer's hard drive (`<-`).

    - Delete one or many files/directories from computer's hard drive.

    - Delete one or many files/directories from backup hard drive.

- The list of directories to check (synchronise) is defined in Configuration File together with some extra rules (optional) which files/directories to ignore in process of sync.

### Configuration File

The Configuration File lists all directories from computer's hard drive that must be synchronised with the backup hard drive. Also the files or sub folders that must be ignored in those directories. The Configuration File must follow the following rules and format:

- The Configuration File is a text file, called `mybackupsync.config`, located at the root folder of backup hard drive.

- Empty lines or lines wich contains only spaces and/or tabs are ignored.

- The text followed a `#` symbol is considered a comment and must be ignored (together with the `#` symbol) until the end of the line.

- If a word ends with `/` symbol, it is a directory otherwise it is a file. Example `documents/` and `igor.user/` are directories; `documents` and `igor.user` are files.

- If a directory in computer's hard drive must be sync with backup hard drive, it is written in configuration file inside of a `[]` tag in format: `[<computer_drive_directory>/ -> <backup_drive_directory>/]`. 

    - Where `<computer_drive_directory>/` is the directory name on the computer's hard drive, containing also the mounting point, for example `C:/users/igor/Documents/`.

    - Where `<backup_drive_directory>/` is the directory name on the backup hard drive without mounting point, for example `Documents/`.

    - For example the line `[C:/users/igor/Documents/ -> Documents/]` means: sync the content of the `C:/users/igor/Documents/` directory (including sub-directories) from the computer's hard drive to the backup drive inside of `<backup_drive_mounting_point>/Documents/`.

    - If `<computer_drive_directory>/` is missing on computer's hard drive, MyBackUpSync exits with error message.

- MyBackUpSync checks and syncs only the content of directories and subdirectories mentioned in configuration file inside of `[]` tags.

- The non empty lines that follows a `[]` tag, are extra rules applied only to the last specified directory to be synchronised:

    - The line start with `!` symbol, indicates that the directory or file (following the `!` symbol) must not be synchronised.

    - `!/<sub_directory>/` - do not sync the `<sub-directory>` sub-folder. Examples: 

        - If `[DriveD:/src/ -> src/]` line is followed by `!/build/`, means `DriveD:/src/build/` must not be synchronised.

        - If `[DriveD:/src/ -> src/]` line is followed by `!/tmp*/`, means all folders in `DriveD:/src/` with name starting with `tmp` must not be synchronised. But this rule does not apply to sub-folders. For example `DriveD:/src/other/tmp123/` is not ignored.

    - `!*/<directory>/` - do not sync any sub-folders (at any level) with name `<directory>`. Examples:

        - If `[DriveD:/src/ -> src/]` line is followed by `!*/build/`, means any sub-directory (at any level) inside of `DriveD:/src/` having the name `build` must not be synchronised. 

        - If `[DriveD:/src/ -> src/]` line is followed by `!*/build*/`, means any sub-directory (at any level) inside of `DriveD:/src/` having name starting with `build` must not be synchronised. 

    - `!/<file>` - do not sync the `<file>` at a specific location. Examples:

        - If `[DriveD:/src/ -> src/]` line is followed by `!/cli/unused.h`, means `DriveD:/src/cli/unused.h` must not be synchronised.

        - If `[DriveD:/src/ -> src/]` line is followed by `!/cli/unused*`, means all files in `DriveD:/src/cli/` with name starting with `unused` must not be synchronised. But this rule does not apply to sub-folders. For example `DriveD:/src/other/cli/unused123/` is not ignored.

    - `!*/<file>` - do not sync the `<file>` (at any level). Examples:

        - If `[DriveD:/src/ -> src/]` line is followed by `!*/make.cmake`, means any file (at any level) inside of `DriveD:/src/` having the name `make.cmake` must not be synchronised. 

        - If `[DriveD:/src/ -> src/]` line is followed by `!*/*.cmake`, means any file (at any level) inside of `DriveD:/src/` having name ending with `.cmake` must not be synchronised. 


### UI

- MyBackUpSync does not use graphical elements and is implemented entirely using text characters in the terminal (command line).

- The style must resamble the style of a "FAR" File Manager.

- The frames, the tree structure, the scroll-box and the progress bar must be drawn with the special characters used by the "FAR" File Manager 2/3: the Unicode box drawing and block element glyphs (`U+2500` - `U+259F`), listed in the internal FAR table `BOX_DEF_SYMBOLS` (`far/interf.hpp`).

    - The Main Pane uses the single line glyphs (`┌─┐│└┘`), the dialogs use the double line glyphs (`╔═╗║╚╝`), the tree uses `├─`, `└─` and `│`, the scroll-box uses `▲`, `▼`, `░` and `█`.

    - If the terminal is not able to display those glyphs, MyBackUpSync falls back to the equivalent plain ASCII characters (`+`, `-`, `|`, `#`).

- The majority of the space occupies the list of all differences (files and folders that are different between computer's hard drive and backup drive) that must be synchronised. This is the 'Main Pane'.

- The list of commands are located at the bottom of the screen. This is the 'Bottom Pane'.

#### Main Pane

The Main Pane contains a list of differences (files and folders that are different between computer's hard drive and backup drive) that must be synchronised. 

- Every line is a directory or a file which is different or missing (between computer's hard drive and backup drive). 

- One line represents 'The Cursor', it has a brighter Font (compared to other lines). Using the keyboard arrows up and down the User can navigate throught the list of differences (directories and files) in the Main Pane. 

- Every line is displayed like: `[ ] -> <mark> <file_or_directory_name>   <size>`: 

    - Where the first element (`[ ]`) is a 'Check Box' that the User can select (`[X]`) or unselect (`[ ]`) using the space-bar. The selection is applied to the file or directory the cursor points to.

    - If a file is selected (`[X]`) the corresponding file is marked as 'to be synchronised' (to be copied to other drive or delted, depending on action the user selects).

    - If the User selects again an already selected file - it is unselected (`[ ]`).

    - If a directory line is selected (`[X]`) the corresponding directory and all sub-directories and files are marked as 'to be synchronised' (to be copied to other drive or delted, depending on action the user selects).
    
    - If the User selects again an already selected directory - the corresponding directory and all sub-directories and files are unselected (`[ ]`).

    - The second element `->` is an arrow which shows the direction where the file or directory must be copied. To the right `->`: if it is different or missing on backup drive, or to the left `<-` if it is missing on computer's drive.

    - If a directory contains files that must be copied in both directions (some files to backup drive and some files from backup drive), the arrow in front of directory name is displayed like `<>`.

    - The third element `<mark>` shows whether the leafs (files and sub-directories) of a directory are hidden or displayed: `+` if they are hidden, `-` if they are displayed. For a file, and for a directory without leafs, a space is displayed.

    - The fourth element `<file_or_directory_name>` is the name of the file or directory to be synchronised.The name of the directory ends with `/`.

    - The fifth element `<size>` is the size of the file. If it is a directory, the size is not displayed.

- By default the leafs (files and sub-directories) of every directory are hidden, therefore only the directories listed in the Configuration File that still contain a difference are displayed.

- If the User presses the `Enter` key when the Cursor points to a directory, the leafs of that directory are displayed. If the User presses `Enter` again, the leafs are hidden again.

- Hiding the leafs of a directory does not change the selection (`[X]`) nor the direction of its content: a hidden file is still copied or deleted when its parent directory is selected.

- The files and directories are shown in a "Tree-like" structure. The sub-directories and files of a directory are displayed as leafs:

```
[ ] -- - DirectoryName1/
 ├─[ ] <> - Sub-Directory1/
 │  ├─[ ] ->   File11          123Kb
 │  ├─[ ] <-   File12           234b
 │  └─[ ] ->   File13           23Kb
 └─[ ] <- - Sub-Directory2/
    ├─[ ] <- + Sub-Directory21/
    ├─[ ] ->   File22          678Mb
    └─[ ] <-   File23            1Gb
```

In the example above `Sub-Directory1/` and `Sub-Directory2/` display their leafs (`-`), while the leafs of `Sub-Directory21/` are hidden (`+`).

- At the right side of the Main Pane is a scroll-box showing the content of the Main Pane relatively to the entire list.

#### Bottom Pane

The Bottom Pane is located at the bottom of the screen. It displays all the available commands. It looks like:

```
[F1 Refresh][F4 List][F5 Copy][F8 Delete][F9 Collapse All][F10 Quit]
```

- `F9` hides or displays the leafs of all the directories at once. While at least one directory displays its leafs the command is shown as `[F9 Collapse All]`; once every directory is hidden it is shown as `[F9 Expand All]`.

#### Shortkeys and navigation

The following actions are available using keyboard:

- Up/Down: move the Cursor one line up and down in the list of differences in Main Pane.
- PageUp/PageDown: move the Cursor one screen up and down in the list of differences in Main Pane.
- Left or Backspace: move the Cursor one level up (parent directory) in the list of differences in Main Pane.
- Pos1/End: move the Cursor at the beginning/end in the list of differences in Main Pane.
- Spacebar: toggle selection of a file or directory (and its content) where the Cursor points to.
- Enter: if the Cursor points to a directory, hide or display its leafs (files and sub-directories) in the Main Pane. By default the leafs of all directories are hidden.
- F1 Refresh: re-check again the content of computer's hard drive and backup hard drive and re-generate the list of differences.
- F4 List: generates a temporary text file containing the list of all differences, display the message where the file was saved. The generated text file must have the same format like the list displayed in the Main Pane.
- F5 Copy:
    - If there are more files/directories selected (`[X]`), only the selected files/directories are copied, regardless of the Cursor position.
    - If there are no files/directories selected (`[X]`), the file/directory where Cursor points to is copied.
- F8 Delete:
    - If there are more files/directories selected (`[X]`), only the files/directories are deleted, regardless of the Cursor position.
    - If there are no files/directories selected (`[X]`), the file/directory where Cursor points to is deleted.
- F9 Collapse All / Expand All: hide the leafs of all the directories in the Main Pane. If the leafs of all the directories are already hidden, display them all instead.

#### Actions and confirmations

All actions that copy or delete files/directories must be confirmed by the user. In this case a list is displayed on top of the Main Pane containing all files/directories and the action to be done (copy or delete), and two options `[Ok]` and `[Cancel]`. If the User selects `[Ok]`, the action is performed. If the User selects `[Cancel]`, the action is aborted.

## Test

`Test` folder contains an example of a computer's hard drive (`DriveC/`) and a backup hard drive (`DriveE/`). `DriveE/mybackupsync.config` has the rules that have been already applied and the both drives (`DriveC/` and `DriveE/`) are completelly synchronised. This can be used as an example.
