#! /bin/bash
set -eou pipefail
bash2yaml detect-drift --out test/scenario2/out
export NO_COLOR=NO_COLOR
bash2yaml detect-drift --out test/scenario2/out