# Documentation Skills for AI Contributors

This guide explains how to update documentation in bash2gitlab. Documentation consists of three areas: README.md, the readthedocs website in `/docs/`, and Python docstrings.

## Critical Rule: ALWAYS Run Formatters

**MANDATORY:** After editing ANY documentation file, you MUST run the appropriate formatter. Failing to do this is unacceptable.

- **Python files:** Run `make black` (runs isort + black)
- **Markdown files:** Run `make check_md` (runs mdformat)
- **Everything:** Run `make check_all_docs` to verify all documentation

Editing files with compact formatting to save tokens but forgetting to run the formatter is a common mistake. Do not make it.

## Documentation Areas

### 1. README.md (Root Level)

The main project documentation. Contains installation, quick start, usage examples, and comparison to alternatives.

**When to update:**

- New features are added
- Installation process changes
- Usage patterns change
- Examples need updating

**How to update:**

1. Edit `README.md` directly
1. Run `make check_md` to format and lint
1. Run `make check_spelling` to catch typos

### 2. ReadTheDocs Site (/docs/)

Detailed documentation in `/docs/` rendered at https://bash2gitlab.readthedocs.io/

**Structure:**

- `docs/index.md` - Landing page
- `docs/installation.md` - Installation guide
- `docs/usage/*.md` - Usage documentation
- `docs/extending/*.md` - Extensibility guides
- `docs/quality_gates/*.md` - Testing and linting docs
- `docs/CHANGELOG.md` - Version history

**When to update:**

- New commands are added
- Configuration options change
- Workflows need documenting
- API changes

**How to update:**

1. Edit the relevant `.md` file in `/docs/`
1. Run `make check_md` to format
1. Run `make make_docs` to generate HTML (optional, for preview)
1. Run `make check_spelling`

### 3. Python Docstrings

In-code documentation for modules, classes, and functions.

**Style Requirements:**

- **True:** Docstrings must accurately describe behavior
- **Not vacuous:** Must provide useful information, not obvious statements
- **Compact:** Minimize tokens while maintaining clarity

**Good docstring:**

```python
def normalize_path(path: Path, base: Path) -> Path:
    """Convert path to be relative to base directory.

    Args:
        path: Absolute or relative path to normalize.
        base: Base directory for relative resolution.

    Returns:
        Normalized path relative to base.
    """
```

**Bad docstring (vacuous):**

```python
def normalize_path(path: Path, base: Path) -> Path:
    """This function normalizes a path.

    Args:
        path: A path.
        base: A base.

    Returns:
        A path.
    """
```

**When to update:**

- Function signatures change
- Behavior changes
- New parameters added
- Return types change

**How to update:**

1. Edit docstrings in Python files
1. Run `make black` to format
1. Run `make check_docs` to verify coverage and test doctests

## Core Documentation Commands

These Makefile targets are the foundation of documentation work:

### check_docs

Verifies docstring coverage and tests embedded doctests.

```bash
make check_docs
```

- Runs `interrogate` - ensures 70% docstring coverage
- Runs `pydoctest` - validates doctests work

### make_docs

Generates HTML documentation from docstrings.

```bash
make make_docs
```

- Uses `pdoc` to create HTML docs in `docs/` directory
- Useful for previewing how docstrings render

### check_md

Validates and formats markdown files.

```bash
make check_md
```

- Runs `linkcheckMarkdown` - checks for broken links
- Runs `markdownlint` - lints markdown style
- Runs `mdformat` - **FORMATS MARKDOWN FILES**

### check_spelling

Checks spelling across all documentation.

```bash
make check_spelling
```

- Runs `pylint` with spelling checks on code
- Runs `codespell` on README.md, code, and docs
- Uses `private_dictionary.txt` for project-specific terms

**IMPORTANT:** When you encounter spelling errors for valid technical terms (like `autogit`, `dataclass`, `rtoml`, `iff`, etc.), add them to `private_dictionary.txt` in alphabetical order at the end of the file. These are project-specific terms that aren't in standard dictionaries but are correct in this codebase.

### check_changelog

Validates CHANGELOG.md format.

```bash
make check_changelog
```

- Runs `changelogmanager validate`
- Ensures changelog follows keepachangelog format

### check_all_docs

Runs all documentation checks.

```bash
make check_all_docs
```

Equivalent to: `check_docs check_md check_spelling check_changelog`

## Workflow Example

When updating documentation for a new feature:

1. **Update docstrings** in the relevant Python files

   ```bash
   # Edit bash2gitlab/commands/new_feature.py
   make black
   make check_docs
   ```

1. **Update README.md** with usage example

   ```bash
   # Edit README.md
   make check_md
   ```

1. **Add detailed documentation** in /docs/

   ```bash
   # Edit docs/usage/new_feature.md
   make check_md
   ```

1. **Update CHANGELOG.md** with changes

   ```bash
   # Edit CHANGELOG.md
   make check_changelog
   ```

1. **Run full documentation validation**

   ```bash
   make check_all_docs
   ```

1. **Run spelling check**

   ```bash
   make check_spelling
   ```

## Common Mistakes to Avoid

1. **Forgetting to run formatters** - The #1 mistake. Always run `make black` or `make check_md` after edits.

1. **Vacuous docstrings** - Don't state the obvious. "Returns a string" is useless if the return type already says `-> str`.

1. **Breaking links** - Run `make check_md` to catch broken links in markdown.

1. **Ignoring coverage** - `make check_docs` will fail if docstring coverage drops below 70%.

1. **Spelling errors** - Run `make check_spelling` before committing. Add valid project-specific technical terms (like `autogit`, `rtoml`, `OAuth`) to `private_dictionary.txt`.

1. **Inconsistent formatting** - Let the tools do it. Don't manually format - run the commands.

## Integration with Other Workflows

Documentation updates often accompany code changes:

- After implementing a feature, update docstrings and run `make black`
- Before running `make check` (full test suite), ensure `make check_all_docs` passes
- Before committing, run `make pre-commit` which includes formatting
- If adding new dependencies, update `README.md` and `docs/installation.md`

## Tips for Token Efficiency

1. **Be precise:** "Validates CI schema" beats "Validates the GitLab CI/CD pipeline YAML schema file"
1. **Omit obvious info:** Type hints make some docstring content redundant
1. **Use active voice:** "Compiles scripts" beats "This function compiles scripts"
1. **Skip redundant Args:** If `path: Path` is obvious, don't document it unless there's special behavior

But remember: **compact ≠ vacuous**. Always provide meaningful information.
