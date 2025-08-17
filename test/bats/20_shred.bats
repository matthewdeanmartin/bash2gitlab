#!/usr/bin/env bats
load './test_helper.bash'

setup() { setup_tmpdir; }
teardown() { teardown_tmpdir; }

@test "decompile --dry-run processes a simple file" {
  IN="$SRCDIR/pipeline.yml"
  OUT="$OUTDIR/pipeline.decompileded.yml"
  cat >"$IN" <<'YAML'
job1:
  stage: build
  script:
    - echo "Hello"
    - |
      echo "inline block"
      echo "more lines"
YAML

  run_cli decompile --in "$IN" --out "$OUT" --dry-run
  [ "$status" -eq 0 ]
  [[ "$output" =~ "DRY RUN: Would have processed" ]] || [[ "$output" =~ "Successfully processed" ]]
}
