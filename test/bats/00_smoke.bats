#!/usr/bin/env bats
load './test_helper.bash'

@test "shows help and exits 0" {
  run_cli --help
  [ "$status" -eq 0 ]
  [[ "$output" =~ "usage: bash2gitlab" ]]
  [[ "$output" =~ "compile" ]]
  [[ "$output" =~ "lint" ]]
}

@test "shows version and exits 0" {
  run_cli --version
  [ "$status" -eq 0 ]
  [[ "$output" =~ "bash2gitlab " ]]
}
