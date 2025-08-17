# bash2gitlab – Usage

This guide shows how to use **bash2gitlab** to move shell logic out of `.gitlab-ci.yml`, work locally with real shell
files, and compile back to clean CI YAML.

---

## Who this is for

* Teams with **centralized YAML templates** included across many repos.
* Pipelines where **most logic is Bash** but lives as YAML strings.
* Developers who want **IDE/bash tooling** (linting, shellcheck, formatting) on the actual scripts.

**Not a full YAML templating engine.** bash2gitlab focuses on inlining shell, not merging YAML structures or
orchestrating template complexity.

---

## Quickstart

```bash
# 1) Extract shell commands from your pipeline to real scripts
bash2gitlab decompile --in . --out ./compiled --scripts ./scripts

# 2) Edit scripts locally (lint, test, run)
vim scripts/my_job.sh

# 3) Compile: inline scripts into YAML again
bash2gitlab compile \
  --in . \
  --out ./compiled \
  --scripts ./scripts \
  --templates-in . \
  --templates-out ./compiled

# 4) (Optional) Watch for changes and recompile
bash2gitlab compile --in . --out ./compiled --scripts ./scripts --watch
```

Results land in `./compiled` by default (customizable). Commit as needed.

---

## Commands at a glance

| Command      | What it does                                                                                   |
|--------------|------------------------------------------------------------------------------------------------|
| `compile`    | Reads YAML, **inlines Bash** from your repo (and sourced scripts) back into `script:` entries. |
| `decompile`      | Scans YAML and **extracts Bash** to standalone `*.sh` files, leaving cleaner YAML behind.      |
| `copy2local` | Copies CI templates (e.g., from a centralized repo) into your repo for **local iteration**.    |
| `init`       | Creates **starter structure** (folders, sample config) for a smoother first run.               |

---

## Command details

### `compile`

Inline shell files into YAML `script:` steps.

```bash
bash2gitlab compile \
  --in <INPUT_DIR> \
  --out <OUTPUT_DIR> \
  [--scripts <SCRIPTS_DIR>] \
  [--templates-in <TEMPLATES_IN>] \
  [--templates-out <TEMPLATES_OUT>] \
  [--parallelism <N>] \
  [--dry-run] [-v|-q] [--watch]
```

#### Typical layout

```text
repo/
  .gitlab-ci.yml              # includes/uses jobs
  scripts/                    # your *.sh files
  templates/                  # optional yaml templates
  compiled/                   # output
```

#### Behavior

* Resolves `script:` entries like `./scripts/build.sh` and **inlines their contents**.
* Follows `source`/`.` directives **within scripts** (see *Inlining rules* below).
* Optionally inlines `global_variables.sh` into YAML `variables:` (see *Conventions*).
* Strips script shebangs when inlining.

#### Good to know

* `--dry-run` shows planned work without writing files.
* `--watch` re-runs on changes to inputs.
* `--parallelism` speeds large repos.

---

### `decompile`

Extract shell from YAML into real files so your IDE and shell tooling can work.

```bash
bash2gitlab decompile \
  --in <INPUT_DIR> \
  --out <OUTPUT_DIR> \
  [--scripts <SCRIPTS_DIR>] \
  [--templates-in <TEMPLATES_IN>] \
  [--templates-out <TEMPLATES_OUT>] \
  [--parallelism <N>] \
  [--dry-run] [-v|-q]
```

#### Behavior

* Finds `script:` blocks in YAML and writes them to `*.sh` files.
* Replaces the YAML `script:` with a shell call (e.g., `- ./scripts/jobname.sh`).
* Preserves job structure; doesn’t attempt YAML merging.

---

### `copy2local`

Bring remote/centralized CI templates into your repo for fast local cycles.

```bash
bash2gitlab copy2local \
  --in <TEMPLATES_IN> \
  --out <TEMPLATES_OUT>
```

#### Typical use

* You `include:` YAML from a central repo.
* Use `copy2local` to copy those templates (and their `src` shell folders) into `./local-ci/` in your repo.

#### Notes

* Copies `src/` contents (not the folder itself) to reduce path nesting.

---

### `init`

Create a minimal skeleton to try the workflow quickly.

```bash
bash2gitlab init --out .
```

Prompts you with questions and then creates a toml config.

---

## Inlining rules

**What triggers inlining**

* YAML `script:` entries that **invoke a single shell file** (e.g., `./scripts/build.sh`).
* Inside a script, lines matching `source <path>` or `. <path>` are **recursively inlined** up to a safe depth.

**Path resolution**

* Relative to the file that contains the reference.
* Constrained to the **project working tree**. Attempts to escape (`..` above repo root) are rejected.
* Symlinks are resolved; if they point outside the repo, they are rejected.

**Safety**

* Cycle detection prevents infinite recursion.
* Only **bare paths** are inlined. If a `source` line has extra args or command chaining, it is **not** inlined.

**Unsupported for inlining**

* Compound shell lines (e.g., `./build.sh && ./post.sh`).
* Commands with arguments that change semantics (e.g., `pwsh -NoProfile script.ps1`).

---

## File conventions

* `global_variables.sh` (optional): lines of `KEY=VALUE` (no spaces around `=`); will be inlined into YAML `variables:`.

**Example**

```bash
# scripts/global_variables.sh
IMAGE_TAG=latest
DEPLOY_ENV=staging
```

```yaml
# Result snippet in compiled YAML
variables:
  IMAGE_TAG: "latest"
  DEPLOY_ENV: "staging"
```

---

## Configuration & precedence

You can set options via **CLI flags**, **environment variables**, or **TOML config**. Precedence:

1. **CLI flags** (highest)
2. **Environment variables**
3. **TOML config** (e.g., `bash2gitlab.toml`) (lowest)

**Environment variables**

* Prefix: `BASH2GITLAB_` (e.g., `BASH2GITLAB_IN=.` `BASH2GITLAB_OUT=./compiled`).

**TOML example**

```toml
[tool.bash2gitlab]
# --- General Settings ---
input_dir = "ci/src"
output_dir = "ci/dist"
```
See config section for full example.

---

## Formatting, anchors & comments

* **Comments:** not guaranteed to be preserved through decompile/compile cycles.
* **Anchors & aliases:** supported for common cases; complex anchor patterns may be normalized.
* **Long lines & quoting:** compiler may reflow to keep valid YAML.

If anchors/comments are critical, keep them in template files you don’t round-trip often.

---

## Examples

### Example: simple job

```yaml
# .gitlab-ci.yml (authoring)
build:
  stage: build
  script:
    - ./scripts/build.sh
```

```bash
# scripts/build.sh
set -euo pipefail
source ./lib/common.sh
make build
```

**Compiled YAML (excerpt)**

```yaml
build:
  stage: build
  script:
    - |
      set -euo pipefail
      # from scripts/lib/common.sh
      # ...inlined content...
      make build
```

### Example: decompile then edit

```bash
bash2gitlab decompile --in . --out ./compiled --scripts ./scripts
# edit ./scripts/test.sh
bash2gitlab compile --in . --out ./compiled --scripts ./scripts
```

---

## Troubleshooting

* **A script didn’t inline**

    * Check the YAML uses a **single shell path** entry (no args/chains).
    * Ensure the file exists under the repo root and is executable (or at least readable).
    * Verify `source` targets are bare paths with no args.

* **Path traversal error**

    * A `source` path attempts to leave the repo (e.g., `../../secrets.sh`). Keep sources inside the working tree.

* **Variables missing**

    * Confirm `global_variables.sh` has `KEY=VALUE` pairs with no spaces around `=`.

* **YAML changed formatting**

    * Normalization is expected. Anchors/comments may be rearranged or dropped.

---

## Exit codes

* `0` success
* `1` other error
* `10` file not found
* `11` key error

---

## FAQ

**Q: Can I run this in CI?**
Yes, but you would have to commit changes for remote repositories to use the new files. Use `compile` in a job to
produce final YAML artifacts as a quality gate or in CI mode to fail the build when changes would have been made. (
feature pending implementation)

**Q: Will it merge template YAML?**
No. It focuses on shell inlining/extraction. Use your existing YAML includes/extends patterns.

**Q: How deep does `source` inlining go?**
A safe, finite depth. Cycles are detected and reported.

**Q: Can I inline scripts with arguments?**
No. Only bare `source <path>` and single-file `script:` invocations are inlined.
