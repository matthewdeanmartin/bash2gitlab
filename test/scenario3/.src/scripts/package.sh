#!/usr/bin/env bash
set -euo pipefail
set -x

if [[ "${CI:-}" == "" ]]; then
  . before_script.sh
fi

mkdir -p dist
tar -czvf dist/myproject.tar.gz scripts/ tests/
