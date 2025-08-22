#!/usr/bin/env bash
set -euo pipefail

. .venv/Scripts/activate
# no way to clean decompile targets yet.
python -c "import shutil, pathlib; shutil.rmtree(pathlib.Path('.src'), ignore_errors=True)"
bash2gitlab decompile --in-folder .decompile_in --out .src
echo "Decompile done"
bash2gitlab clean --out .build
echo "Clean done"
bash2gitlab compile --in .src --out .build
echo "Compile done"
python -m bash2gitlab.commands.best_effort_runner .build/.gitlab-ci.yml
echo "Runner done"