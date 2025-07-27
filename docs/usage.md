# Usage

## Workflow

- shred your existing `.gitlab-ci.yml`
- open your shell files in your favorite IDE to see syntax highlighting, linting hints, etc.
- modify your shell files
- compile them to a .gitlab-ci.yml (or yaml templates)
- check in all files, both the source and compiled.

## Hints
- use a `/src/` and `/out/` folder pair
- You can separately do a deployment to get your `.gitlab-ci.yml` to the root of your repo. Don't compile to and from the same folder (say, root and `/src/`)


```bash
❯ bash2gitlab --help
usage: bash2gitlab [-h] [--version] {compile,shred} ...

positional arguments:
  {compile,shred}
    compile        Compile an uncompiled directory into a standard GitLab CI structure.
    shred          Shred a GitLab CI file, extracting inline scripts into separate .sh files.

options:
  -h, --help       show this help message and exit
  --version        show program's version number and exit
```

```bash
❯ bash2gitlab compile --help
usage: bash2gitlab compile [-h] --in INPUT_DIR --out OUTPUT_DIR [--scripts SCRIPTS_DIR] [--templates-in TEMPLATES_IN]
                           [--templates-out TEMPLATES_OUT] [--format] [--dry-run] [-v] [-q]

options:
  -h, --help            show this help message and exit
  --in INPUT_DIR        Input directory containing the uncompiled `.gitlab-ci.yml` and other sources.
  --out OUTPUT_DIR      Output directory for the compiled GitLab CI files.
  --scripts SCRIPTS_DIR
                        Directory containing bash scripts to inline. (Default: <in>)
  --templates-in TEMPLATES_IN
                        Input directory for CI templates. (Default: <in>)
  --templates-out TEMPLATES_OUT
                        Output directory for compiled CI templates. (Default: <out>)
  --format              Format all output YAML files using 'yamlfix'. Requires yamlfix to be installed.
  --dry-run             Simulate the compilation process without writing any files.
  -v, --verbose         Enable verbose (DEBUG) logging output.
  -q, --quiet           Disable output.
```

Shred is the command to convert your .gitlab-ci.yml into a collection of yaml and shell scripts that can be compiled. 
I'd expect this to be one time event.
```bash
❯ bash2gitlab shred --help
usage: bash2gitlab shred [-h] --in INPUT_FILE --out OUTPUT_FILE [--scripts-out SCRIPTS_OUT] [--dry-run] [-v] [-q]

options:
  -h, --help            show this help message and exit
  --in INPUT_FILE       Input GitLab CI file to shred (e.g., .gitlab-ci.yml).
  --out OUTPUT_FILE     Output path for the modified GitLab CI file.
  --scripts-out SCRIPTS_OUT
                        Output directory to save the shredded .sh script files.
  --dry-run             Simulate the shredding process without writing any files.
  -v, --verbose         Enable verbose (DEBUG) logging output.
  -q, --quiet           Disable output.
```