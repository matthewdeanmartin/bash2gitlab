# Contributing

## Getting going

Fork the repo.

```bash
uv sync
. ./.venv/Scripts/activate
```

Make changes

```bash
make check
```

Check Python compatibility across the lowest supported, current, and upcoming versions:

```bash
tox -e py38,py313,py314
```

## Scope

Yaml linting, yaml formatting are good features, even if they need a 3rd party library. The reason is that ruamel.yaml
doesn't necessarily output pretty yaml.

shfmt, shellcheck and any other tool you'd use with bash is out of scope because I don't want to maintain yet another
multitool tool aggregator.

After I've already named and published this tool, it occurs to me that I could re-do this for github actions, etc.
