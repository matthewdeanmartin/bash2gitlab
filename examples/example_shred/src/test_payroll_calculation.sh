#!/bin/bash

if [[ "${CI:-}" == "" ]]; then
  . ./global_variables.sh
fi

chmod +x ${EXECUTABLE_NAME}
echo "1000.00" > test_input.dat
echo "Running test with input from test_input.dat..."
./$EXECUTABLE_NAME < test_input.dat | grep "Calculated Tax: 150.00"
echo "Test passed: The calculated tax is correct."
