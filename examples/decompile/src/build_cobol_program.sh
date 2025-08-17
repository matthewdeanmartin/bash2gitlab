#!/bin/bash

if [[ "${CI:-}" == "" ]]; then
  . ./global_variables.sh
  . ./build_cobol_program_variables.sh
fi

cobc -x -o ${EXECUTABLE_NAME} ${PROGRAM_NAME}.cbl
echo "Compilation successful. Executable created."
