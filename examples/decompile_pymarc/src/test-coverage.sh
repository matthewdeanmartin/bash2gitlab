#!/bin/bash

uv run coverage run -m unittest discover
uv run coverage xml
uv run coverage report
