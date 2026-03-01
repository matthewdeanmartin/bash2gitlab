.EXPORT_ALL_VARIABLES:


# if you wrap everything in uv run, it runs slower.
ifeq ($(origin VIRTUAL_ENV),undefined)
    VENV := uv run
else
    VENV :=
endif

uv.lock: pyproject.toml
	@echo "Installing dependencies"
	@uv sync --all-extras

clean-pyc:
	@echo "Removing compiled files"


clean-test:
	@echo "Removing coverage data"
	@rm -f .coverage || true
	@rm -f .coverage.* || true

clean: clean-pyc clean-test

# tests can't be expected to pass if dependencies aren't installed.
# tests are often slow and linting is fast, so run tests on linted code.
test: clean uv.lock install_plugins
	@echo "Running unit tests"
	# $(VENV) pytest --doctest-modules bash2gitlab
	# $(VENV) python -m unittest discover
	$(VENV) pytest test -vv -n 2 --cov=bash2gitlab --cov-report=html --cov-fail-under 48 --cov-branch --cov-report=xml --junitxml=junit.xml -o junit_family=legacy --timeout=5 --session-timeout=600
	$(VENV) bash ./scripts/basic_checks.sh
#	$(VENV) bash basic_test_with_logging.sh

.PHONY: test-summary
test-summary: clean uv.lock install_plugins
	@echo "Running tests with summary output"
	$(VENV) pytest test -q --tb=short --no-header --cov=bash2gitlab --cov-fail-under 48 --cov-branch --timeout=5 --session-timeout=600
	$(VENV) bash ./scripts/basic_checks.sh

.PHONY: test-llm
test-llm: clean uv.lock install_plugins
	@echo "Running tests (LLM-optimized output)"
	NO_COLOR=1 $(VENV) pytest test -q --tb=line --no-header --color=no --cov=bash2gitlab --cov-fail-under 48 --cov-branch --cov-report=term-missing:skip-covered --timeout=5 --session-timeout=600 2>&1 | head -100
	$(VENV) bash ./scripts/basic_checks.sh

.PHONY: test-ci
test-ci: clean uv.lock install_plugins
	@echo "Running tests (CI mode)"
	$(VENV) pytest test -v -n auto --tb=short --cov=bash2gitlab --cov-report=html --cov-fail-under 48 --cov-branch --cov-report=xml --junitxml=junit.xml -o junit_family=legacy --timeout=5 --session-timeout=600
	$(VENV) bash ./scripts/basic_checks.sh

.PHONY: isort
isort:
	@echo "Formatting imports"
	$(VENV) isort .

.PHONY: jiggle_version

jiggle_version:
ifeq ($(CI),true)
	@echo "Running in CI mode"
	jiggle_version check
else
	@echo "Running locally"
	jiggle_version hash-all
	# jiggle_version bump --increment auto
endif

.PHONY: black
black: isort jiggle_version
	@echo "Formatting code"
	$(VENV) metametameta pep621
	$(VENV) black bash2gitlab # --exclude .venv
	$(VENV) black test # --exclude .venv
	$(VENV) git2md bash2gitlab --ignore __init__.py __pycache__ --output SOURCE.md

.PHONY: pre-commit
pre-commit: isort black
	@echo "Pre-commit checks"
	$(VENV) pre-commit run --all-files


.PHONY: bandit
bandit:
	@echo "Security checks"
	$(VENV) bandit bash2gitlab -r --quiet



.PHONY: pylint
pylint:  isort black
	@echo "Linting with pylint"
	$(VENV) ruff check --fix
	$(VENV) pylint bash2gitlab --fail-under 9.8

# for when using -j (jobs, run in parallel)
.NOTPARALLEL: /isort /black

.PHONY: quick-check
quick-check: mypy bandit
	@echo "✅ Quick checks complete (type checking, security)"

.PHONY: llm-check
llm-check: uv.lock
	@echo "Running LLM-optimized checks"
	@echo "→ Type checking..."
	@NO_COLOR=1 $(VENV) mypy bash2gitlab --ignore-missing-imports --check-untyped-defs 2>&1 | head -20
	@echo "→ Security scanning..."
	@if NO_COLOR=1 $(VENV) bandit bash2gitlab -r --quiet 2>&1 | grep -v "nosec encountered" | grep -v "^\[" > /tmp/bandit_output.txt 2>&1; then \
		if [ -s /tmp/bandit_output.txt ]; then cat /tmp/bandit_output.txt; fi; \
	fi; rm -f /tmp/bandit_output.txt || true
	@echo "→ Running tests..."
	@NO_COLOR=1 $(VENV) pytest test -q --tb=line --no-header --color=no --cov=bash2gitlab --cov-fail-under 48 --cov-branch --cov-report=term:skip-covered --timeout=5 --session-timeout=600 2>&1 | tail -50
	@echo "✅ LLM checks complete"

.PHONY: ci-check
ci-check: mypy test-ci pylint bandit update-schema
	@echo "✅ CI checks complete"

.PHONY: full-check
full-check: mypy test pylint bandit pre-commit update-schema
	@echo "✅ Full checks complete"

check: mypy test pylint bandit pre-commit update-schema

#.PHONY: publish_test
#publish_test:
#	rm -rf dist && poetry version minor && poetry build && twine upload -r testpypi dist/*

.PHONY: publish
publish: test
	rm -rf dist && hatch build

.PHONY: mypy
mypy:
	$(VENV) echo $$PYTHONPATH
	$(VENV) mypy bash2gitlab --ignore-missing-imports --check-untyped-defs


check_docs:
	$(VENV) interrogate bash2gitlab --verbose  --fail-under 70
	$(VENV) pydoctest --config .pydoctest.json | grep -v "__init__" | grep -v "__main__" | grep -v "Unable to parse"

make_docs:
	pdoc bash2gitlab --html -o docs --force

check_md:
	$(VENV) linkcheckMarkdown README.md
	$(VENV) markdownlint README.md --config .markdownlintrc
	$(VENV) mdformat README.md docs/*.md


check_spelling:
	$(VENV) pylint bash2gitlab --enable C0402 --rcfile=.pylintrc_spell
	$(VENV) pylint docs --enable C0402 --rcfile=.pylintrc_spell
	$(VENV) codespell README.md --ignore-words=private_dictionary.txt
	$(VENV) codespell bash2gitlab --ignore-words=private_dictionary.txt
	$(VENV) codespell docs --ignore-words=private_dictionary.txt

check_changelog:
	# pipx install keepachangelog-manager
	$(VENV) changelogmanager validate

check_all_docs: check_docs check_md check_spelling check_changelog

check_self:
	# Can it verify itself?
	$(VENV) ./scripts/dog_food.sh

#audit:
#	# $(VENV) python -m bash2gitlab audit
#	$(VENV) tool_audit single bash2gitlab --version=">=2.0.0"

install_plugins:
	echo "N/A"

.PHONY: issues
issues:
	echo "N/A"

core_all_tests:
	./scripts/exercise_core_all.sh bash2gitlab "compile --in examples/compile/src --out examples/compile/out --dry-run"
	uv sync --all-extras

update-schema:
	@mkdir -p bash2gitlab/schemas
	@echo "Downloading GitLab CI schema..."
	@if curl -fsSL "https://gitlab.com/gitlab-org/gitlab/-/raw/master/app/assets/javascripts/editor/schema/ci.json" -o bash2gitlab/schemas/gitlab_ci_schema.json ; then \
		echo "✅ Schema saved"; \
	else \
		echo "⚠️  Warning: Failed to download schema"; \
	fi
	@echo "Downloading NOTICE..."
	@if curl -fsSL "https://gitlab.com/gitlab-org/gitlab/-/raw/master/app/assets/javascripts/editor/schema/NOTICE?ref_type=heads" -o bash2gitlab/schemas/NOTICE.txt ; then \
		echo "✅ NOTICE saved"; \
	else \
		echo "⚠️  Warning: Failed to download NOTICE"; \
	fi