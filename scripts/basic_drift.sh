#! /bin/bash
set -eou pipefail
bash2gitlab detect-drift --out test/scenario2/out
export NO_COLOR=NO_COLOR
bash2gitlab detect-drift --out test/scenario2/out