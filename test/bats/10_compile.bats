#!/usr/bin/env bats
load './test_helper.bash'

setup() { setup_tmpdir; }
teardown() { teardown_tmpdir; }

@test "compile --dry-run with explicit in/out exits 0" {
  # minimal uncompiled input (whatever your compiler expects—this can be empty if compile tolerates it)
  cat >"$SRCDIR/.gitlab-ci.yml" <<'YAML'
stages: [build]
build:
  stage: build
  script:
    - echo "hi"
YAML

  run_cli compile --in "$SRCDIR" --out "$OUTDIR" --dry-run
  [ "$status" -eq 0 ]
  # INFO logs generally go to stderr; bats merges streams into $output
  [[ "$output" =~ "Starting bash2gitlab compiler" ]]
}
