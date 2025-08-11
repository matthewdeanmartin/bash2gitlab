#!/usr/bin/env bats

# These tests stub `cobc` so we don't need a COBOL toolchain.
# They also verify behavior when CI is set/unset (sourcing global_variables.sh).

setup() {
  # Temporary sandbox per test
  SANDBOX="$(mktemp -d)"
  cd "$SANDBOX"

  # Copy the scripts under test into the sandbox (assumes repo layout)
  # If your tests run from repo root, adjust these paths if needed.
  cp -f "${BATS_TEST_DIRNAME}/../build.sh" ./build.sh

  # A dummy COBOL source file (build.sh refers to "${PROGRAM_NAME}.cbl")
  touch dummy.cbl

  # Create a fake 'cobc' ahead of PATH that logs args and simulates output
  mkdir -p bin
  cat > bin/cobc <<'EOF'
#!/usr/bin/env bash
# Log argv for assertions
printf '%s\n' "$0 $*" >> cobc_invocations.log
# Parse flags to find -o <outfile> and last non-flag arg as src
out=""
src=""
while (( "$#" )); do
  case "$1" in
    -o)
      out="$2"; shift 2;;
    -*)
      shift;;
    *)
      src="$1"; shift;;
  esac
done
# Simulate "compile": create the output file
if [[ -n "$out" ]]; then
  : > "$out"
else
  # fallback if -o is missing (shouldn't happen)
  : > a.out
fi
# touch the "source" to prove we saw it
[[ -n "$src" ]] && [[ -e "$src" ]] || true
exit 0
EOF
  chmod +x bin/cobc
  export PATH="$PWD/bin:$PATH"
}

teardown() {
  rm -rf "$SANDBOX"
}

@test "build.sh (non-CI): sources global_variables.sh and invokes cobc with expected args" {
  # Arrange non-CI by unsetting CI and providing the globals file
  unset CI
  cat > global_variables.sh <<'EOF'
#!/usr/bin/env bash
export PROGRAM_NAME="dummy"
export EXECUTABLE_NAME="dummy_exec"
EOF

  # Ensure the expected .cbl exists (build.sh uses ${PROGRAM_NAME}.cbl)
  touch dummy.cbl

  run bash ./build.sh

  # Assert script succeeded
  [ "$status" -eq 0 ]
  # Assert success message
  [[ "$output" == *"Compilation successful. Executable created."* ]]

  # Assert the output executable exists
  [ -f "dummy_exec" ]

  # Assert cobc saw the right flags/args
  [ -f cobc_invocations.log ]
  grep -q -- "-x -o dummy_exec dummy.cbl" cobc_invocations.log
}

@test "build.sh (CI): uses environment variables instead of sourcing globals" {
  # Provide a globals file with *wrong* values to detect accidental sourcing
  cat > global_variables.sh <<'EOF'
#!/usr/bin/env bash
export PROGRAM_NAME="WRONG_NAME"
export EXECUTABLE_NAME="WRONG_EXEC"
EOF

  # Export CI and correct vars via env
  export CI=1
  export PROGRAM_NAME="ci_prog"
  export EXECUTABLE_NAME="ci_exec"
  touch ci_prog.cbl

  run bash ./build.sh

  [ "$status" -eq 0 ]
  [[ "$output" == *"Compilation successful. Executable created."* ]]

  # If build.sh had sourced globals under CI, we'd get WRONG_EXEC instead
  [ -f "ci_exec" ]
  [ ! -f "WRONG_EXEC" ]

  # Verify cobc call shape again
  grep -q -- "-x -o ci_exec ci_prog.cbl" cobc_invocations.log
}
