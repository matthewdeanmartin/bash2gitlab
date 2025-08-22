# Guidance for Future AI Contributors

This repository uses Python and Markdown. Follow these rules when modifying any files:

## Style
- Python is formatted with `isort` and `black`.
- Linting is managed by `ruff` and `pylint`.
- Type checks run through `mypy`.
- Markdown is formatted with `mdformat` and checked by `markdownlint`.

## Tests and Checks
- Run `make check` before committing. It runs formatting, unit tests, security checks, and pre-commit hooks.
- After `make check`, run `tox -e py38,py313,py314` to verify the lowest, current, and upcoming Python versions.
- For quick iterations you may run `pre-commit run --files <file>`.
- To run tests directly, use `uv run pytest`.

## Environment
- Dependencies are managed with `uv`. Run `uv sync --all-extras` if tools are missing.

## Commits
- Submit changes as a single commit on the main branch.

