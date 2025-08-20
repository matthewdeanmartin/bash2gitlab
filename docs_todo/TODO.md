# TODO

## Pragma

```yaml
.some-script: &some-anchor
  - ./script1.sh  # Pragma: must-inline
```

## Compile

- config option to only inline if `.` or `source`?
- `Compiled with the command` will omit all the switches! Need to be able to normalize to command that reproduces.

## Compile Bug
- variables treated as scripts.

Secretly variables
```
.variables
   - X: 1
```

Explicitly variables
```
variables:
   - X: 1
```

Obviously variables
```
.some_job:
    variables:
       - X: 1
```


## Complement to drift-detection

- Detect uncompiled

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

- Does not open in browser? No arg to pass this along and the default is FALSE   - partially fixed?
- pyvis doesn't specify encoding, so blows up on windows (out of bounds way to set this?) - fixed?
  - Will work if PYTHONUTF8=1  env var is set.   - fixed?
- if dot isn't available, it blows up and doesn't retry, no way to check for recursion/retry  - fixed?

- networkx is unreadable
- If you do retry from the error message, it recalculates the graph
- Graph seems to miss relationships between yaml files?

## Doctor

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

