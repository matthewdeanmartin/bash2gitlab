# bash2gitlab

> Compile pure Bash scripts into your `.gitlab-ci.yml`. Get IDE support for your scripts while keeping them
> centralized.

Tired of writing Bash inside YAML strings with no syntax highlighting, linting, or testing? `bash2gitlab` lets you
develop your CI logic in `.sh` files and then compiles them into your GitLab CI configuration, giving you the
best of both worlds.

Bash in YAML is Bash without quality gates. Also, includes support for inlining a large number of scripts from other
language, from Python to PHP.

[![tests](https://github.com/matthewdeanmartin/bash2gitlab/actions/workflows/build.yml/badge.svg)
](https://github.com/matthewdeanmartin/bash2gitlab/actions/workflows/tests.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/matthewdeanmartin/bash2gitlab/main.svg)
](https://results.pre-commit.ci/latest/github/matthewdeanmartin/bash2gitlab/main)
[![Downloads](https://img.shields.io/pypi/dm/bash2gitlab)](https://pypistats.org/packages/bash2gitlab)
[![Python Version](https://img.shields.io/pypi/pyversions/bash2gitlab)
![Release](https://img.shields.io/pypi/v/bash2gitlab)
](https://pypi.org/project/bash2gitlab/)

______________________________________________________________________

## Before

Surely Gitlab has a solution for this? Not as far as I can
tell. [Here are some of my best workarounds](https://gitlab.com/matthewdeanmartin/includes_templates).

Your IDE sees a single YAML string, and your scripts are trapped in one file.

`.gitlab-ci.yml`:

```yaml
build-job:
  script:
    - echo "Building project"
    - make build
```

## After

Your IDE provides full support for Bash, and your scripts can be versioned, shared, and tested independently.

`scripts/build.sh`:

```bash
#!/usr/bin/env bash
set -eo pipefail

echo "Building project"
make build
```

`uncompiled.gitlab-ci.yml`:

```yaml
build-job:
  script:
    - ./scripts/build.sh
```

Run `bash2gitlab compile`, and the final, valid `.gitlab-ci.yml` is generated for you.

______________________________________________________________________

## Who is this for?

This tool is for you if:

- You manage CI/CD templates in a centralized repository and `include:` them in many other projects.
- Your `.gitlab-ci.yml` files contain thousands of lines of shell scripts.
- You want to write, test, and debug your CI scripts locally without involving Docker or a full pipeline simulation.
- Your IDE's lack of Bash support in YAML files is slowing you down.
- You want to be able to put Python or other non-Bash scripts into your shared templates.

If your CI/CD configuration is simple or contained entirely within a single repository, you might not need this tool.

## Installation

`bash2gitlab` is a standalone command-line tool. Installation with `pipx` is recommended to avoid dependency conflicts.

Install `[all]` extras for all commands. On your build server install just `bash2gitlab` for the core libraries which
allows you to run `compile`, `decompile` on server. This minimizes supply chain risks.

```bash
# Recommended
pipx install bash2gitlab[all]

# Or via pip
pip install bash2gitlab[all]
```

## Getting Started: A Quick Tour

1. **Initialize Your Project**
   Run `bash2gitlab init` to create a configuration file (`.bash2gitlab.toml`) and directories to organize your source
   files.

1. **Decompile an Existing Configuration**
   If you have an existing `.gitlab-ci.yml` with inline scripts, you can extract them automatically:

```bash
bash2gitlab decompile --in-file .gitlab-ci.yml --out my-project/
```

3. **Write and Edit Your Scripts**
   Create or edit your `.sh` files in the `scripts` directory. Write standard, clean Bash—your IDE will thank you. In
   your source YAML (`uncompiled.yml`):

```yaml
my-job:
  script:
    - ./scripts/my-script.sh
```

4. **Compile**
   Compile your source YAML and scripts into a final, GitLab-ready configuration:

```bash
bash2gitlab compile --in my-project/ --out compiled/
```

This generates a `compiled/.gitlab-ci.yml` file, ready to be deployed to your project's root.

## Usage and Commands

`bash2gitlab` provides a few core commands to manage your workflow.

Run with

- bash2gitlab for CLI
- bash2gitlab-interactive for CLI question and answer
- bash2gitlab-tui for Terminal UI
- bash2gitlab-gui for GUI

### Core Compile/Decompile

| Command     | Description                                                                |
|:------------|:---------------------------------------------------------------------------|
| `compile`   | Compiles source YAML and `.sh` files into a final `.gitlab-ci.yml`.        |
| `decompile` | Extracts inline scripts from a `.gitlab-ci.yml` into separate `.sh` files. |

### Debugging from remote repo

| Command      | Description                                                                    |
|:-------------|:-------------------------------------------------------------------------------|
| `copy2local` | Copies compiled files from a central repo to a local project for testing.      |
| `map-deploy` | Copies compiled files from a central repo to a many local project for testing. |
| `commit-map` | Copies intential changes in local projects back to the central repo.           |

### Setup

| Command               | Description                                              |
|:----------------------|:---------------------------------------------------------|
| `init`                | Initializes a new `bash2gitlab` project and config file. |
| `clean`               | Carefully delete output in target folder.                |
| `install-precommit`   | Add git hook to compile before commit                    |
| `uninstall-precommit` | Remove precommit hook                                    |

### Diagnostics

| Command             | Description                                                      |
|:--------------------|:-----------------------------------------------------------------|
| `lint`              | Call GitLab APIs to lint your YAML                              |
| `detect-drift`      | Report what unexpected changes were made to the generated files. |
| `show-config`       | Display config after cascade                                     |
| `doctor`            | Look for environment problems                                    |
| `graph`             | Generate graph of inline relationships                           |
| `detect-uncompiled` | Detect if you forgot to compile                                  |
| `validate`          | Validate JSON schema of all YAML in input and output             |

### Other

| Command             | Description                                                               |
|:--------------------|:--------------------------------------------------------------------------|
| `check-pins`        | Analyze GitLab CI include: statements and suggest pinning to tags        |
| `trigger-pipelines` | Trigger pipelines in GitLab projects and optionally wait for completion  |

### Simulate Gitlab Pipeline Locally

| Command | Description                                                                         |
|:--------|:------------------------------------------------------------------------------------|
| `run`   | Best efforts to run bash in a .gitlab-ci.yml file in similar order as a real runner |

For detailed options on any command, run `bash2gitlab <command> --help`.

______________________________________________________________________

## Advanced Topics

#### Bash Completion

Enable tab completion in your shell by running the global activation command once:

```bash
activate-global-python-argcomplete
```

#### Global Variables

To define variables that should be inlined into the global `variables:` block of your `.gitlab-ci.yml`, create a
`global_variables.sh` file in your input directory.

#### Limitations

- **No `include:` Inlining:** This tool only inlines `.sh` file references. It does not process or merge GitLab's
  `include:` statements for other YAML files.
- **Single Statement Invocations:** The script invocation must be on its own line. Multi-statement lines like
  `echo "hello" && script.sh` are not supported.
- **Comments:** Comments in the source YAML may not be preserved in the final compiled output.

## How It Compares

- **[gitlab-ci-local](https://github.com/firecow/gitlab-ci-local):** This is an excellent tool for running your entire
  GitLab pipeline in local Docker containers. `bash2gitlab` is different—it focuses on the "unit testing" of your Bash
  logic itself, assuming you can and want to execute your scripts on your local machine without the overhead of Docker.
- **GitHub Actions
  ** [GitHub composite actions](https://docs.github.com/en/actions/concepts/workflows-and-actions/reusable-workflows)
  do not have this problem. A shared GitHub action can reference a script in the shared action's repo. A GitHub
  "reusable" workflow is a single yaml file and might suffer from the same problem as Gitlab pipelines.
- **Git Submodules** Build runners will need permissions to clone and git is more complicated to use.
- **Base image holds all bash** You can only have one base image, so if you are using it for bash and yaml, you can't
  use other base images.
- **Trigger remote pipeline** A remote pipeline has access to the shell files in its own repo.

## Project Health & Info

| Metric            | Health                                                                                                                                                                                                            | Metric          | Info                                                                                                                                                                                                            |
|:------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:----------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Tests             | [![Tests](https://github.com/matthewdeanmartin/bash2gitlab/actions/workflows/build.yml/badge.svg)](https://github.com/matthewdeanmartin/bash2gitlab/actions/workflows/build.yml)                                  | License         | [![License](https://img.shields.io/github/license/matthewdeanmartin/bash2gitlab)](https://github.com/matthewdeanmartin/bash2gitlab/blob/main/LICENSE.md)                                                        |
| Coverage          | [![Codecov](https://codecov.io/gh/matthewdeanmartin/bash2gitlab/branch/main/graph/badge.svg)](https://codecov.io/gh/matthewdeanmartin/bash2gitlab)                                                                | PyPI            | [![PyPI](https://img.shields.io/pypi/v/bash2gitlab)](https://pypi.org/project/bash2gitlab/)                                                                                                                     |
| Lint / Pre-commit | [![pre-commit.ci status](https://results.pre-commit.ci/badge/github/matthewdeanmartin/bash2gitlab/main.svg)](https://results.pre-commit.ci/latest/github/matthewdeanmartin/bash2gitlab/main)                      | Python Versions | [![Python Version](https://img.shields.io/pypi/pyversions/bash2gitlab)](https://pypi.org/project/bash2gitlab/)                                                                                                  |
| Quality Gate      | [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=matthewdeanmartin_bash2gitlab\&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=matthewdeanmartin_bash2gitlab)    | Docs            | [![Docs](https://readthedocs.org/projects/bash2gitlab/badge/?version=latest)](https://bash2gitlab.readthedocs.io/en/latest/)                                                                                    |
| CI Build          | [![Build](https://github.com/matthewdeanmartin/bash2gitlab/actions/workflows/build.yml/badge.svg)](https://github.com/matthewdeanmartin/bash2gitlab/actions/workflows/build.yml)                                  | Downloads       | [![Downloads](https://static.pepy.tech/personalized-badge/bash2gitlab?period=total\&units=international_system\&left_color=grey\&right_color=blue\&left_text=Downloads)](https://pepy.tech/project/bash2gitlab) |
| Maintainability   | [![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=matthewdeanmartin_bash2gitlab\&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=matthewdeanmartin_bash2gitlab) | Last Commit     | ![Last Commit](https://img.shields.io/github/last-commit/matthewdeanmartin/bash2gitlab)                                                                                                                         |

| Category        | Health                                                                                               
|-----------------|------------------------------------------------------------------------------------------------------|
| **Open Issues** | ![GitHub issues](https://img.shields.io/github/issues/matthewdeanmartin/bash2gitlab)                 |
| **Stars**       | ![GitHub Repo stars](https://img.shields.io/github/stars/matthewdeanmartin/bash2gitlab?style=social) |
