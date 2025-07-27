# bash2gitlab
Compile bash to yaml pipelines to get IDE support for bash and import bash from template repos

For example

.gitlab-ci.yml
```yaml
job:
    script:
        - ./script.sh.
```

script.sh
```bash
make build
```

compiles to

.gitlab-ci.yml
```yaml
job:
    script:
        - make build
```

See [extended examples here](https://github.com/matthewdeanmartin/bash2gitlab/tree/main/examples).

## Scenario
Your .gitlab-ci.yml pipelines are more bash than yaml. 1000s of lines of bash. But your IDE doesn't recognize
your bash as bash, it is a yaml string. You get syntax highlighting telling you that `script:` is a yaml key and that
is it.

So you extract the bash to a .sh file and execute it. But your job is mostly defined in a template in a centralized
repository. So the .sh file needs to be in every repo that imports the template. That's not good. You can't import
bash from the other repo.

Other solutions to get at a centralized bash script quickly get complicated.

## Installation

This is a standalone command, pipx is better.

```bash
pipx install bash2gitlab
```

If for some reason you want to use it as a library...

```bash
pip install bash2gitlab
```

## Usage

- Shred your current .gitlab-ci.yml file into yaml and bash
- Edit your bash
- Compile it
- Deploy the .gitlab-ci.yml to your project root by copying the file.

See [extended examples here](https://github.com/matthewdeanmartin/bash2gitlab/tree/main/examples).

```bash
❯ bash2gitlab compile --help
usage: bash2gitlab compile [-h] --in INPUT_DIR --out OUTPUT_DIR [--scripts SCRIPTS_DIR] [--templates-in TEMPLATES_IN]
                           [--templates-out TEMPLATES_OUT] [--format] [-v]

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
  -v, --verbose         Enable verbose (DEBUG) logging output.
```

## Name
Gitlab runners expect bash, sh or powershell. To use another shell, you have to use bash to execute a script in the other
shell.

## Special files

This will be inlined into the `variables:` stanza.

- global_variables.sh

## Out of scope
This doesn't inline include templates, only references to `.sh` files. In otherwords, if you are incluing many yaml
templates, then there will still be many yaml templates, they won't be merged to a single file.

This approach can't handle invocations that...

- multistatement, e.g. `echo hello && ./script.sh`
- rely on shebangs in the file e.g. `my_script`


## Formatting and comments
No particular guarantees that the compiled will have comments.

## Not ready yet
- Powershell is supported by gitlab, but not by this library... yet.
- Validate/lint with API calls to Gitlab.
- Support alternative yaml formatters (prettier, yamlfix, yamlfixer-opt-nc)
- custom shebang
- custom "do not edit" banner
- Include command to reproduce build copied to header
