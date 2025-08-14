#!/usr/bin/env bats
load './test_helper.bash'

@test "suggests similar subcommand on typo" {
  run_cli copmile --help
  [ "$status" -ne 0 ]
  # Looser assertion to avoid coupling to exact phrasing:
  [[ "$output" =~ "compile" ]]
  [[ "$output" =~ "Unknown" || "$output" =~ "Did you mean" || "$output" =~ "similar" ]]
}
