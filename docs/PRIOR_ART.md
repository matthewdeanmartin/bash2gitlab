# Prior Art

Almost all prior art that I could find relates to just living with all your bash being a string in yaml.

I think this is painful because

- you must yaml-escape your bash
- bash tooling doesn't support it
- any tool that does support bash-in-yaml needs to support it for many different CI syntaxes.

## shellcheck In-Place

- [gitlab-ci-shellcheck](https://github.com/spyoungtech/gitlab-ci-shellcheck)
- [yaml-shellcheck](https://github.com/mschuett/yaml-shellcheck) Supports multiple CI syntaxes
- [shellcheck-scripts-embedded-in-gitlab-ci-yaml](https://candrews.integralblue.com/2022/02/shellcheck-scripts-embedded-in-gitlab-ci-yaml/)

## IDE support for yaml in-place

- [harrydowning.yaml-embedded-languages](https://marketplace.visualstudio.com/items?itemName=harrydowning.yaml-embedded-languages)

## Formatting

I can't find any tools that format bash in-place in the yaml.

## Executing

- [Gitlab runner](https://docs.gitlab.com/runner/) Install both gitlab and a runner on your machine. Not really what
  most developers want to locally test their pipelines.
- [gitlab-ci-local](https://github.com/firecow/gitlab-ci-local)
- [ci-yml](https://pypi.org/project/ci-yml/) is close? You write your pipeline in travis syntax(!) in a ci.yml, execute
  it locally and then use the tool to execute as gitlab-ci.yml... I think.

## Unit testing

As far as I know, no unit testing framework supports unit testing your bash in-place in the yaml.
