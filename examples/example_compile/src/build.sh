#! /bin/bash
# The -x flag creates an executable.
# The -o flag specifies the output name for the executable.
if [[ "${CI:-}" == "" ]]; then
  # shellcheck disable=SC1091
  . global_variables.sh
fi
cobc -x -o "${EXECUTABLE_NAME}" "${PROGRAM_NAME}".cbl
echo "Compilation successful. Executable created."