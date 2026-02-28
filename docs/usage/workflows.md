# Workflow

## decompileding

bash2gitlab decompileding is not necessarily opinionated.

- Decompile your `.gitlab-ci.yml` or other template with `bash2gitlab decompile`
- Open in your IDE for syntax highlighting
- Lint with shellcheck
- Find bugs and edit your original yaml to fix via copy-paste.
- Delete the decompiled bash

Round trip decompile-compile is not guaranteed, yaml is too quirky.

## Compiling

bash2gitlab compilation is a somewhat opinionated workflow and make the most sense when you are using a centralized
repo for your gitlab templates.

## Repo setup

- Create each of your other repos, e.g.
    - Infrastructure as code
    - Services/Data tier
    - User interface

Each of these will need builds scripts, eg.

- Quality gates
- Compilation and packaging
- Deployment to some environment

To validate your scripts you can run them locally or run them in a pipeline.

This works fine until you have scripts that are duplicated across each of your repos.

- Create a centralized template repo
- Update each repo to reference the centralized repo

Now each bash script will be resolved relative to the executing pipeline. So all the bash needs to be inlined.

As soon as you inline all your bash, you lose almost all tooling for bash.

## Converting pre-existing yaml

- Decompile existing yaml templates to bash and yaml
- Update bash so it can run locally and on your build server
- Validate bash with shellcheck, etc.

## Compilation

- Generate compiled
- Add precommit hook so it is compiled each time you attempt to commit

## Using your new scripts

- Reference from other repos with `include:` as per usual

## Debugging after script centralization

- Deploy to other repo via copy2local
- Alternatively, deploy to other repos via `map-deploy`
- Execute bash locally in the various repos
- Fix bugs in your bash locally
- Run the commit2central to copy local changes back to the centralized repo (pending feature)

## What could go wrong?

- Compile automatically detects unexpected changes in the generated code.
- People could edit the compiled code, use `detect-drift` to find that
- People could edit the compiled code and you delete it all to recompile. Use `clean` to do a careful clean and detect
  changes.