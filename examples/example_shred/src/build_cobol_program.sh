#!/bin/bash
cobc -x -o ${EXECUTABLE_NAME} ${PROGRAM_NAME}.cbl
echo "Compilation successful. Executable created."
