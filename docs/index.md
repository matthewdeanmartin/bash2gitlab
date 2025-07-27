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

## Scenario

Your .gitlab-ci.yml pipelines are more bash than yaml. 1000s of lines of bash. But your IDE doesn't recognize
your bash as bash, it is a yaml string. You get syntax highlighting telling you that `script:` is a yaml key and that
is it.

So you extract the bash to a .sh file and execute it. But your job is mostly defined in a template in a centralized
repository. So the .sh file needs to be in every repo that imports the template. That's not good. You can't import
bash from the other repo.

Do you want to import the template from the centralized repo and clone the centralized repo to get the non-yaml files?
That requires additional permissions that a simple yaml import doesn't and clutters the file system.

## Usage

See [extended examples here](https://github.com/matthewdeanmartin/bash2gitlab/tree/main/examples).

```bash
# compiling
bash2gitlab compile --in src --out out --format
# shredding
bash2gitlab shred --in original/.gitlab-ci.yml --out src
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
