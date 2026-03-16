#! /bin/bash
set -eou pipefail
# Smoke test  all the tests that don't necessarily change anything
# exercises the arg parser mostly.

IN=test/test_commands/scenario2/src
OUT=test/test_commands/scenario2/out
set -eou pipefail
echo "help..."
bash2yaml --help
echo "compile help..."
bash2yaml compile --help
echo "compile version..."
bash2yaml --version
echo "compile (1)..."
bash2yaml compile --in "$IN" --out "$OUT"
echo "compile (2)..."
bash2yaml compile --in "$IN" --out "$OUT" --verbose
echo "compile (3)..."
bash2yaml compile --in "$IN" --out "$OUT" --dry-run
echo "compile (4)..."
bash2yaml compile --in "$IN" --out "$OUT" --quiet
echo "Clean..."
mkdir --parents tmp
bash2yaml clean --out tmp
rmdir tmp
echo "graph..."
bash2yaml graph --in "$IN"
echo "Doctor..."
bash2yaml doctor # --in "$IN" --out "$OUT"
echo "Decompile dry run..."
bash2yaml decompile --in-folder "$OUT" --out tmp --dry-run
echo "Detect uncompiled..."
bash2yaml detect-uncompiled  --in "$IN" --list-changed
echo "Detect drift"
bash2yaml detect-drift  --out "$OUT"
echo "Show config..."
bash2yaml show-config
echo "Map deploy..."
bash2yaml map-deploy --dry-run
echo "Commit map..."
bash2yaml commit-map --dry-run
# bash2yaml copy2local  --dry-run # needs live git repo

echo "done..."