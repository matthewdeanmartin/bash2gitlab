# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.10.1] - 2026-04-15

### Fixed
- Load the bundled GitLab CI schema correctly after the package rename and cache it for offline validation.

## [0.10.0] - 2026-03-17

### Changed
- Rename package to bash2yaml. GitLab is a trademark and subject to GitLab's trademark policies. Rather than figure out how to comply, the name is changing. This is also in preparation for supporting GitHub Actions and other bash-in-yaml build scripts. bash2gitlab will be left up on PyPI, but future releases will be published as bash2yaml only. The userbase is approximately zero, so this should not be disruptive.

## [0.9.10] - 2026-03-01

### Added
- Python 3.14 support.
- Pragma: inline-artifact directive for inlining zipped folders.
- `--totalhelp` switch to list all available help text.

### Fixed
- Bad CLI switches fixed.

## [0.9.9] - 2025-09-29

### Fixed
- Include the GitLab library in the distribution.

### Added
- `autogit` command and associated switches.

## [0.9.8] - 2025-09-05

### Fixed
- Wrong bash return value for `detect-uncompiled` command.
- Fix other ad hoc return values throughout CLI.

### Added
- `check-pins` command to attempt to upgrade `include:` elements to the latest hash or git tag.

## [0.9.7] - 2025-09-01

### Fixed
- Improve startup performance with lazy loading via rtoml.
- Fix caching logic for the update checker.

## [0.9.6] - 2025-09-01

### Fixed
- Load JSON schema from cache first, then URL, then bundled resource.
- Prime schema cache before attempting multi-threaded validation.

## [0.9.5] - 2025-08-28

### Fixed
- Backwards compatibility fixes for Python 3.8 and earlier minor versions.

## [0.9.4] - 2025-08-28

### Added
- New `validate` command to validate YAML against JSON schema without requiring a full compile.

### Changed
- Add dependency on orjson and urllib3 for speed, and tomli for backwards compatibility.

### Fixed
- Performance improvements throughout.

## [0.9.3] - 2025-08-27

### Fixed
- Fix `detect-drift` argument parsing failure. Validate with more comprehensive basic_check.sh test.

## [0.9.2] - 2025-08-24

### Fixed
- Replace ad hoc error handling in CLI code with `sys.exit` and numeric exit codes; use Python exceptions everywhere else.
- Improve error reporting when running gui, tui, or interactive modes without installing the `[all]` extra.
- Add `set -eo pipefail` to best-effort runner scripts to stop execution on errors.
- Remove unnecessary `required=True` from `--gitlab-url` lint argument.
- Refactor bash inliner to delegate shebang stripping to `inline_bash_source` and simplify `read_bash_script`.
- Improve internal build and CI configuration.

## [0.9.1] - 2025-08-23

### Fixed
- Reduce likelihood of import errors in core mode. Make install help text vertically more compact.
- Fix `doctor` command.

## [0.9.0] - 2025-08-22

### Changed
- Split installation into `bash2gitlab` for core (suitable for CI/build servers) and `bash2gitlab[all]` for all commands on a local workstation. This minimizes supply chain risk by keeping the core dependency footprint very small.

### Added
- CLI option `bash2gitlab run --in-file .gitlab-ci.yml` for best-effort local pipeline execution. This is not a real runner.

## [0.8.22] - 2025-08-22

### Changed
- `map-deploy` writes compiled files to multiple destination folders.
- `map-commit` gathers changes from multiple folders; does not handle conflicts yet.

### Added
- Best-effort local runner to attempt execution of a `.gitlab-ci.yml` without a real GitLab runner.

## [0.8.21] - 2025-08-20

### Added
- `# Pragma: do-not-validate-schema` directive for jobs using `!reference`. GitLab merges all templates before JSON schema validation.

## [0.8.20] - 2025-08-20

### Fixed
- Fix regression where YAML `stages` blocks were turned into string blocks.

### Added
- Validate YAML against the GitLab JSON schema during compile. Validation results are always reported.

## [0.8.19] - 2025-08-20

### Fixed
- Fix regression where scripts were serialized as quoted YAML lists. Add unit tests to cover the behavior.

### Added
- Skip compile when no changes have been made since the last compile to any file in the input folder.

## [0.8.18] - 2025-08-19

### Fixed
- Fix variable lists being turned into string blocks and `!reference` tags being turned into plain lists.

## [0.8.17] - 2025-08-18

### Fixed
- Fix `graph` command to retry alternative renderers when graphviz is unavailable.
- Fix `graph` command to handle UTF-8 errors gracefully.
- Fix `lint` command to read `gitlab_url` from config when not supplied on the CLI.
- Fix `Pragma` directive feature in the inliner.
- Fix Tkinter GUI tab-switching after running a command.
- Suppress color logging inside GUI and TUI subprocess calls.
- Extract second bash reader module (`bash_reader2.py`) to improve inlining reliability.

## [0.8.16] - 2025-08-17

### Changed
- Improve documentation, docstrings, and help text.
- Extend `init` command to cover all configuration options.

## [0.8.15] - 2025-08-17

### Added
- Interactive mode via `bash2gitlab-interactive` command.
- GUI via `bash2gitlab-gui` command.
- Pragma directives to control inlining behavior: `do-not-inline`, `do-not-inline-next-line`, `start-do-not-inline`, `end-do-not-inline`, and `allow-outside-root`.

### Changed
- Rename `shred` command to `decompile`.
- Update config file to support storing almost all command options.

## [0.8.14] - 2025-08-16

### Added
- Textual TUI interface mirroring the CLI.
- Generate a makefile when running the `decompile` command.

## [0.8.13] - 2025-08-15

### Fixed
- Fix incorrect CLI argument validation in `decompile` command.

### Changed
- `graph` command now attempts alternative graphing styles when graphviz is not available.

## [0.8.12] - 2025-08-15

### Added
- `graph` command to visualize inline relationships.
- `doctor` command for environment diagnostics.
- `show-config` command to display the resolved cascading configuration.

### Fixed
- `decompile` now writes output to a folder.
- `decompile` accepts `--in-file` or `--in-folder`.
- `decompile` records `!reference [.job, key]` as a bash comment.
- `decompile` logs with paths relative to the YAML file, not cwd.
- Fix leading `.` being stripped from generated filenames.

## [0.8.11] - 2025-08-14

### Added
- `install-precommit` and `uninstall-precommit` commands to manage git pre-commit hooks that compile before commit.
- Pluggy plugin support.
- Extended script language inlining support for a much larger set of interpreters using `interpreter -c "..."` invocations.

## [0.8.10] - 2025-08-12

### Fixed
- Minimize all "script as YAML lists" representations because they are incompatible with line continuation characters.

## [0.8.9] - 2025-08-11

### Fixed
- Fix loss of all newlines in output scripts.

## [0.8.8] - 2025-08-11

### Added
- Support for inlining non-bash languages (Python, etc.) using `python -c` and equivalent interpreter invocations.

### Fixed
- Force a trailing newline at the end of every inlined script.
- Minimize bash written as `- code` YAML lists to reduce quoting problems.
- Quote strings more aggressively to prevent YAML interpretation issues.

## [0.8.7] - 2025-08-10

### Added
- `clean` command to remove only unmodified files from the output folder.
- Check for stray files in the output folder before compiling.
- `lint` command (beta) for calling GitLab APIs to validate YAML.

### Changed
- Detect file invocations that are followed by a comment.
- Remove the concept of script folder and template folder in favor of a single input folder and output folder.

### Removed
- Global variable file feature removed pending a rethink.

### Fixed
- Avoid rewriting output files when no changes have occurred.

## [0.8.6] - 2025-08-09

### Changed
- Restrict `map-deploy` and `map-commit` operations to `.sh`, `.ps1`, and `.y[a]ml` files.

### Added
- `map-commit` CLI command.
- Suggestions for incorrect CLI commands.

## [0.8.5] - 2025-08-08

### Added
- `map-deploy` feature to copy compiled files to multiple destination projects.

### Changed
- Discourage excessive quoting in generated output.

### Fixed
- Gracefully degrade when a generated YAML file has been hand-edited into invalid YAML.

## [0.8.4] - 2025-08-06

### Added
- Embed the compile command used in the generated file header.
- `detect-drift` command to report unexpected changes made to generated files outside of compile.

### Fixed
- Fix bug that stringified certain complex values in YAML maps.

## [0.8.3] - 2025-08-05

### Added
- Basic PowerShell (`.ps1`) file support.

### Fixed
- Fix bug in `copy2local` command.

## [0.8.2] - 2025-08-05

### Added
- Check for updated package version on PyPI at startup.

### Changed
- `copy2local` now copies the contents of the source folder directly into the destination folder to reduce nesting.

## [0.8.1] - 2025-08-05

### Added
- Improve logging output.

## [0.8.0] - 2025-08-04

### Added
- Inline bash scripts referenced via `source script.sh` using the same logic as inlining bash into YAML.

### Changed
- Rename `clone2local` to `copy2local`, using archive and copy commands to get a portion of a remote repo into a dependent repo for testing.

### Fixed
- Fix bug where multiple script references in a script list were all overwritten by the last script.

## [0.7.0] - 2025-08-02

### Added
- Initial `clone` feature for sparse-cloning scripts into dependent repos for testing. Not fully baked yet.

### Removed
- Remove `--format` option. Major YAML formatting tools are in various states of unsupportedness and cause failures unrelated to bash2gitlab output.

## [0.6.0] - 2025-07-30

### Changed
- Update hash algorithm to base64-encode the whole YAML document so that reformats with more than whitespace changes are detected correctly.

### Fixed
- Loosely detect YAML anchors, assuming all hashes with a list value and a `./script.sh` pattern are script anchors.
- Detect jobs that have only `before_script` or `after_script`.

## [0.5.1] - 2025-07-30

### Fixed
- Preserve long lines without wrapping.
- Remove leading blank lines from scripts to avoid indentation indicators such as `|2-`.

## [0.5.0] - 2025-07-29

### Added
- Modification detection feature that warns when compiled output has been changed outside of compile.

### Fixed
- Process YAML files in subfolders correctly.

## [0.4.1] - 2025-07-27

### Fixed
- Fix command line aliases to `bash2gitlab` and `b2gl`, removing earlier copy-paste errors.

## [0.4.0] - 2025-07-27

### Added
- Watch mode (`--watch`) to recompile automatically on file changes.
- `decompile` support for job-level variables, auto-generated if-blocks for including variables, and mock CI variable file generation.
- `init` command to generate a configuration file.

## [0.3.0] - 2025-07-27

### Added
- Support for TOML config file and environment variable configuration as alternatives to CLI switches.

### Fixed
- Fix Python 3.14 compatibility.

## [0.2.0] - 2025-07-27

### Added
- `decompile` command to convert pre-existing bash-in-YAML pipeline templates into separate shell files and YAML.

## [0.1.0] - 2025-07-26

### Added
- Initial `compile` command and CLI interface.
- Verbose and quiet logging modes.
- Support for simple input/output project structure.

[0.10.1]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.10.0...v0.10.1
[0.10.0]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.9.10...v0.10.0
[0.9.10]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.9.9...v0.9.10
[0.9.9]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.9.8...v0.9.9
[0.9.8]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.9.7...v0.9.8
[0.9.7]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.9.6...v0.9.7
[0.9.6]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.9.5...v0.9.6
[0.9.5]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.9.4...v0.9.5
[0.9.4]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.9.3...v0.9.4
[0.9.3]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.22...v0.9.0
[0.8.22]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.21...v0.8.22
[0.8.21]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.20...v0.8.21
[0.8.20]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.19...v0.8.20
[0.8.19]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.18...v0.8.19
[0.8.18]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.17...v0.8.18
[0.8.17]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.16...v0.8.17
[0.8.16]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.15...v0.8.16
[0.8.15]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.14...v0.8.15
[0.8.14]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.13...v0.8.14
[0.8.13]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.12...v0.8.13
[0.8.12]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.11...v0.8.12
[0.8.11]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.10...v0.8.11
[0.8.10]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.9...v0.8.10
[0.8.9]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.8...v0.8.9
[0.8.8]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.7...v0.8.8
[0.8.7]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.6...v0.8.7
[0.8.6]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.5...v0.8.6
[0.8.5]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.4...v0.8.5
[0.8.4]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.3...v0.8.4
[0.8.3]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.5.1...v0.6.0
[0.5.1]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/matthewdeanmartin/bash2gitlab/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/matthewdeanmartin/bash2gitlab/releases/tag/v0.1.0
