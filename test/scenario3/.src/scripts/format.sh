#!/usr/bin/env bash
set -euo pipefail
set -x

if [[ "${CI:-}" == "" ]]; then
  . before_script.sh
fi

# Example: format with shfmt
shfmt -w -i 2 -ci .
