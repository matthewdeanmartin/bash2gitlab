#! /bin/bash
set -eou pipefail
echo "help..."
bash2gitlab --help
echo "compile help..."
bash2gitlab compile --help
echo "compile version..."
bash2gitlab --version
echo "compile (1)..."
bash2gitlab compile --in test/scenario2/src --out test/scenario2/out
echo "compile (2)..."
bash2gitlab compile --in test/scenario2/src --out test/scenario2/out --verbose
echo "compile (3)..."
bash2gitlab compile --in test/scenario2/src --out test/scenario2/out --dry-run
echo "compile (4)..."
bash2gitlab compile --in test/scenario2/src --out test/scenario2/out --quiet
echo "done..."