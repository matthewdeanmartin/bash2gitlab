# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

- Added for new features.
- Changed for changes in existing functionality.
- Deprecated for soon-to-be removed features.
- Removed for now removed features.
- Fixed for any bug fixes.
- Security in case of vulnerabilities.

## [0.8.15] - 2025-08-16

### Added

- Interactive mode via bash2gitlab-interactive

### Changed

- Inline supports Pragma commands to skip certain bash from being in-lined.
    - `# Pragma: do-not-inline`: Prevents inlining on the current line.
    - `# Pragma: do-not-inline-next-line`: Prevents inlining on the next line.
    - `# Pragma: start-do-not-inline`: Starts a block where no inlining occurs.
    - `# Pragma: end-do-not-inline`: Ends the block.
    - `# Pragma: allow-outside-root`: Bypasses the directory traversal security check.

## [0.8.14] - 2025-08-16

### Added

- Basc textual TUI added to mirror the CLI interface
- Generates makefile for decompile command

## [0.8.13] - 2025-08-15

### Fixed

- Decompile command had wrong CLI argument validation

### Changed

- `graph` command will attempt other graphing styles if graphviz not available.

## [0.8.12] - 2025-08-14

### Added

- Graph command
- Doctor command for diagnostics
- Show config command to show how cascading config resolves

### Fixed

- Decompile write to a folder now.
- Decompile will take --in-file or --in-folder
- Decompile records `!reference [.job, key]` as bash comment
- Decompile now logs with relative path.
- Decompile should now use path relative to yaml not cwd
- Leading `.` got stripped from file names. Fixed

## [0.8.11] - 2025-08-14

### Added

- Install/uninstall git precommit hooks to compile before commit (not integrated with the popular pre-commit tool).
  Support for
  integration with the `pre-commit` tool is on the way.
- Pluggy support for plugins

### Changed

- Now support inlining a much larger list of script languages using variations on `intepreter -c "..."`

## [0.8.10] - 2025-08-11

### Fixed

- Minimize all "script as yaml lists" because they are not compatible with line continuation characters. No one should
  use any version of bash2gitlab before 0.8.10.

## [0.8.9] - 2025-08-11

### Fixed

- Lost all new lines.

## [0.8.8] - 2025-08-11

### Added

- Support for inlining other languages, python, etc. using `python -c`, etc.

### Fixed

- Force new line at the end of any script.
- Minimize bash written in `- code` lists because of risk of quoting problems.
- Quote strings more aggressively

## [0.8.7] - 2025-08-10

### Changed

- File invocations followed by comment are now detected.
- Concept of script folder and template folder gone. Input folder and output folder is enough.

### Removed

- Global variable file feature is broken, will need to rethink

### Added

- Clean command that only removes unmodified files from output folder
- Checks for stray files in output folder before compiling
- Lint command, but it is in "beta" testing

### Fixed

- No longer rewrites files even when there are no changes

## [0.8.6] - 2025-08-09

### Changed

- Map deploy and map commit now restricted to .sh, .ps1 and .y\[a\]ml files.

### Added

- Map commit CLI available.
- Suggestions on incorrect cli command

## [0.8.5] - 2025-08-08

### Changed

- Discourage excessive quotes

### Fixed

- Gracefully degrade if someone changes generated yaml to invalid yaml.

### Added

- Map deploy started.

## [0.8.4] - 2025-08-06

### Added

- Shows command used to generate in the header
- Added "detect-drift" command, to complement the existing drift detection that runs at compile time.

### Fixed

- Bug that stringified certain complex values in yaml maps.

## [0.8.3] - 2025-08-05

### Added

- Basic ps1 file support

### Fixed

- Fixed bug with copy2local

## [0.8.2] - 2025-08-05

### Added

- Checks for updated package from pypi.

### Changed

- copy2local now copies the contents of src folder to destination folder, to reduce nesting.

## [0.8.1] - 2025-08-05

### Added

- Improve logging

## [0.8.0] - 2025-08-04

### Added

- Inlines bash by same logic as inlining bash into yaml. Looks for `source script.sh` and inlines it.

### Changed

- clone2local is now copy2local using archive and copy commands to get a part of your remote repo into a dependent
  report for testing.

### Fixed

- Reference or multiple scripts in a script list would all be stomped by last script.

## [0.7.0] - 2025-08-02

### Added

- Started work on a clone feature to get scripts into dependent repos for testing. Not fully baked yet.

### Removed

- A `--format` option was a bad idea because all of the major yaml formatting tools are in various states of
  unsupportedness and cause failures unrelated to bash2gitlab's outputs. Use your favorite orchestration tool, such as
  make or just to format with a yaml formatter that works for you.

## [0.6.0] - 2025-07-30

### Changed

- Hash is now a bash64 encode of whole yaml document so reformats with more than just whitespace changes can be detected
  correctly

### Fixed

- Loosely detect anchors (assumes all hashes with a list value and ./script.sh pattern are script anchors)
- Detects jobs with only before_script or after_script

## [0.5.1] - 2025-07-30

### Fixed

- Preserve long lines
- Remove leading blank lines from scripts to avoid indentation indicators (e.g. `|2-`)

## [0.5.0] - 2025-07-29

### Fixed

- Subfolders with yaml files are now processed

### Added

- Started a feature to detect modification, currently warns and doesn't stop.

## [0.4.1] - 2025-07-27

### Fixed

- Command line aliases are now bash2gitlab and b2gl. Previously had some copy-paste junk.

## [0.4.0] - 2025-07-27

### Added

- Watch mode (--watch) to recompile on file changes
- Decompile supports job-level variables
- Decompile automatically includes if-block to include job level and global variables.
- Decompile generates mock CI variables file
- init command to generate config file

## [0.3.0] - 2025-07-27

### Added

- Option to use toml config file or envvar config instead of CLI switches

### Fixed

- Python 3.14 support fixed.

## [0.2.0] - 2025-07-27

### Added

- decompile command to turn pre-existing bash-in-yaml pipeline templates into shell files and yaml

## [0.1.0] - 2025-07-26

### Added

- compile command exists
- verbose and quiet logging
- CLI interface
- supports simple in/out project structure
- supports corralling scripts and templates into a scripts or templates folder, which confuses path resolution 