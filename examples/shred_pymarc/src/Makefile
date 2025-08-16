# Auto-generated Makefile for GitLab CI jobs
# Use 'make <job_name>' to run a job with proper before/after script handling

.PHONY: help

help:
	@echo 'Available jobs:'
	@echo '  lint'
	@echo '  test-coverage'
	@echo '  test-python'
	@echo ''
	@echo 'Use: make <job_name> to run a job'

.PHONY: lint
lint: lint_before_script
	@echo 'Running lint main script...'
	@./lint.sh

.PHONY: lint_before_script
lint_before_script:
	@echo 'Running lint before script...'
	@./lint_before_script.sh

.PHONY: test-coverage
test-coverage: test-coverage_before_script
	@echo 'Running test-coverage main script...'
	@./test-coverage.sh

.PHONY: test-coverage_before_script
test-coverage_before_script:
	@echo 'Running test-coverage before script...'
	@./test-coverage_before_script.sh

.PHONY: test-python
test-python: test-python_before_script
	@echo 'Running test-python main script...'
	@./test-python.sh

.PHONY: test-python_before_script
test-python_before_script:
	@echo 'Running test-python before script...'
	@./test-python_before_script.sh

.PHONY: all
all: lint test-coverage test-python
