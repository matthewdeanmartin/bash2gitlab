# Workflow

bash2gitlab is a somewhat opinionated workflow.

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

## Shred existing yaml templates to bash and yaml

## Update bash so it can run locally and on your build server

## Validate bash with shellcheck, etc.

## Generate compiled

## Reference from other repos

## Deploy to other repo via copy2local

## Alternatively, deploy to other repos via "deploy-by-map" (not implemented yet)

## Execute bash locally

## Fix bugs in your bash locally

## Run the commit2central to copy local changes back to the centralized repo