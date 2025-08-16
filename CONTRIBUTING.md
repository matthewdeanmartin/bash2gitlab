# Contributing

## Ways to contribute

- Open a ticket for a bug or feature.
- Customize via configuration, see [example config](examples/sample_config/pyproject.toml)
- Merge request. Open ticket, check if anyone is home, see below for house style and build.
- Plugins. Basic support for pluggy.
- Extend via public API. Public python API might not be super stable yet, consider pinning your version.
- Extend via orchestration tool, e.g. Justfile, Makefile. Some of the most obvious improvements would be a built-in
  formatter or linter, which I'm avoiding because there are so may complications with dependencies on tools that are not
  even written in Python.

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

# bash2gitlab House Style Guide

---

## 1. General Principles

* **Docstrings:** All public functions, classes, and modules have Google-style docstrings.
* **Type Annotations:** Required for all function parameters and return values (including `None`). Prefer Python 3.9+
  built-in generics (`list[str]`, `dict[str, Any]`).
* **Line Length:** Soft limit at 120 characters; 140 characters allowed if it improves clarity.

---

## 2. Logging

* Define `logger = logging.getLogger(__name__)` at module scope.
* Always use **f-strings** for message formatting — no `%` or `.format()` in logging.
* Always log paths **relative** to the current working directory to avoid visual clutter.
* Use:

    * `logger.debug()` for detailed internal state and should include variables.
    * `logger.info()` for normal operational messages.
    * `logger.warning()` for recoverable issues.
    * `logger.error()` for failures.

---

## 3. Exceptions

* Raise specific exceptions with clear, actionable messages.
* When wrapping third-party errors, preserve the original exception with `from e` unless intentionally suppressing
  context.
* Empty exception class definitions should include `pass` for visual clarity.

---

## 4. Function and Variable Naming

* Variables: `snake_case` prefix.
* No underscore prefix for scope (private/public), use __all__ for communicating scope/visibility
* Function names are **imperative** (`process_job`, `run_compile_all`) rather than descriptive nouns.
* Constants: `ALL_CAPS`.

---

## 5. Path Handling

* Use `pathlib.Path` consistently.
* Resolve paths with `strict=True` by default.
* When logging, log the shorter relative path.
* Use non-strict resolution only when explicitly making allowances for unit testing.

---

## 6. CLI Conventions

* CLI handlers:

    * Log start message.
    * Validate inputs.
    * Call core logic.
    * Catch expected exceptions and log user-friendly errors.
    * Return `int` exit codes.
    * `__main__` module with argparse code returns exit code. All other modules throw and do not sys.exit()


* Use consistent flag naming:

    * Long options are `--kebab-case`.
    * Map to `snake_case` in `dest`.
    * Prefer full descriptive names over abbreviations.

---

## 7. Data Structures

* Prefer built-in generics over `typing.List`/`typing.Dict`.
* Avoid mutable default arguments.
* For ordered YAML data, use `ruamel.yaml.comments.CommentedMap` and `CommentedSeq` where structure preservation is
  needed.

---

## 8. Diff and File Writing Patterns

* When rewriting files, log line-change counts at INFO level and full diffs at DEBUG level.
* Always write accompanying `.hash` files for generated YAML to detect drift.

---

## 9. Testing Hooks

* For modules with global config, provide `reset_for_testing()` helpers.
* Avoid side effects at import time (other than constant definitions and lazy loading).

---

## 10. Style Consistency Rules

* No bare `except:`.
* `None` checks use `is None` / `is not None`.
* When optional args are keyword-only, enforce with `*` in function signatures.
* Prefer early returns to deep nesting.

---

## 11. Inconsistencies to Avoid

* Mixing formatting styles in logging — **always use f-strings**.
* Don't use underscore for "private" functions. Use __all__ in the module header.
* Varied CLI option naming (prefer `--in` to `--input-dir`).
