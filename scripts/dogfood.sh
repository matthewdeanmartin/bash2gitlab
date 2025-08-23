#!/usr/bin/env bash

set -euo pipefail

# Namespace prefix: b2g_

b2g_activate_venv() {
  if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows (Git Bash or similar)
    source .venv/Scripts/activate
  else
    # Unix-like
    source .venv/bin/activate
  fi
}

b2g_clean_src() {
  python -c "import shutil, pathlib; shutil.rmtree(pathlib.Path('.src'), ignore_errors=True)"
}

b2g_decompile() {
  bash2gitlab decompile --in-folder .decompile_in --out .src
  echo "✅ Decompile complete"
}

b2g_clean_build() {
  bash2gitlab clean --out .build
  echo "✅ Clean complete"
}

b2g_compile() {
  bash2gitlab compile --in .src --out .build
  echo "✅ Compile complete"
}

b2g_run_ci() {
  python -m bash2gitlab.commands.best_effort_runner .build/.gitlab-ci.yml
  echo "✅ Runner executed"
}

main() {
  b2g_activate_venv
  b2g_clean_src
  b2g_decompile
  b2g_clean_build
  b2g_compile
  b2g_run_ci
}

# Call main if not sourced
[[ "${BASH_SOURCE[0]}" == "$0" ]] && main "$@"
