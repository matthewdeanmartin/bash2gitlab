#!/usr/bin/env bash
set -euo pipefail
set -x

if [[ "${CI:-}" == "" ]]; then
  . before_script.sh
fi

# Run all Bats tests
bats tests/
