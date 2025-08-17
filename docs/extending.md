# Extending bash2gitlab

## Orchestration

Orchestration means using a tool like `make`, `just` or ordinary bash to move around, lint, reformat your code
after compiling.

## Python Scripting

See the `__all__` list in the `__init__` file for the current public API. Consider pinning versions if you take
a dependency on the Python API and doubly so if you program against the private API that isn't in the `__all__` list.

## pluggy Plugins

See hookspecs.py for the hooks available. Plugins allow deep integration without needing any coordination from the
application's maintainers.

## Contributing

You can extend bash2gitlab by making a merge request.