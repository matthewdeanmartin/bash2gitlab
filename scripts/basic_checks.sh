#! /bin/bash
set -eou pipefail
# Smoke test  all the tests that don't necessarily change anything
# exercises the arg parser mostly.

IN=test/test_commands/scenario2/src
OUT=test/test_commands/scenario2/out
set -eou pipefail
echo "help..."
bash2gitlab --help
echo "compile help..."
bash2gitlab compile --help
echo "compile version..."
bash2gitlab --version
echo "compile (1)..."
bash2gitlab compile --in "$IN" --out "$OUT"
echo "compile (2)..."
bash2gitlab compile --in "$IN" --out "$OUT" --verbose
echo "compile (3)..."
bash2gitlab compile --in "$IN" --out "$OUT" --dry-run
echo "compile (4)..."
bash2gitlab compile --in "$IN" --out "$OUT" --quiet
echo "Clean..."
mkdir --parents tmp
bash2gitlab clean --out tmp
rmdir tmp
echo "graph..."
bash2gitlab graph --in "$IN"
echo "Doctor..."
bash2gitlab doctor # --in "$IN" --out "$OUT"
echo "Decompile dry run..."
bash2gitlab decompile --in-folder "$OUT" --out tmp --dry-run
echo "Detect uncompiled..."
bash2gitlab detect-uncompiled  --in "$IN" --list-changed
echo "Detect drift"
bash2gitlab detect-drift  --out "$OUT"
echo "Show config..."
bash2gitlab show-config
echo "Map deploy..."
bash2gitlab map-deploy --dry-run
echo "Commit map..."
bash2gitlab commit-map --dry-run
# bash2gitlab copy2local  --dry-run # needs live git repo

echo "done..."