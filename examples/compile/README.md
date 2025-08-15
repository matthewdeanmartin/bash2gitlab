 # Compile Example

This compiles a bash and a .gitlab-ci.yml file into just yaml files.

The reason for this is so that references to bash files are gone and you can import the yaml, inlined bash and all,
from any repo.

This is useful if you manage many, many repos and have centralized your yaml files and the bash in these templates
runs to hundreds or thousands of lines of bash.

If you have only one repo or if there is only one or two lines of bash per job, this is probably not the workflow for 
you.

## Workflow

Either run `./verify.sh` and `./compile.sh` individually or use the `Makefile` and run `make compile`.

Verify.sh is optional, it runs various linters, quality gates for your bash.

## Adapting the Bash to run locally

Add this to the header of your files to simulate global variables. 

```bash
if [[ "${CI:-}" == "" ]]; then
  . global_variables.sh
fi
```

