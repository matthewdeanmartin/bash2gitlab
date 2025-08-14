#!/usr/bin/env bats
load './test_helper.bash'

setup() { setup_tmpdir; }
teardown() { teardown_tmpdir; }

@test "lint fails early when --out dir is missing (exit 10) without contacting network" {
  # don't create OUTDIR; force the early error path
  MISSING="$TMPDIR/does-not-exist"
  run_cli lint --out "$MISSING" --gitlab-url "https://gitlab.example.invalid"
  [ "$status" -eq 10 ]
  [[ "$output" =~ "Output directory does not exist" ]]
}

@test "lint with empty out dir returns 0 (no files) or 2 (invalid) but should not crash" {
  run_cli lint --out "$OUTDIR" --gitlab-url "https://gitlab.example.invalid" --timeout 0.01
  # Depending on implementation: empty set may yield 0; network path guarded by empty file list.
  [[ "$status" -eq 0 || "$status" -eq 2 ]]
}
