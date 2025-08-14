#!/usr/bin/env bats
load './test_helper.bash'

setup() { setup_tmpdir; }
teardown() { teardown_tmpdir; }

@test "clean --dry-run with out dir exits 0" {
  run_cli clean --out "$OUTDIR" --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" =~ "Starting cleaning output folder" ]]
}
