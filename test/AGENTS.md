# Test Guidelines

All tests in this directory must use `pytest`.

- Prefer fixtures and helpers over mocking. Avoid unnecessary mocking and do not mock file system interactions.
- Use `tmp_path` for any file system interaction.
- The following pytest plugins are available:
  - `pytest-cov`
  - `pytest-xdist`
  - `pytest-randomly`
  - `pytest-sugar`
  - `pytest-mock`
  - `pytest-unused-fixtures`
  - `hypothesis`
  - `detect-test-pollution`
  - `pytest-timeout`
