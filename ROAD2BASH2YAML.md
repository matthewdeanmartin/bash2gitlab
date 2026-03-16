# Road to bash2yaml

## Overview

This document describes the plan to evolve `bash2yaml` into `bash2yaml` — a multi-platform CI/CD script compilation
tool. The core idea stays the same: write your scripts in real files, compile them into CI YAML. The expansion: support
GitLab CI, GitHub Actions, CircleCI, AWS CodeBuild (`buildspec.yml`), Bitbucket Pipelines, and Semaphore CI.

---

## What We Have Today (bash2yaml)

**Core concept:** Read an "uncompiled" YAML file where CI job `script:` blocks contain references to `.sh` files. Inline
those script files recursively. Validate the result against an official schema. Write the compiled output.

**Key subsystems:**

- `compile_all.py` — orchestrates compilation
- `compile_bash_reader.py` — recursive bash/source inlining
- `compile_not_bash.py` — Python/Node/Ruby/etc inlining
- `config.py` — hierarchical config (toml + env vars)
- `plugins.py` / `hookspecs.py` — pluggy extension points
- `validate_pipeline.py` — jsonschema validation against GitLab's schema
- `decompile_all.py` — reverse: extract inlined scripts back to files
- YAML handled with `ruamel.yaml` to preserve comments, anchors, formatting

---

## The Multi-Platform Problem

Each CI platform has a different YAML structure. They all share the same fundamental need: shell commands live inside
YAML strings. The compilation logic (find script reference → inline content) is platform-agnostic. The differences are:

| Platform            | Output File                | Script sections                                                       | Variables section                       | Validation                          |
|---------------------|----------------------------|-----------------------------------------------------------------------|-----------------------------------------|-------------------------------------|
| GitLab CI           | `.gitlab-ci.yml`           | `script`, `before_script`, `after_script`                             | `variables:` (top-level + per-job)      | Official JSON schema + lint API     |
| GitHub Actions      | `.github/workflows/*.yml`  | `run:` (in steps)                                                     | `env:` (top-level + per-job + per-step) | JSON schema (SchemaStore)           |
| CircleCI            | `.circleci/config.yml`     | `run:` (in steps, `command:` key)                                     | `environment:`                          | JSON schema (official)              |
| AWS Buildspec       | `buildspec.yml`            | `commands:` in phases (`install`, `pre_build`, `build`, `post_build`) | `env.variables:`                        | JSON schema (unofficial/community)  |
| Bitbucket Pipelines | `bitbucket-pipelines.yml`  | `script:` in steps                                                    | `variables:` (limited)                  | JSON schema (unofficial/Atlassian)  |
| Semaphore           | `.semaphore/semaphore.yml` | `commands:` in tasks/jobs                                             | `env_vars:`                             | JSON schema (official Semaphore v2) |

---

## Proposed Architecture

### Single Package, Multi-Target + Pluggy Extension

Rename the package to `bash2yaml`. Introduce a **target** concept. Each target is a platform adapter that knows:

1. Which YAML keys contain script lines (e.g. `script:`, `run:`, `commands:`)
2. Where variables live
3. Which JSON schema to validate against
4. What the default output filename is

The compilation pipeline stays generic. A target adapter plugs in at the "find script lines" and "validate output"
stages.

**Built-in target adapters** live in `bash2yaml/targets/` and ship with the package:

```
targets/
├── base.py           # Abstract base / interface
├── gitlab.py         # Existing GitLab logic migrated here
├── github.py         # GitHub Actions
├── circleci.py       # CircleCI
├── buildspec.py      # AWS CodeBuild
├── bitbucket.py      # Bitbucket Pipelines
└── semaphore.py      # Semaphore CI
```

Third-party targets (Jenkins, Azure DevOps, etc.) are deliverable as pluggy plugins — same extension mechanism already
used for script inliners. A plugin registers a new target name; the CLI `--target` flag picks it up automatically.

The CLI gets a `--target` flag (or the target is auto-detected from the input filename / config).

---

## Migration Plan

### Phase 0 — Rename & Restructure (No New Features)

**This phase must be complete and all tests passing before any other phase begins.**

1. Rename internal module from `bash2yaml/` to `bash2yaml/`
2. Rename config file from `bash2yaml.toml` → `bash2yaml.toml` (with backwards-compatible fallback for a few versions)
3. Rename env var prefix `bash2yaml_` → `BASH2YAML_` (with backwards-compatible fallback for a few versions)
4. Update CLI entry points: `bash2yaml` / `b2y` (keep `b2gl` as a deprecated alias for a few versions)
5. Keep `bash2yaml` as a separate thin wrapper package on PyPI that depends on `bash2yaml` and re-exports everything —
   maintained for a few versions then deprecated
6. Write additional unit tests to improve coverage of existing behavior before the rename, so regressions are caught
   during the rename itself
7. All tests pass, no behavior changes

**Gate: Do not start Phase 1 until Phase 0 is complete with green tests.**

### Phase 1 — Target Abstraction

1. Define `BaseTarget` interface with methods:
    - `script_key_paths(doc) → list[tuple]` — yield (job_name, script_section, list_of_lines) for all scriptable
      sections
    - `variables_key_paths(doc) → list[tuple]` — yield locations of variable sections
    - `default_output_filename() → str`
    - `validate(doc, path) → list[ValidationError]`
    - `schema_url() → str | None` — for fetching/caching remote schemas
2. Refactor `compile_all.py` to call target methods instead of hardcoding GitLab structure
3. Implement `GitLabTarget` by extracting existing logic
4. Add `--target` CLI flag and `target =` config key
5. Add auto-detection: sniff input filename or directory structure to pick default target
6. All existing behavior preserved via `GitLabTarget`

### Phase 2 — GitHub Actions Target

**Structural differences from GitLab:**

- File lives in `.github/workflows/` (multiple files per repo, not one)
- Jobs are nested under `jobs:` key
- Scripts live in `steps:` as `run:` multiline string blocks — the entire block is one script, not an array of lines
- Variables: `env:` at workflow level, job level, and step level
- No built-in `before_script` / `after_script` — these are modeled as separate steps
- Uses `uses:` for reusable actions — skip inlining these, leave them untouched

**Note on `run:` inlining:** Because GitHub uses a multiline string (`run: |`) rather than an array of lines, the
inliner treats the entire block as a single script reference (e.g. `run: ./scripts/build.sh`). The referenced file's
contents replace the whole `run:` value as a literal block scalar. This is equivalent to how a developer would mentally
read it: "this step runs this script."

**Variable files** still use `global_variables.sh` / `jobname_variables.sh` shell syntax. The `global_variables.sh` file
serves double duty: the tool reads it to populate the YAML `env:` block, and developers can also `source` it locally
during debugging. The target adapter converts the parsed key/value pairs into GitHub's `env:` dict format.

**Tasks:**

1. Implement `GitHubTarget`
2. Handle `run: |` multiline blocks
3. Handle `env:` variable merging at workflow, job, and step scopes
4. Fetch/cache GitHub Actions JSON schema from SchemaStore
5. Handle compiling multiple files (treat workflow directory as `input_dir`)
6. Add examples

### Phase 3 — CircleCI Target

**Structural differences:**

- Config at `.circleci/config.yml`
- Steps are under `jobs.<name>.steps[].run.command` (or shorthand `run: command`)
- Multi-line `run` can use `command: |` key
- Environment: `environment:` at job level and executor level
- `orbs:` are reusable units — skip inlining these
- Workflows section just orchestrates — no scripts there

**Tasks:**

1. Implement `CircleCITarget`
2. Handle both `run: "single line"` and `run:\n  command: |` forms
3. Fetch/cache CircleCI JSON schema
4. Add examples

### Phase 4 — AWS Buildspec Target

**Structural differences:**

- File is `buildspec.yml` (standalone, not a pipeline file per se)
- Scripts live in `phases.<phase>.commands[]` — array of strings (similar to GitLab)
- Phases: `install`, `pre_build`, `build`, `post_build`
- Variables: `env.variables` dict and `env.parameter-store` (SSM), `env.secrets-manager`
- No concept of jobs — single build context
- `finally:` block in each phase for cleanup

**Tasks:**

1. Implement `BuildspecTarget`
2. Handle phase-based structure
3. Handle `env.variables` merging
4. Find or write JSON schema (AWS doesn't have an official one — may need community schema or write our own subset)
5. Add examples

### Phase 5 — Bitbucket Pipelines Target

**Structural differences:**

- File is `bitbucket-pipelines.yml`
- Scripts live under `pipelines.<trigger>.*.steps[].script[]` — array of strings (similar to GitLab)
- Multiple pipeline triggers: `default`, `branches`, `tags`, `pull-requests`, `custom`
- Variables: no top-level `variables:` equivalent — Bitbucket uses repo/workspace settings; YAML has `variables:` for
  manual trigger inputs only
- `after-script:` analogous to GitLab's `after_script`
- `services:` and `definitions:` sections — skip inlining

**Tasks:**

1. Implement `BitbucketTarget`
2. Navigate nested pipeline trigger structure
3. Handle `definitions.steps` (reusable step definitions via YAML anchors)
4. Find/use Atlassian's JSON schema
5. Add examples

### Phase 6 — Semaphore Target

**Structural differences:**

- File is `.semaphore/semaphore.yml`
- Blocks → tasks → jobs, with `commands:` at the job level (array of strings)
- Environment: `env_vars:` array of `{name, value}` objects (different structure!)
- `prologue` and `epilogue` blocks with `commands:` (analogous to before/after_script)
- Pipelines can include other pipelines (promotions)

**Tasks:**

1. Implement `SemaphoreTarget`
2. Handle the `env_vars:` object-array format for variable merging
3. Handle `prologue`/`epilogue` as script sections
4. Fetch/cache Semaphore v2 JSON schema
5. Add examples

---

## Cross-Cutting Concerns

### Variable File Format

Currently `global_variables.sh` uses shell `KEY=VALUE` syntax. This maps cleanly to GitLab's `variables:` dict. For
other platforms this still works as the canonical source format, but the target adapter must write variables in the
platform's native structure (e.g. Semaphore's `env_vars: [{name: K, value: V}]`).

### Schema Management

Each target needs a schema. Current approach (GitLab): try remote fetch → 7-day cache → bundled fallback. This should be
generalized into a `SchemaFetcher` utility that any target can use.

Schemas to source:

- **GitLab:** `gitlab.com/-/raw/master/app/assets/javascripts/editor/schema/ci.json` (already have it)
- **GitHub Actions:** SchemaStore `json.schemastore.org/github-workflow.json`
- **CircleCI:** `json.schemastore.org/circleciconfig.json`
- **AWS Buildspec:** `json.schemastore.org/buildspec.json`
- **Bitbucket Pipelines:** `json.schemastore.org/bitbucket-pipelines.json`
- **Semaphore:** Semaphore docs / may need community schema

All SchemaStore schemas are available under Apache 2.0 / public domain — safe to bundle as fallbacks.

### Lint/Validate APIs

Users do not distinguish between "lint" and "validate" — these are the same command from their perspective. The `lint`
command covers both schema validation and any available API/CLI validation.

GitLab has a live lint API (`POST /api/v4/ci/lint`). Other platforms:

- **GitHub Actions:** No official lint API. Schema validation only.
- **CircleCI:** Has a CLI tool (`circleci config validate`) — shell out to it if installed, skip gracefully if not.
- **AWS:** No official lint API.
- **Bitbucket:** No official lint API.
- **Semaphore:** Has `sem` CLI for validation — shell out to it if installed, skip gracefully if not.

The `lint` command always runs schema validation. API/CLI validation runs additionally when applicable and available,
with a clear message if the external tool is not found.

### Decompile

Decompilation is currently GitLab-specific (looks for `script:`, `before_script:`, etc.). It needs to be target-aware.
Each target adapter should implement `decompile_script_sections()`.

### The `run` Command (Local Simulation)

`best_effort_runner.py` simulates GitLab pipelines locally. This is very platform-specific and hard to generalize.
Proposal: keep it GitLab-only for now, or make it explicitly unsupported for other targets with a clear error message.

### Detect Drift

Hash-based drift detection is purely output-file-level — fully platform-agnostic. No changes needed.

### Map / Deploy

The `map-deploy` / `copy2local` commands deal with Git repos. They are platform-agnostic at the file level. No changes
needed.

---

## Open Questions

**11. Auto-detection of target from input file**
When the user doesn't specify `--target`, the tool should sniff the input filename/directory to pick a target (e.g.
`.gitlab-ci.yml` → gitlab, `.github/workflows/` → github). But what if detection is ambiguous or the file has a
non-standard name? Should it fail loudly and demand `--target`, or fall back to GitLab as the default (preserving
existing behaviour)?

**12. The `init` command per platform**
Currently `init` scaffolds a new bash2yaml project. Each platform needs a different directory layout. Should
`init --target github` produce the correct scaffold for that platform, or should `init` stay GitLab-only until after all
targets are implemented?

**13. Compiled file header**
The output file currently gets a `# DO NOT EDIT — compiled with bash2yaml` header. For bash2yaml the header needs to
name the tool correctly. Should there be a `# target: github` line in the header too, so the tool can auto-detect the
target on subsequent runs by reading its own output? Or is that too clever?

**14. Inline begin/end markers**
GitLab output currently uses `# >>> BEGIN inline: path/to/script` / `# <<< END inline` comment markers. These work
because GitLab script sections are YAML arrays of strings. For GitHub's `run: |` multiline string, those comment markers
would become literal lines in the shell script — which is fine, but do you still want them? Or is a simpler marker (e.g.
just the shebang line) enough?

**15. The `decompile` command for GitHub**
Decompile reverses compilation: it reads `# >>> BEGIN inline` markers to split scripts back out. For GitHub, the entire
`run:` block would become one `.sh` file. The step `name:` would have to be used to derive the filename. Is `name:`
always present and clean enough to use as a filename slug, or do we need a different convention (e.g. a comment near the
`run:` key in the uncompiled source)?

**16. Scripts that span multiple steps (GitHub Actions)**
In GitLab you have one `script:` list per job. In GitHub Actions a job has many `steps:`, each potentially with its own
`run:`. A job-level `global_variables.sh` maps cleanly to a GitLab job. For GitHub, does `global_variables.sh` inject
`env:` at the **job** level (affecting all steps), or at each individual **step** level? And is there a per-step
variable file convention needed (e.g. `stepname_variables.sh`)?

**17. Uncompiled source location convention for GitHub**
For GitLab, `input_dir` contains the uncompiled `.gitlab-ci.yml` and a `scripts/` subdirectory. For GitHub, you'd have
multiple workflow files. Should the uncompiled sources live alongside the workflows (e.g. `.github/workflows/src/`) or
in a completely separate top-level directory (e.g. `ci/github/`)? This affects how `copy2local` and `map-deploy` work
for GitHub users.

**18. Pragma system portability**
The current pragma system (`# Pragma: do-not-inline`, `# Pragma: allow-outside-root`) lives in bash comments. Since
script inlining is platform-agnostic, pragmas work for all platforms. But the pragma syntax uses `#` — which is also a
YAML comment character. Is there any concern about pragmas appearing in raw YAML (not inside script lines) being
misinterpreted, or is this a non-issue because pragmas only appear inside script content?

**19. Test strategy for new targets**
The current test suite tests against real GitLab CI YAML fixtures. For new platforms: should each target have its own
fixture-based integration tests (a complete uncompiled + expected-compiled pair per platform), or is unit-testing the
target's `script_key_paths()` / `variables_key_paths()` methods in isolation sufficient? Related: should the fixtures
live in `test/fixtures/github/`, `test/fixtures/circleci/`, etc.?

**20. `pyproject.toml` tool section name**
Currently config can live in `pyproject.toml` under `[tool.bash2yaml]`. After the rename this becomes
`[tool.bash2yaml]`. Should the backwards-compat fallback also read `[tool.bash2yaml]` for a few versions, or is
`pyproject.toml` considered too "permanent" to carry a stale section name and users should migrate it?

**21. Version numbering after rename**
Does bash2yaml start at `1.0.0` (clean break, signals new tool), continue from wherever bash2yaml left off (
continuity), or something else?

---

## Decisions Made

| Decision                       | Answer                                                                                                                              |
|--------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| Package name                   | `bash2yaml` / `b2y`                                                                                                                 |
| `bash2yaml` backwards compat | Thin wrapper package maintained for a few versions, then deprecated                                                                 |
| GitHub `run:` inlining         | Entire `run:` block treated as a single script reference                                                                            |
| Variable file format           | Keep `global_variables.sh` shell syntax; tool converts to each platform's native format; `.sh` enables `source` for local debugging |
| Phase 0 first                  | Yes — rename must be complete with green tests before any platform work begins                                                      |
| Platform order                 | No priority — all platforms are equal; implement in any convenient order after Phase 1                                              |
| `lint` vs `validate`           | One command (`lint`), always runs schema validation, adds API/CLI validation when available                                         |
| GitHub multiple workflow files | Treat `.github/workflows/` directory as `input_dir`, process all `.yml` files                                                       |
| Third-party target plugins     | Yes — pluggy extension point so external packages can register new targets                                                          |
| `b2y` CLI name                 | No known clashes — confirmed safe                                                                                                   |

---

## Files That Will Change Most

- `bash2yaml/commands/compile_all.py` — needs target abstraction injected
- `bash2yaml/commands/decompile_all.py` — needs target awareness
- `bash2yaml/commands/lint_all.py` — needs target-aware validation
- `bash2yaml/utils/validate_pipeline.py` — generalize to `validate_yaml.py`
- `bash2yaml/config.py` — add `target` config key
- `bash2yaml/__main__.py` — add `--target` flag
- `bash2yaml/schemas/` — add schemas for other platforms

## Files That Are Largely Platform-Agnostic (Change Little)

- `compile_bash_reader.py` — pure bash inlining, no YAML structure awareness
- `compile_not_bash.py` — pure script inlining, no YAML structure awareness
- `plugins.py` / `hookspecs.py` — plugin machinery stays the same
- `config.py` — mostly config loading, needs minor additions
- `watch_files.py` — file watching, fully generic
- `autogit.py`, `copy2local.py`, `map_deploy.py` — Git operations, generic
- `detect_drift.py` — hash comparison, fully generic
- `utils/` — most utilities are generic

---

## Rough Effort Estimate by Phase

| Phase | Description                          | Relative Effort  |
|-------|--------------------------------------|------------------|
| 0     | Rename & restructure                 | Small            |
| 1     | Target abstraction + GitLab refactor | Medium           |
| 2     | GitHub Actions target                | Medium           |
| 3     | CircleCI target                      | Small            |
| 4     | AWS Buildspec target                 | Small            |
| 5     | Bitbucket Pipelines target           | Small            |
| 6     | Semaphore target                     | Small            |
| —     | Schema management generalization     | Small            |
| —     | Docs, examples, tests per platform   | Medium (ongoing) |
