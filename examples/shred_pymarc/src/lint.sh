#!/bin/bash

uv run ruff check .
uv run ruff format --check --diff .
uv run mypy .
