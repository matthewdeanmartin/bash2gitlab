# bash2gitlab
Compile bash to yaml pipelines to get IDE support for bash and import bash from centralized template repos

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

## Who is this for

- If you store your yaml templates in a centralized repo and `include:` them from other repos.
- If you have a lot of bash in your yaml that in theory could be executed locally

Your .gitlab-ci.yml pipelines are more bash than yaml. 1000s of lines of bash. But your IDE doesn't recognize
your bash as bash, it is a yaml string. You get syntax highlighting telling you that `script:` is a yaml key and that
is it.

So you extract the bash to a .sh file and execute it. But your job is mostly defined in a template in a centralized
repository. So the .sh file needs to be in every repo that imports the template. That's not good. You can't import
bash from the other repo.

## Who this is not for

If all your yaml pipelines are in a single repository, you can just reference bash files in your single repository.

If you have a trivial amount of bash in your templates

## Installation

This is a standalone command, installing with pipx is better than pip.

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

```text
❯ bash2gitlab --help
usage: bash2gitlab [-h] [--version] {compile,shred,copy2local,init} ...

positional arguments:
  {compile,shred,copy2local,init}
    compile             Compile an uncompiled directory into a standard GitLab CI structure.
    shred               Shred a GitLab CI file, extracting inline scripts into separate .sh files.
    copy2local          Copy folder(s) from a repo to local, for testing bash in the dependent repo
    init                Initialize a new bash2gitlab project and config file.

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit

❯ bash2gitlab compile --help
usage: bash2gitlab compile [-h] --in INPUT_DIR --out OUTPUT_DIR [--scripts SCRIPTS_DIR] [--templates-in TEMPLATES_IN] 
[--templates-out TEMPLATES_OUT] [--parallelism PARALLELISM] [--dry-run] [-v] [-q] [--watch]

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
  --parallelism PARALLELISM
                        Number of files to compile in parallel (default: CPU count).
  --dry-run             Simulate the compilation process without writing any files.
  -v, --verbose         Enable verbose (DEBUG) logging output.
  -q, --quiet           Disable output.
  --watch               Watch source directories and auto-recompile on changes.
```

## Bash completion

This project uses [argcomplete](https://github.com/kislyuk/argcomplete) for tab completion in Bash.
After installation, enable completions with one of the following:

```bash
# Enable for all Python executables
activate-global-python-argcomplete

# Or enable for the current shell only
eval "$(register-python-argcomplete bash2gitlab)"
```

## Supported Shells
Gitlab runners expect bash, sh or powershell. To use another shell, you have to use bash to execute a script in the other
shell.

## Special files

This will be inlined into the `variables:` stanza.

- global_variables.sh

## Out of scope
This doesn't inline `include:` templates, only references to `.sh` files. In other words, if you are including many yaml
templates, then there will still be many yaml templates, they won't be merged to a single file.

This approach can't handle invocations that...

- multistatement, e.g. `echo hello && ./script.sh`
- rely on shebangs in the file e.g. `my_script`


## Formatting and comments
No particular guarantees that the compiled will have comments.

## Prior Art
- [gitlab-ci-local](https://github.com/firecow/gitlab-ci-local) Runs pipeline in local docker containers. 

bash2gitlab differs in that it assumes you can and want to execute your bash scripts without docker containers.