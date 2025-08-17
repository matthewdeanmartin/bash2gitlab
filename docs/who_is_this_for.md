# Who is this for

## You have a lot of bash in YAML

If your `script:` stanzas top out at a single line of bash, you don't need this. Use the minimum-lines setting in
decompile to avoid extracting one and two lines of bash to a file.

## You have centralized your gitlab templates

If you have only one repo, you can reference bash in a `./script.sh` file already. The problem happens only when
you need to put a lot of bash into YAML and then `include:` that template from a remote repo. When you do that, you
can't reference a `./script.sh` file, as its location is resolved relative to where the pipeline is running.

Gitlab, if you're listening, you could possibly solve some of the problem with

```yaml
script:
  - remote: project/folder/script.sh
```

## You need quality gates

Quality gates are tools like shellcheck, bats, formatters and IDEs. These tool never support working with bash in yaml
and probably never will because the various yaml-base CI formats are incompatible.

## The logic is mostly in bash and not yaml

If you use a cascading hierarchy of 3,000 yaml references/dereferences, hidden jobs with `extends:` to simulate
bash maps, variables that overwrite variables that overwrite variables, conditionalling including yaml templates and so
on....

Then most of your logic is in yaml tricks and you will need to run a real pipeline to capture all of that. You
might still benefit from shellcheck, formatting and IDE support, but you won't be able to execute a bash script locally,
independent of a pipeline.