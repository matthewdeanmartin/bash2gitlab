#!/usr/bin/env bats

# These tests stub the program executable to emit the expected line
# so we can validate test.sh's behavior without COBOL.

setup() {
  SANDBOX="$(mktemp -d)"
  cd "$SANDBOX"

  cp -f "${BATS_TEST_DIRNAME}/../test.sh" ./test.sh
  chmod +x ./test.sh
}

teardown() {
  rm -rf "$SANDBOX"
}

@test "test.sh (CI): uses env EXECUTABLE_NAME, creates test_input.dat, runs and greps expected output" {
  export CI=1
  export EXECUTABLE_NAME="payroll_tax_calculator"

  # Create a non-executable stub first; test.sh should chmod +x it
  cat > "$EXECUTABLE_NAME" <<'EOF'
#!/usr/bin/env bash
# Ignore stdin; just emit the line test.sh greps for
echo "Calculated Tax: 150.00"
EOF
  # Intentionally *not* executable yet
  chmod -x "$EXECUTABLE_NAME"

  run bash ./test.sh

  [ "$status" -eq 0 ]
  [[ "$output" == *"Running test with input from test_input.dat..."* ]]
  [[ "$output" == *"Test passed: The calculated tax is correct."* ]]

  # Input file should have been created with the amount
  [ -f test_input.dat ]
  grep -qx "1000.00" test_input.dat

  # Script should have made the program executable
  [ -x "$EXECUTABLE_NAME" ]
}

@test "test.sh (non-CI): sources global_variables.sh for EXECUTABLE_NAME" {
  unset CI
  cat > global_variables.sh <<'EOF'
#!/usr/bin/env bash
export EXECUTABLE_NAME="from_globals_exec"
EOF

  cat > from_globals_exec <<'EOF'
#!/usr/bin/env bash
echo "Calculated Tax: 150.00"
EOF
  chmod -x from_globals_exec  # test.sh should chmod +x

  run bash ./test.sh

  [ "$status" -eq 0 ]
  [[ "$output" == *"Test passed: The calculated tax is correct."* ]]
  [ -x from_globals_exec ]
  [ -f test_input.dat ]
}
