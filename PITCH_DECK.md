# bash2yaml

## Write scripts. Compile to CI. Any platform.

---

## The Problem We Solve

CI/CD pipelines across every major platform share one dirty secret:

**Shell scripts trapped inside YAML strings.**

```yaml
- name: Build
  run: |
    set -eo pipefail
    apt-get update -qq
    apt-get install -y build-essential
    ./configure --prefix=/usr/local
    make -j$(nproc)
    make install
```

200 lines of bash. In a string. In a file your IDE treats as YAML.

No syntax highlighting. No linting. No unit testing. No reuse.

---

## The Solution

**bash2yaml** separates your scripts from your pipeline definition.

```
scripts/build.sh        →    compiled .github/workflows/build.yml
scripts/test.sh         →    compiled .circleci/config.yml
scripts/deploy.sh       →    compiled .gitlab-ci.yml
                        →    compiled buildspec.yml
```

Write real scripts. Get IDE support, shellcheck, bats tests.
Compile to any CI platform's native YAML.

**One codebase. Any pipeline. No compromises.**

---

## Who Uses CI/CD?

Everyone who ships software.

| Platform            | Estimated Users             |
|---------------------|-----------------------------|
| GitHub Actions      | 100M+ repositories          |
| GitLab CI           | 30M+ users                  |
| CircleCI            | Thousands of enterprises    |
| AWS CodeBuild       | Every AWS shop              |
| Bitbucket Pipelines | Millions of Atlassian teams |
| Semaphore           | Growing fast                |

We currently serve **GitLab CI only.**
That is a small slice of a very large pie.

---

## The Expansion: bash2yaml

```
bash2gitlab  →  bash2yaml
```

Same core engine. New targets.

- `bash2yaml compile --target github`
- `bash2yaml compile --target circleci`
- `bash2yaml compile --target buildspec`
- `bash2yaml compile --target bitbucket`
- `bash2yaml compile --target semaphore`
- `bash2yaml compile --target <your-plugin>`  ← extensible

---

## What Stays the Same

The hard parts are already built.

- Recursive bash `source` inlining
- 20+ language script inlining (Python, Node, Ruby, PHP, ...)
- Pragma system (`# Pragma: do-not-inline`)
- JSON schema validation
- Drift detection via hashes
- Plugin system (pluggy)
- Config hierarchy (toml + env vars)
- Git integration (pre-commit hooks, autogit, map-deploy)
- TUI / GUI / interactive modes

**All of this works for every target from day one.**

---

## Platform Comparison

| Feature                  | GitLab | GitHub | CircleCI | Buildspec  | Bitbucket |       Semaphore       |
|--------------------------|:------:|:------:|:--------:|:----------:|:---------:|:---------------------:|
| Array-style script lines |   ✓    |        |          |     ✓      |     ✓     |           ✓           |
| Multiline string scripts |        |   ✓    |    ✓     |            |           |                       |
| before/after script      |   ✓    |        |          | ✓ (phases) |     ✓     | ✓ (prologue/epilogue) |
| Top-level variables      |   ✓    |   ✓    |          |            |           |                       |
| Per-job variables        |   ✓    |   ✓    |    ✓     |            |           |           ✓           |
| Per-step variables       |        |   ✓    |    ✓     |            |           |                       |
| Official JSON schema     |   ✓    |   ✓    |    ✓     | community  | community |           ✓           |
| Live lint API            |   ✓    |        |  ✓ CLI   |            |           |         ✓ CLI         |
| Multiple pipeline files  |        |   ✓    |          |            |           |                       |

---

## Feature: Cross-Platform Script Sharing

Today: one `.sh` file compiles into one GitLab job.

Tomorrow: the same `.sh` file compiles into **all your platforms at once.**

```
scripts/
├── build.sh          # shared
├── test.sh           # shared
├── deploy.sh         # shared
└── notify_slack.sh   # shared

bash2yaml compile --target gitlab   → .gitlab-ci.yml
bash2yaml compile --target github   → .github/workflows/ci.yml
bash2yaml compile --target circleci → .circleci/config.yml
```

Organisations running multi-cloud or migrating between platforms
get this **for free.** Write once. Deploy everywhere.

---

## Feature: Platform Migration Assistant

Migrating from CircleCI to GitHub Actions?
From Bitbucket to GitLab?

bash2yaml is already doing the hard part — your scripts are
platform-neutral. The migration is just compiling to a new target.

```bash
# You already have:
bash2yaml compile --target circleci

# Migration day:
bash2yaml compile --target github

# That's it. Your scripts didn't change.
```

This is a **genuine differentiator** no other tool offers.

---

## Feature: Unified `global_variables.sh`

Every platform stores CI variables differently:

- GitLab: `variables:` dict
- GitHub: `env:` dict (3 scopes)
- Semaphore: `env_vars: [{name: K, value: V}]` array
- Buildspec: `env.variables:` dict

bash2yaml normalises all of this.
You write one `global_variables.sh`, source it locally for debugging,
and the tool emits the correct structure per platform.

```bash
# works locally:
source global_variables.sh && ./scripts/test.sh

# works in every CI system:
bash2yaml compile --target <any>
```

---

## Feature: GitHub Actions — Step-Level Script Management

GitHub's multi-step job structure gives bash2yaml a unique opportunity.

Instead of one big script per job, each step is a separately managed file:

```yaml
# uncompiled
steps:
  - name: Install dependencies
    run: ./scripts/install.sh
  - name: Run tests
    run: ./scripts/test.sh
  - name: Upload coverage
    run: ./scripts/coverage.sh
```

Each `.sh` is independently:

- version controlled
- shellchecked
- unit tested with bats
- reused across workflows

---

## Feature: GitHub Actions — Reusable Workflow Compilation

GitHub's `workflow_call` trigger enables reusable workflows.
bash2yaml can manage the scripts inside them exactly like regular workflows.

A team maintains a **central library** of `.sh` scripts.
Individual repos compile them into their own workflows.

This is the GitHub-native equivalent of GitLab's `include:` pattern —
already a first-class feature in bash2yaml for GitLab.

---

## Feature: CircleCI Orb Script Extraction

CircleCI Orbs embed shell commands as YAML strings — the same problem
we solve for pipelines, but at the reusable component level.

**Future target: `bash2yaml compile --target circleci-orb`**

Manage orb commands as `.sh` files. Compile into the orb YAML.
Publish cleaner, more maintainable orbs.

---

## Feature: AWS Buildspec — Phase-Aware Compilation

Buildspec has named phases: `install`, `pre_build`, `build`, `post_build`.
Each phase can have a `finally:` block.

bash2yaml maps these to conventional script names:

```
scripts/
├── install.sh         → phases.install.commands
├── pre_build.sh       → phases.pre_build.commands
├── build.sh           → phases.build.commands
├── post_build.sh      → phases.post_build.commands
├── install_finally.sh → phases.install.finally.commands
└── build_finally.sh   → phases.build.finally.commands
```

Every AWS CodeBuild project gets the same IDE support
and quality gates that GitLab users have today.

---

## Feature: AWS Buildspec — SSM / Secrets Manager Awareness

Buildspec's `env.parameter-store` and `env.secrets-manager` sections
reference secrets by ARN. bash2yaml can:

- Keep secrets references in `global_variables.sh` as comments
- Populate the `parameter-store:` section separately from `variables:`
- Warn if a variable looks like a secret but is in the wrong section

Secrets hygiene as a compile-time check. No more accidental plaintext
values in `env.variables` that should be in Secrets Manager.

---

## Feature: Bitbucket Pipelines — Definitions Management

Bitbucket's `definitions:` section holds reusable step templates
and service containers. Steps are shared via YAML anchors.

bash2yaml can manage the scripts inside `definitions.steps[*].script`
the same way it manages regular pipeline steps.

A `definitions_variables.sh` convention could populate
shared variables used across pipeline triggers.

---

## Feature: Semaphore — Prologue/Epilogue as Named Scripts

Semaphore's `prologue` and `epilogue` are the equivalent of
GitLab's `before_script` / `after_script`.

bash2yaml maps them conventionally:

```
scripts/
├── prologue.sh   → block.task.prologue.commands
└── epilogue.sh   → block.task.epilogue.commands
```

Teams writing Semaphore pipelines get the same
before/after script management they'd have in GitLab.

---

## Feature: `detect-drift` Across All Platforms

The hash-based drift detection system works at the file level.
It is fully platform-agnostic from day one.

**Every platform gets:**

- Detection of manual edits to compiled files
- Pre-commit hooks that refuse to commit manually-edited compiled output
- `bash2yaml detect-drift` in CI to fail the pipeline if drift is found

This is a behaviour most teams don't have for any platform.
bash2yaml brings it to all of them.

---

## Feature: `map-deploy` for Cross-Repo CI Standards

Organisations with many repositories often want to standardise
their pipeline configuration across all of them.

bash2yaml's `map-deploy` command pushes compiled YAML to
multiple target repositories in one operation.

With multi-platform support, a central team can maintain
one source of truth and deploy to:

- All GitHub repos (GitHub Actions workflows)
- All GitLab projects (GitLab CI)
- Mixed estates

**One CI standards team. All repos. All platforms.**

---

## Feature: The Plugin Ecosystem

bash2yaml ships with 6 built-in targets.
The plugin system (pluggy) means anyone can add more.

**Community targets could include:**

- Azure DevOps Pipelines
- Jenkins declarative pipelines
- Drone CI
- Woodpecker CI
- Harness CI
- TeamCity
- Tekton (Kubernetes-native CI)
- Dagger (code-first pipelines)

A plugin registers a target name. Users install the plugin.
`bash2yaml compile --target azure-devops` just works.

---

## Feature: IDE Integration Opportunities

With a well-defined source format (uncompiled YAML + `.sh` files),
third parties can build:

- **VS Code extension**: navigate from compiled YAML back to source `.sh`
- **JetBrains plugin**: inline script preview alongside pipeline YAML
- **Language server**: autocomplete for pragma comments
- **Linting integration**: shellcheck errors surfaced in the CI YAML editor

The separation of scripts from YAML is the foundation
these tools need to exist.

---

## Feature: `graph` Command Per Platform

The existing `graph` command shows inline dependency relationships
(which scripts source which other scripts).

With multi-platform support, graph can also show:

- Which workflow files share scripts (GitHub)
- Which CircleCI jobs share orb commands
- Cross-platform script reuse visualisation

**"This script is used in 3 platforms and 7 jobs."**

---

## Feature: Quality Gates — Shellcheck Integration

Shellcheck is a static analyser for shell scripts.
It currently works on `.sh` files independently.

bash2yaml can integrate shellcheck as a compile-time gate:

- Run shellcheck on all referenced scripts before inlining
- Fail compilation if shellcheck reports errors
- Report which CI job/step/platform would be affected by each error

**Every platform gets shellcheck-clean scripts. Automatically.**

---

## Feature: Quality Gates — bats Test Runner

`bats` is a bash testing framework.
bash2yaml's `run` command (local simulation) can integrate with it:

- Discover `test/*.bats` files alongside each `.sh` file
- Run bats tests before compilation
- Refuse to compile if tests fail

**Tested scripts in. Compiled YAML out.**

Platform-agnostic quality gate that works regardless of
which CI system the compiled YAML runs on.

---

## Feature: `doctor` Command Expansion

The current `doctor` checks the environment for bash2gitlab prerequisites.

With multiple platforms, `doctor` becomes a per-target health check:

- `bash2yaml doctor --target github` — checks for GitHub CLI, schema cache
- `bash2yaml doctor --target circleci` — checks for `circleci` CLI
- `bash2yaml doctor --target semaphore` — checks for `sem` CLI
- `bash2yaml doctor` — checks all configured targets

Onboarding friction reduced. New team members run one command
and know exactly what they need to install.

---

## Feature: `check-pins` Expansion

GitLab has `include:` statements for referencing external templates.
GitHub Actions has `uses: owner/action@ref` for third-party actions.

The existing `check-pins` command (which analyses GitLab `include:` refs)
can expand to:

- Detect unpinned `uses: owner/action@main` (security risk — should be `@sha256:...`)
- Warn about actions from unverified publishers
- Report actions that have newer versions available

**Supply chain security for GitHub Actions. At compile time.**

---

## Roadmap Summary

| Phase | Deliverable                        | Value                 |
|-------|------------------------------------|-----------------------|
| 0     | Rename to bash2yaml                | Foundation            |
| 1     | Target abstraction layer           | Architecture          |
| 2     | GitHub Actions target              | Largest new market    |
| 3     | CircleCI target                    | Enterprise users      |
| 4     | AWS Buildspec target               | Cloud-native shops    |
| 5     | Bitbucket target                   | Atlassian ecosystem   |
| 6     | Semaphore target                   | Growing segment       |
| 7     | Shellcheck integration             | Quality gate          |
| 8     | bats integration                   | Quality gate          |
| 9     | Plugin ecosystem                   | Community growth      |
| 10    | IDE integrations                   | Developer experience  |
| 11    | Cross-platform migration assistant | Unique differentiator |

---

## The Core Insight

Every CI platform reinvented the same mistake:

**Shell scripts do not belong inside YAML strings.**

bash2yaml fixes this mistake for every platform,
not just the one you happen to use today.

The tool your team needs when you adopt GitHub Actions
is the same tool you needed on GitLab CI.
It already exists. It just needs to know about your platform.

---

## bash2yaml

> Write scripts. Compile to CI. Any platform.

`pip install bash2yaml`

`bash2yaml init --target github`

`bash2yaml compile`

MIT License. Plugin-extensible. Built on a proven core.

---

*Built on bash2gitlab v0.9.10 — production-stable since 2024.*
