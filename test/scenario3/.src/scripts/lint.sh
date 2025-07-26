#!/usr/bin/env bash
set -euo pipefail
set -x

if [[ "${CI:-}" == "" ]]; then
  . before_script.sh
fi

# Example: lint with shellcheck
find . -name "*.sh" -exec shellcheck {} +
