#! /bin/bash
set -euo pipefail
# Verify bash with common tools, such as shellcheck, prettier, bash dry run, bashate and many more

shellcheck src/*.sh
prettier src --write
