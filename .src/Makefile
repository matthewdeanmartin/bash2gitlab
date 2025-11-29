# Auto-generated Makefile for GitLab CI jobs
# Use 'make <job_name>' to run a job with proper before/after script handling

.PHONY: help

help:
	@echo 'Available jobs:'
	@echo '  bandit'
	@echo '  build_docs'
	@echo '  build_package'
	@echo '  check_docs'
	@echo '  lint'
	@echo '  mypy'
	@echo '  precommit'
	@echo '  publish_pypi'
	@echo '  pytest'
	@echo ''
	@echo 'Use: make <job_name> to run a job'

.PHONY: lint
lint:
	@echo 'Running lint main script...'
	@./lint.sh

.PHONY: mypy
mypy:
	@echo 'Running mypy main script...'
	@./mypy.sh

.PHONY: precommit
precommit:
	@echo 'Running precommit main script...'
	@./precommit.sh

.PHONY: pytest
pytest:
	@echo 'Running pytest main script...'
	@./pytest.sh

.PHONY: bandit
bandit:
	@echo 'Running bandit main script...'
	@./bandit.sh

.PHONY: check_docs
check_docs:
	@echo 'Running check_docs main script...'
	@./check_docs.sh

.PHONY: build_docs
build_docs:
	@echo 'Running build_docs main script...'
	@./build_docs.sh

.PHONY: build_package
build_package:
	@echo 'Running build_package main script...'
	@./build_package.sh

.PHONY: publish_pypi
publish_pypi:
	@echo 'Running publish_pypi main script...'
	@./publish_pypi.sh

.PHONY: all
all: bandit build_docs build_package check_docs lint mypy precommit publish_pypi pytest
