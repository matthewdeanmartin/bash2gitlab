# TODO

- Powershell is supported by gitlab, but not by this library... yet.
- Validate/lint with API calls to Gitlab.
- Support alternative yaml formatters (prettier, yamlfix, yamlfixer-opt-nc)

## Change-in-generated-code-detection
- switch to whole doc comparison?

## Config
- custom shebang
- custom "do not edit" banner

## Compile
- Include command to reproduce build copied to header

## doesn't handle bash lines in a anchor 

```yaml
.thing: &anchor
  - echo 1
  - echo 2
```