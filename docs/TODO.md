# TODO

## Compile
- Support `# bash2gitlab: Do not inine` Pragma
- Support `# bash2gitlab: start/stop ignore` Pragma
- Config option - prefer yaml comment, prefer bash comment (Maybe not?)

## UI 
- non tui interactive UI

## Decompile
- min lines before extracting (1 is too small?)
- support value/description syntax

```
variables:
  TOX_EXE:
    value: tox
    description: "The name of the tox executable."
```

## Config
- custom shebang
- custom "do not edit" banner

## Advanced Features
- Validate/lint with API calls to Gitlab.
