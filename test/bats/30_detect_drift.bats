#!/usr/bin/env bats
load './test_helper.bash'

setup() { setup_tmpdir; }
teardown() { teardown_tmpdir; }

@test "detect-drift runs against an empty out dir and exits 0" {
  run_cli detect-drift --out "$OUTDIR"
  [ "$status" -eq 0 ]
}
