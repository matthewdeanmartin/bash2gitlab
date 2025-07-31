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
- Shred supports job-level variables
- Shred automatically includes if-block to include job level and global variables.
- Shred generates mock CI variables file
- init command to generate config file

## [0.3.0] - 2025-07-27

### Added

- Option to use toml config file or envvar config instead of CLI switches

### Fixed

- Python 3.14 support fixed.

## [0.2.0] - 2025-07-27

### Added

- shred command to turn pre-existing bash-in-yaml pipeline templates into shell files and yaml

## [0.1.0] - 2025-07-26

### Added

- compile command exists
- verbose and quiet logging
- CLI interface
- supports simple in/out project structure
- supports corralling scripts and templates into a scripts or templates folder, which confuses path resolution 