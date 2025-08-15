set -euo pipefail
echo "Starting job in $CI_JOB_STAGE stage"
bash --version
echo "ENV: $CI_COMMIT_BRANCH on $CI_COMMIT_SHORT_SHA"