# Prior Art

Almost all prior art that I could find relates to just living with all your bash being a string in yaml.

I think this is painful because

- you must take yaml-escape your bash
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

I can't find any tools for executing a bash script locally without installing an entire gitlab instance with runners.

## Unit testing

As far as I know, no unit testing framework supports unit testing your bash in-place in the yaml.
