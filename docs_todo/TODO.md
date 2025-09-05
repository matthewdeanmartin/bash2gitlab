# TODO

## Concurrency bug?

- see TestConcurrency, update checker problem.

## New commands

- pipeline trigger: after updating a central repo, go tell a bunch of repos to rebuild
- upgrade pipeline: pin unpinned templates, upgrade pinned templates to latest.


## Bugs
- validate fails on bad error if --out is missing.
- Permission denied on writing json schema to cache on window. FIXED.

## Perf
- rtoml
- caching/memoizing
- parallelize all commands
  - compile - done
  - validate - done
  - lint - done
  - all others ... TODO



## Bash Friendliness
- Map more errors to return codes. Make sure only `__main__` returns codes, all others throw python exceptions
- `--json` output option
- Support piped input (for single file at a time usage)

## detect drift/detect uncompiled
- not enough logging in some cases, dry run shows output, but w/o dry run no output at all.

## Errors

- Defaults to stack trace on compile when can't find the script.
- Blows up on inlining script in .sh file, should suggest adding `Pragma: do-not-inline`

## Core/All installation

- seems to want tomlkit when it core mode to run `--version`, but didn't happen in local testing! This probably affects
  all optional packages

## Best effort runner

- Doesn't stop on tools failing

## Minor Config

- For config not yet implemented in config file, just check env var.

## Compile

- config option to only inline if `.` or `source`?

## Complement to drift-detection

- Detect uncompiled. Same as `compile --dry-run` or `compile` but error on something done or TODO
- BUG: detect stray files doesn't detect stray files. (delete yaml from source, not deleted from destination). Should
  run at compile time

## Decompile

- min lines before extracting (1 is too small?). Partially done, need to make available to config/ui
- support value/description syntax. Partially done, need to update calling code.

```yaml
variables:
  TOX_EXE:
    value: tox
    description: "The name of the tox executable."
```

## Config

- move all config logic to config (cascade also happens in dunder-main)
- stronger concept of shared params
- allow --config-file to be set on any command
- better example of how to set config via env vars

## Docs

- docstrings
- reconcile docs to actual code
- merge docs script
- copy readme/contributing/change log at build time

## Analysis and design

- Do analysis & design doc for as-is
- Generate some improvement proposals

## Graph

- Does not open in browser? No arg to pass this along and the default is FALSE - partially fixed?
- pyvis doesn't specify encoding, so blows up on windows (out of bounds way to set this?) - fixed?
    - Will work if PYTHONUTF8=1 env var is set. - fixed?
- if dot isn't available, it blows up and doesn't retry, no way to check for recursion/retry - fixed?

- networkx is unreadable
- If you do retry from the error message, it recalculates the graph
- Graph seems to miss relationships between yaml files?

## Doctor

- Needs major attention
- blows up checking if a file is in a subfolder "stray source file: ... f.relative_to..."
- Warning about *Every* single .sh script in src, "Dependency not found and will be skipped..." - What?

## TUI

- console colors broken in log capture of 'clean' - fixed?
- console colors broken in log capture of compile, too - fixed?

## GUI

- GUI doesn't load defaults from config
- Color is completely garbled. GUI should run with NO COLOR - fixed?
- Doesn't switch to Console Output when you click a command, so it just sits there.

## Lint

- Lint doesn't grab the gitlab URL from the config

## Config

- Is parallelism coming from shared?

## Tests needed

- test of !reference "variable/scripts"
- test of variables with description

## Core/CI build

- options:
    - force everyone to pick core/all
    - Split library
    - Default to core, tell people how to install on 1st attempt to use a fancy feature

## Doctor

- Large script warnings at 25kb ?!
- Complains about husky hooks, but that is where bash2gitlab put the hooks 1st time around
- Spurious warning: Uncommited changes to map may be detectign that there was a recompile, e.g. undeployed changes
- Can't find powershell on a windows machine with powershell!