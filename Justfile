# Use bash with strict flags
set dotenv-load := true
set windows-shell := ["C:/Program Files/Git/usr/bin/bash.exe", "-c"]
set shell := ["bash", "-c"]

# Detect if we're in a virtual environment
venv := if env_var_or_default("VIRTUAL_ENV", "") == "" { "uv run" } else { "" }

# Default recipe to display help
default:
    @just --list

# Install dependencies
uv-lock:
    @echo "Installing dependencies"
    @uv sync --all-extras

# Remove compiled files
clean-pyc:
    @echo "Removing compiled files"

# Remove coverage data
clean-test:
    @echo "Removing coverage data"
    @rm -f .coverage || true
    @rm -f .coverage.* || true

# Clean all
clean: clean-pyc clean-test

# Install plugins
install-plugins:
    @echo "N/A"

# Run unit tests
test: clean uv-lock install-plugins
    @echo "Running unit tests"
    {{venv}} pytest test -vv -n 2 --cov=bash2gitlab --cov-report=html --cov-fail-under 48 --cov-branch --cov-report=xml --junitxml=junit.xml -o junit_family=legacy --timeout=5 --session-timeout=600
    {{venv}} bash ./scripts/basic_checks.sh

# Run tests with summary output
test-summary: clean uv-lock install-plugins
    @echo "Running tests with summary output"
    {{venv}} pytest test -q --tb=short --no-header --cov=bash2gitlab --cov-fail-under 48 --cov-branch --timeout=5 --session-timeout=600
    {{venv}} bash ./scripts/basic_checks.sh

# Run tests (LLM-optimized output)
test-llm: clean uv-lock install-plugins
    @echo "Running tests (LLM-optimized output)"
    NO_COLOR=1 {{venv}} pytest test -q --tb=line --no-header --color=no --cov=bash2gitlab --cov-fail-under 48 --cov-branch --cov-report=term-missing:skip-covered --timeout=5 --session-timeout=600 2>&1 | head -100
    {{venv}} bash ./scripts/basic_checks.sh

# Run tests (CI mode)
test-ci: clean uv-lock install-plugins
    @echo "Running tests (CI mode)"
    {{venv}} pytest test -v -n auto --tb=short --cov=bash2gitlab --cov-report=html --cov-fail-under 48 --cov-branch --cov-report=xml --junitxml=junit.xml -o junit_family=legacy --timeout=5 --session-timeout=600
    {{venv}} bash ./scripts/basic_checks.sh

# Format imports
isort:
    @echo "Formatting imports"
    {{venv}} isort .

# Version jiggling
jiggle-version:
    #!/usr/bin/env bash
    if [ "$CI" = "true" ]; then
        echo "Running in CI mode"
        jiggle_version check
    else
        echo "Running locally"
        jiggle_version hash-all
    fi

# Format code
black: isort jiggle-version
    @echo "Formatting code"
    {{venv}} metametameta pep621
    {{venv}} black bash2gitlab
    {{venv}} black test
    {{venv}} git2md bash2gitlab --ignore __init__.py __pycache__ --output SOURCE.md

# Pre-commit checks
pre-commit: isort black
    @echo "Pre-commit checks"
    {{venv}} pre-commit run --all-files

# Security checks
bandit:
    @echo "Security checks"
    {{venv}} bandit bash2gitlab -r --quiet

# Linting with pylint
pylint: isort black
    @echo "Linting with pylint"
    {{venv}} ruff check --fix
    {{venv}} pylint bash2gitlab --fail-under 9.8

# Type checking
mypy:
    {{venv}} echo $PYTHONPATH
    {{venv}} mypy bash2gitlab --ignore-missing-imports --check-untyped-defs

# Quick checks
quick-check: mypy bandit
    @echo "✅ Quick checks complete (type checking, security)"

# LLM-optimized checks
llm-check: uv-lock
    @echo "Running LLM-optimized checks"
    @echo "→ Type checking..."
    @NO_COLOR=1 {{venv}} mypy bash2gitlab --ignore-missing-imports --check-untyped-defs 2>&1 | head -20 || true
    @echo "→ Security scanning..."
    @NO_COLOR=1 {{venv}} bandit bash2gitlab -r --quiet 2>&1 | grep -v "nosec encountered" | grep -v "^\[" || true
    @echo "→ Running tests..."
    @NO_COLOR=1 {{venv}} pytest test -q --tb=line --no-header --color=no --cov=bash2gitlab --cov-fail-under 48 --cov-branch --cov-report=term:skip-covered --timeout=5 --session-timeout=600 2>&1 | tail -50 || true
    @echo "✅ LLM checks complete"

# CI checks
ci-check: mypy test-ci pylint bandit update-schema
    @echo "✅ CI checks complete"

# Full checks
full-check: mypy test pylint bandit pre-commit update-schema
    @echo "✅ Full checks complete"

# Run all checks
check: mypy test pylint bandit pre-commit update-schema

# Publish package
publish: test
    rm -rf dist && hatch build

# Check documentation
check-docs:
    {{venv}} interrogate bash2gitlab --verbose --fail-under 70
    {{venv}} pydoctest --config .pydoctest.json | grep -v "__init__" | grep -v "__main__" | grep -v "Unable to parse"

# Make documentation
make-docs:
    pdoc bash2gitlab --html -o docs --force

# Check markdown
check-md:
    {{venv}} linkcheckMarkdown README.md
    {{venv}} markdownlint README.md --config .markdownlintrc
    {{venv}} mdformat README.md docs/*.md

# Check spelling
check-spelling:
    {{venv}} pylint bash2gitlab --enable C0402 --rcfile=.pylintrc_spell
    {{venv}} pylint docs --enable C0402 --rcfile=.pylintrc_spell
    {{venv}} codespell README.md --ignore-words=private_dictionary.txt
    {{venv}} codespell bash2gitlab --ignore-words=private_dictionary.txt
    {{venv}} codespell docs --ignore-words=private_dictionary.txt

# Check changelog
check-changelog:
    {{venv}} changelogmanager validate

# Check all documentation
check-all-docs: check-docs check-md check-spelling check-changelog

# Self-check
check-self:
    {{venv}} ./scripts/dog_food.sh

# Issues
issues:
    @echo "N/A"

# Core all tests
core-all-tests:
    ./scripts/exercise_core_all.sh bash2gitlab "compile --in examples/compile/src --out examples/compile/out --dry-run"
    uv sync --all-extras

# Update schema
update-schema:
    @mkdir -p bash2gitlab/schemas
    @echo "Downloading GitLab CI schema..."
    @curl -fsSL "https://gitlab.com/gitlab-org/gitlab/-/raw/master/app/assets/javascripts/editor/schema/ci.json" -o bash2gitlab/schemas/gitlab_ci_schema.json && echo "✅ Schema saved" || echo "⚠️  Warning: Failed to download schema"
    @echo "Downloading NOTICE..."
    @curl -fsSL "https://gitlab.com/gitlab-org/gitlab/-/raw/master/app/assets/javascripts/editor/schema/NOTICE?ref_type=heads" -o bash2gitlab/schemas/NOTICE.txt && echo "✅ NOTICE saved" || echo "⚠️  Warning: Failed to download NOTICE"
